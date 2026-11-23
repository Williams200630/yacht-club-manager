from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[1]


def load_settings() -> dict[str, str]:
    env_file = ROOT / ".env"
    sample_file = ROOT / ".env.example"
    if not env_file.exists() and sample_file.exists():
        template = sample_file.read_text(encoding="utf-8")
        generated = secrets.token_urlsafe(32)
        template = template.replace("CHANGE_ME_ADMIN_PASSWORD", generated)
        template = template.replace("CHANGE_ME_APP_PASSWORD", secrets.token_urlsafe(32))
        env_file.write_text(template, encoding="utf-8")
    load_dotenv(env_file, override=False)
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": os.getenv("DB_PORT", "55432"),
        "database": os.getenv("DB_NAME", "yacht_club_manager"),
        "user": os.getenv("DB_USER", "yacht_app"),
        "password": os.getenv("DB_PASSWORD", ""),
        "admin_user": os.getenv("POSTGRES_ADMIN_USER", "yacht_admin"),
        "admin_password": os.getenv("POSTGRES_ADMIN_PASSWORD", ""),
        "app_user": os.getenv("POSTGRES_APP_USER", "yacht_app"),
        "app_password": os.getenv("POSTGRES_APP_PASSWORD", ""),
        "auto_start_docker": os.getenv("AUTO_START_DOCKER", "true").lower() == "true",
        "latitude": os.getenv("WEATHER_LATITUDE", "44.95"),
        "longitude": os.getenv("WEATHER_LONGITUDE", "34.10"),
    }

