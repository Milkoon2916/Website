"""
단어장(폴더) / 단어 / 학생 관리 라우트.
전부 로그인한 선생님(get_current_teacher_id)만 접근 가능하고,
본인 소속(teacher_id) 데이터만 보이고 수정 가능함.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import get_current_teacher_id
from .db import get_db

router = APIRouter(prefix="/api", tags=["words"])


# ---------- 단어장(폴더) ----------
class WordListCreate(BaseModel):
    title: str


@router.post("/word-lists")
def create_word_list(body: WordListCreate, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    row = db.create_word_list(teacher_id, body.title)
    return {"id": row.id, "title": row.title}


@router.get("/word-lists")
def list_word_lists(teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    rows = db.list_word_lists(teacher_id)
    return [{"id": r.id, "title": r.title} for r in rows]


@router.delete("/word-lists/{list_id}")
def delete_word_list(list_id: int, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    db.delete_word_list(list_id, teacher_id)
    return {"ok": True}


# ---------- 단어 ----------
class WordCreate(BaseModel):
    english: str
    korean: str
    example: str | None = None


@router.post("/word-lists/{list_id}/words")
def add_word(list_id: int, body: WordCreate, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    row = db.add_word(list_id, teacher_id, body.english, body.korean, body.example)
    return {"id": row.id, "english": row.english, "korean": row.korean, "example": row.example}


@router.get("/word-lists/{list_id}/words")
def list_words(list_id: int, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    rows = db.list_words(list_id, teacher_id)
    return [{"id": r.id, "english": r.english, "korean": r.korean, "example": r.example} for r in rows]


@router.delete("/words/{word_id}")
def delete_word(word_id: int, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    db.delete_word(word_id, teacher_id)
    return {"ok": True}


# ---------- 학생 ----------
class StudentCreate(BaseModel):
    name: str
    access_code: str
    class_group: str | None = None


@router.post("/students")
def create_student(body: StudentCreate, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    row = db.create_student(teacher_id, body.name, body.access_code, body.class_group)
    return {"id": row.id, "name": row.name, "access_code": row.access_code}


@router.get("/students")
def list_students(teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    rows = db.list_students(teacher_id)
    return [{"id": r.id, "name": r.name, "access_code": r.access_code, "class_group": r.class_group} for r in rows]


@router.delete("/students/{student_id}")
def delete_student(student_id: int, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    db.delete_student(student_id, teacher_id)
    return {"ok": True}


# ---------- 결과 보기 (선생님이 자기 학생들 퀴즈 결과 확인) ----------
@router.get("/results")
def list_results(teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    rows = db.list_quiz_results(teacher_id)
    return [
        {
            "id": r.id,
            "student_id": r.student_id,
            "list_id": r.list_id,
            "score": r.score,
            "detail": r.detail,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        }
        for r in rows
    ]
