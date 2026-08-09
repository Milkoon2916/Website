"""
선생님 인증 라우트: 회원가입 / 로그인 / 로그아웃 / 내 정보(Gemini 키·모델) 수정
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from .auth import (
    COOKIE_NAME,
    create_session_token,
    decrypt_api_key,
    encrypt_api_key,
    get_current_teacher_id,
    hash_pin,
    verify_pin,
)
from .db import get_db  # 실제 DB 세션 의존성으로 교체 (SQLAlchemy 등)

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_KWARGS = dict(
    httponly=True,
    secure=True,       # 로컬 http 테스트 시엔 False로 잠깐 바꿔도 됨
    samesite="lax",
    max_age=60 * 60 * 24 * 30,  # 30일
)


class SignupRequest(BaseModel):
    name: str
    pin: str
    gemini_api_key: str
    gemini_model: str = "gemini-3-flash"


class LoginRequest(BaseModel):
    name: str
    pin: str


class UpdateKeyRequest(BaseModel):
    gemini_api_key: str
    gemini_model: str | None = None


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, response: Response, db=Depends(get_db)):
    existing = db.get_teacher_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail="이미 등록된 이름이에요. 다른 이름을 쓰거나 로그인해주세요.")

    teacher = db.create_teacher(
        name=body.name,
        pin_hash=hash_pin(body.pin),
        gemini_api_key_encrypted=encrypt_api_key(body.gemini_api_key),
        gemini_model=body.gemini_model,
    )

    token = create_session_token(teacher.id)
    response.set_cookie(COOKIE_NAME, token, **COOKIE_KWARGS)
    return {"teacher_id": teacher.id, "name": teacher.name}


@router.post("/login")
def login(body: LoginRequest, response: Response, db=Depends(get_db)):
    teacher = db.get_teacher_by_name(body.name)
    if not teacher or not verify_pin(body.pin, teacher.pin_hash):
        raise HTTPException(status_code=401, detail="이름 또는 PIN이 올바르지 않아요.")

    token = create_session_token(teacher.id)
    response.set_cookie(COOKIE_NAME, token, **COOKIE_KWARGS)
    return {"teacher_id": teacher.id, "name": teacher.name}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    teacher = db.get_teacher(teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="선생님 정보를 찾을 수 없어요.")
    # 키 원문은 절대 응답에 포함하지 않고, 마스킹된 형태만 보여줌
    masked = teacher.gemini_api_key_encrypted and "설정됨"
    return {"name": teacher.name, "gemini_model": teacher.gemini_model, "gemini_api_key": masked}


@router.put("/me/gemini")
def update_gemini_key(
    body: UpdateKeyRequest,
    teacher_id: int = Depends(get_current_teacher_id),
    db=Depends(get_db),
):
    db.update_teacher_gemini(
        teacher_id,
        gemini_api_key_encrypted=encrypt_api_key(body.gemini_api_key),
        gemini_model=body.gemini_model,
    )
    return {"ok": True}


# ---------- 다른 라우트(지문분석/워크북/OX/단어장)에서 이렇게 씀 ----------
def get_teacher_gemini_key(teacher_id: int, db) -> str:
    """Gemini 호출 직전에 이걸로 복호화해서 씀. 절대 클라이언트로 리턴하지 말 것."""
    teacher = db.get_teacher(teacher_id)
    if not teacher or not teacher.gemini_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Gemini API 키가 설정되어 있지 않아요. 먼저 등록해주세요.")
    return decrypt_api_key(teacher.gemini_api_key_encrypted)
