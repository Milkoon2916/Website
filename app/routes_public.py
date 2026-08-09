"""
학생용 공개 라우트.
로그인 없이 접속 링크에 포함된 access_code만으로 동작함 (선생님 인증과 완전히 분리).
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .db import get_db
from fastapi import Depends

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/quiz/{access_code}/lists")
def get_available_lists(access_code: str, db=Depends(get_db)):
    """학생이 접속하면 자기 선생님이 만든 단어장 목록을 보여줌."""
    student = db.get_student_by_code(access_code)
    if not student:
        raise HTTPException(status_code=404, detail="학생 코드를 찾을 수 없어요. 선생님께 코드를 다시 확인해주세요.")
    lists = db.list_word_lists(student.teacher_id)
    return {
        "student_name": student.name,
        "word_lists": [{"id": w.id, "title": w.title} for w in lists],
    }


@router.get("/quiz/{access_code}/lists/{list_id}/words")
def get_quiz_words(access_code: str, list_id: int, db=Depends(get_db)):
    """특정 단어장의 단어 목록(퀴즈 문제용)을 줌."""
    student = db.get_student_by_code(access_code)
    if not student:
        raise HTTPException(status_code=404, detail="학생 코드를 찾을 수 없어요.")
    word_list = db.get_word_list(list_id, student.teacher_id)
    if not word_list:
        raise HTTPException(status_code=404, detail="단어장을 찾을 수 없어요.")
    words = db.list_words(list_id, student.teacher_id)
    return [{"id": w.id, "english": w.english, "korean": w.korean, "example": w.example} for w in words]


class ResultSubmit(BaseModel):
    list_id: int
    score: int
    detail: dict | None = None  # 문항별 정오답 등 자유 형식


@router.post("/quiz/{access_code}/results")
def submit_result(access_code: str, body: ResultSubmit, db=Depends(get_db)):
    """학생이 퀴즈를 마치고 결과를 제출. PIN 없이 코드만 맞으면 저장됨 (기존 방식과 동일)."""
    student = db.get_student_by_code(access_code)
    if not student:
        raise HTTPException(status_code=404, detail="학생 코드를 찾을 수 없어요.")
    word_list = db.get_word_list(body.list_id, student.teacher_id)
    if not word_list:
        raise HTTPException(status_code=404, detail="단어장을 찾을 수 없어요.")

    row = db.create_quiz_result(
        student_id=student.id,
        list_id=body.list_id,
        score=body.score,
        detail=json.dumps(body.detail, ensure_ascii=False) if body.detail else None,
    )
    return {"ok": True, "result_id": row.id}
