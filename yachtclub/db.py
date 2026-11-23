from __future__ import annotations

import time
import logging
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import ROOT


class Db:
    def __init__(self, settings: dict[str, str]):
        self.settings = settings
        self.pool = ConnectionPool(
            conninfo=self.conninfo,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )

    @property
    def conninfo(self) -> str:
        s = self.settings
        return (
            f"host={s['host']} port={s['port']} dbname={s['database']} "
            f"user={s['user']} password={s['password']} connect_timeout=3 "
            "application_name=yacht_club_manager"
        )

    def rows(self, sql: str, params: Iterable[Any] = (), actor_id: int | None = None) -> list[dict]:
        with self.pool.connection() as conn:
            if actor_id:
                conn.execute("SELECT set_config('app.user_id', %s, true)", (str(actor_id),))
            return conn.execute(sql, tuple(params)).fetchall()

    def one(self, sql: str, params: Iterable[Any] = (), actor_id: int | None = None) -> dict | None:
        result = self.rows(sql, params, actor_id)
        return result[0] if result else None

    def value(self, sql: str, params: Iterable[Any] = (), actor_id: int | None = None):
        row = self.one(sql, params, actor_id)
        return next(iter(row.values())) if row else None

    def execute(self, sql: str, params: Iterable[Any] = (), actor_id: int | None = None) -> int:
        with self.pool.connection() as conn:
            if actor_id:
                conn.execute("SELECT set_config('app.user_id', %s, true)", (str(actor_id),))
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount

    def readonly_query(self, sql: str) -> list[dict]:
        with self.pool.connection() as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout='5s'")
            return conn.execute(sql).fetchall()

    def transaction(self, actor_id: int | None = None):
        conn = self.pool.getconn()
        transaction = conn.transaction()
        transaction.__enter__()
        if actor_id:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (str(actor_id),))
        return Transaction(self.pool, conn, transaction)

    def close(self):
        self.pool.close()


class Transaction:
    def __init__(self, pool, conn, transaction):
        self.pool, self.conn, self.transaction, self.finished = pool, conn, transaction, False

    def execute(self, sql: str, params: Iterable[Any] = ()):
        return self.conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable[Any] = ()):
        return self.execute(sql, params).fetchone()

    def rows(self, sql: str, params: Iterable[Any] = ()):
        return self.execute(sql, params).fetchall()

    def commit(self):
        self.transaction.__exit__(None, None, None)
        self.finished = True
        self.pool.putconn(self.conn)

    def rollback(self):
        if not self.finished:
            exc = RuntimeError('transaction rolled back')
            self.transaction.__exit__(RuntimeError, exc, None)
            self.finished = True
            self.pool.putconn(self.conn)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            self.commit()
        else:
            self.rollback()


