"""
인증 유틸리티
- PIN 해시/검증 (bcrypt)
- JWT 발급/검증 (httpOnly 쿠키에 담아 사용)
- 선생님 개인 Gemini API 키 암호화/복호화 (Fernet 대칭키)
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, HTTPException, status

# ---------- 환경변수 ----------
# 운영 배포 시 반드시 .env 또는 Render 환경변수로 채워넣을 것.
# 둘 다 없으면 서버 시작할 때마다 값이 바뀌어서 기존 세션/암호화된 키가 깨지니 주의.
JWT_SECRET = os.environ["JWT_SECRET"]  # 예: openssl rand -hex 32 로 생성
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

FERNET_KEY = os.environ["FERNET_KEY"]  # 예: Fernet.generate_key() 로 생성한 값
fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

COOKIE_NAME = "session"


# ---------- PIN 해시 ----------
def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())


# ---------- Gemini API 키 암호화 ----------
def encrypt_api_key(raw_key: str) -> str:
    return fernet.encrypt(raw_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    return fernet.decrypt(encrypted_key.encode()).decode()


# ---------- JWT ----------
def create_session_token(teacher_id: int) -> str:
    payload = {
        "teacher_id": teacher_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="세션이 만료됐어요. 다시 로그인해주세요.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 세션이에요.")
    return payload["teacher_id"]


# ---------- FastAPI 의존성: 로그인한 선생님만 통과 ----------
def get_current_teacher_id(session: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> int:
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요해요.")
    return decode_session_token(session)
