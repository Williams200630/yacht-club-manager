from __future__ import annotations

import re
import bcrypt


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^[+\d][\d\s()\-]{8,19}$")


def validate_credentials(email: str, password: str) -> None:
    if not EMAIL_RE.fullmatch(email.strip().lower()):
        raise ValueError("Введите корректный email.")
    if len(password) < 10 or not re.search(r"[A-Za-zА-Яа-я]", password) or not re.search(r"\d", password):
        raise ValueError("Пароль должен содержать не менее 10 символов, буквы и цифры.")


def validate_phone(phone: str) -> None:
    if not PHONE_RE.fullmatch(phone.strip()):
        raise ValueError("Введите корректный номер телефона.")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False