def connect_with_autostart(settings: dict[str, str], timeout: int = 55) -> tuple[bool, str]:
    """Wait for PostgreSQL, starting this project's compose service when configured."""
    conninfo = (
        f"host={settings['host']} port={settings['port']} dbname={settings['database']} "
        f"user={settings['user']} password={settings['password']} connect_timeout=2"
    )
    try:
        with psycopg.connect(conninfo):
            pass
        if settings.get("auto_start_docker", True):
            prepared, bootstrap_error = _ensure_application_role(settings)
            if not prepared:
                return False, f"Не удалось проверить схему PostgreSQL: {bootstrap_error}"
            return True, "База PostgreSQL доступна, схема и права проверены."
        return True, "База PostgreSQL доступна."
    except psycopg.Error as initial_error:
        if not settings.get("auto_start_docker", True):
            logging.getLogger('yachtclub').exception('PostgreSQL connection failed')
            return False, "PostgreSQL недоступен. Проверьте состояние контейнера и параметры подключения."
        import shutil
        import subprocess

        docker = shutil.which("docker")
        if not docker:
            candidates = (
                Path.home() / "AppData" / "Local" / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
                Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
            )
            docker = next((str(path) for path in candidates if path.is_file()), None)
        if not docker:
            return False, "Docker не найден. Установите и запустите Docker Desktop, затем откройте приложение снова."
        try:
            proc = subprocess.run(
                [docker, "compose", "up", "-d", "db"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            return False, f"Не удалось запустить PostgreSQL через Docker Compose: {exc}"
        if proc.returncode:
            return False, "Docker Compose не запустил базу данных.\n" + (proc.stderr or proc.stdout).strip()
        deadline = time.monotonic() + timeout
        last_bootstrap_error = str(initial_error)
        while time.monotonic() < deadline:
            prepared, bootstrap_error = _ensure_application_role(settings)
            if prepared:
                try:
                    with psycopg.connect(conninfo):
                        return True, "PostgreSQL запущен, схема и роль приложения готовы."
                except psycopg.Error as exc:
                    logging.getLogger('yachtclub').exception('Application DB connection failed after role bootstrap')
                    return False, "Схема подготовлена, но приложение не смогло подключиться. Подробности сохранены в журнале."
            last_bootstrap_error = bootstrap_error
            if "служебной учётной записью" in bootstrap_error:
                return False, bootstrap_error
            time.sleep(1)
        logging.getLogger('yachtclub').error('PostgreSQL bootstrap timed out: %s', last_bootstrap_error)
        return False, f"Не удалось подготовить PostgreSQL за {timeout} секунд. Подробности записаны в журнал приложения."


def _ensure_application_role(settings: dict[str, str]) -> tuple[bool, str]:
    """Create or update the local app role and its DML grants via the DB owner."""
    if not settings.get("password") or not settings.get("user"):
        return False, "В настройках не задан пользователь или пароль приложения."
    admin_conninfo = (
        f"host={settings['host']} port={settings['port']} dbname={settings['database']} "
        f"user={settings['admin_user']} password={settings['admin_password']} connect_timeout=3 "
        "application_name=yacht_club_manager_bootstrap"
    )
    try:
        role = sql.Identifier(settings["user"])
        password = sql.Literal(settings["password"])
        admin_role = sql.Identifier(settings["admin_user"])
        with psycopg.connect(admin_conninfo) as conn:
            # Apply the idempotent schema on every startup. Existing Docker
            # volumes can contain an older/partial schema (for example, the
            # tables may exist while the catalog views do not).
            schema_sql = (ROOT / "sql" / "001_schema.sql").read_text(encoding="utf-8")
            conn.execute(schema_sql, prepare=False)
            conn.execute("DELETE FROM weather_observations WHERE source='Демонстрационный набор'")
            seed_count = conn.execute("SELECT count(*) FROM roles").fetchone()[0]
            if seed_count == 0:
                seed_sql = (ROOT / "sql" / "003_seed.sql").read_text(encoding="utf-8")
                conn.execute(seed_sql, prepare=False)
            ports_migration = (ROOT / "sql" / "005_ports_and_pickup.sql").read_text(encoding="utf-8")
            conn.execute(ports_migration, prepare=False)
            gallery_migration = (ROOT / "sql" / "006_yacht_photo_gallery.sql").read_text(encoding="utf-8")
            conn.execute(gallery_migration, prepare=False)
            exists = conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (settings["user"],)
            ).fetchone()
            if exists:
                conn.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(role, password))
            else:
                conn.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(role, password))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(settings["database"]), role
            ))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
            conn.execute(sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(role))
            conn.execute(sql.SQL(
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"
            ).format(role))
            conn.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(admin_role, role))
            conn.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT USAGE, SELECT ON SEQUENCES TO {}"
            ).format(admin_role, role))
    except Exception as exc:
        if getattr(exc,'sqlstate',None)=='28P01':
            logging.getLogger('yachtclub').error('PostgreSQL bootstrap authentication failed')
            return False, "Не удалось войти в PostgreSQL служебной учётной записью. Проверьте локальные настройки подключения."
        logging.getLogger('yachtclub').exception('PostgreSQL schema bootstrap failed')
        return False, "Не удалось проверить или обновить схему PostgreSQL. Подробности записаны в журнал приложения."
    return True, "Роль приложения создана или синхронизирована."

