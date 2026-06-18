"""Tenant 시크릿 대칭 암호화 (deep module).

Tenant가 입력한 provider API 키를 저장 시 암호화한다. 키는 플랫폼 SECRET_KEY에서
파생한 Fernet 키로 보호하며, API 응답엔 평문을 절대 반환하지 않는다(write-only).
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    return _fernet().decrypt(ciphertext.encode()).decode()
