"""
DB 접근 담당.
routes_auth.py / routes_words.py 에서 부르는 함수들을 실제 데이터베이스(SQLite)에
대고 동작하게 구현. 단어장/학생 관련 함수는 저장 직전에 정원(limits.py)을 체크함.
"""
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException

from .limits import (
    MAX_STUDENTS_PER_TEACHER,
    MAX_WORD_LISTS_PER_TEACHER,
    MAX_WORDS_PER_TEACHER,
)
from .models import (
    MaterialModel,
    PassageModel,
    QuizResultModel,
    SessionLocal,
    StudentModel,
    TeacherModel,
    WordListModel,
    WordModel,
)


@dataclass
class Teacher:
    id: int
    name: str
    pin_hash: str
    gemini_api_key_encrypted: str | None
    gemini_model: str


def _to_dataclass(row: TeacherModel) -> Teacher:
    return Teacher(
        id=row.id,
        name=row.name,
        pin_hash=row.pin_hash,
        gemini_api_key_encrypted=row.gemini_api_key_encrypted,
        gemini_model=row.gemini_model,
    )


class RealDB:
    def __init__(self, session):
        self.session = session

    # ---------- 선생님 ----------
    def get_teacher_by_name(self, name: str) -> Teacher | None:
        row = self.session.query(TeacherModel).filter_by(name=name).first()
        return _to_dataclass(row) if row else None

    def get_teacher(self, teacher_id: int) -> Teacher | None:
        row = self.session.get(TeacherModel, teacher_id)
        return _to_dataclass(row) if row else None

    def create_teacher(self, name: str, pin_hash: str, gemini_api_key_encrypted: str, gemini_model: str) -> Teacher:
        row = TeacherModel(
            name=name,
            pin_hash=pin_hash,
            gemini_api_key_encrypted=gemini_api_key_encrypted,
            gemini_model=gemini_model,
            created_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _to_dataclass(row)

    def update_teacher_gemini(self, teacher_id: int, gemini_api_key_encrypted: str, gemini_model: str | None):
        row = self.session.get(TeacherModel, teacher_id)
        row.gemini_api_key_encrypted = gemini_api_key_encrypted
        if gemini_model:
            row.gemini_model = gemini_model
        self.session.commit()

    # ---------- 단어장(폴더) ----------
    def count_word_lists(self, teacher_id: int) -> int:
        return self.session.query(WordListModel).filter_by(teacher_id=teacher_id).count()

    def create_word_list(self, teacher_id: int, title: str) -> WordListModel:
        if self.count_word_lists(teacher_id) >= MAX_WORD_LISTS_PER_TEACHER:
            raise HTTPException(
                status_code=400,
                detail=f"단어장은 최대 {MAX_WORD_LISTS_PER_TEACHER}개까지 만들 수 있어요. 안 쓰는 단어장을 정리해주세요.",
            )
        row = WordListModel(teacher_id=teacher_id, title=title, created_at=datetime.utcnow())
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_word_lists(self, teacher_id: int):
        return self.session.query(WordListModel).filter_by(teacher_id=teacher_id).all()

    def get_word_list(self, list_id: int, teacher_id: int) -> WordListModel | None:
        row = self.session.get(WordListModel, list_id)
        if row and row.teacher_id == teacher_id:
            return row
        return None

    def delete_word_list(self, list_id: int, teacher_id: int):
        row = self.get_word_list(list_id, teacher_id)
        if row:
            self.session.delete(row)  # cascade로 소속 단어도 같이 삭제됨
            self.session.commit()

    # ---------- 단어 ----------
    def count_words(self, teacher_id: int) -> int:
        return (
            self.session.query(WordModel)
            .join(WordListModel, WordModel.list_id == WordListModel.id)
            .filter(WordListModel.teacher_id == teacher_id)
            .count()
        )

    def add_word(self, list_id: int, teacher_id: int, english: str, korean: str, example: str | None = None) -> WordModel:
        word_list = self.get_word_list(list_id, teacher_id)
        if not word_list:
            raise HTTPException(status_code=404, detail="단어장을 찾을 수 없어요.")
        if self.count_words(teacher_id) >= MAX_WORDS_PER_TEACHER:
            raise HTTPException(
                status_code=400,
                detail=f"단어는 전체 최대 {MAX_WORDS_PER_TEACHER}개까지 저장할 수 있어요. 안 쓰는 단어를 정리해주세요.",
            )
        row = WordModel(list_id=list_id, english=english, korean=korean, example=example)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_words(self, list_id: int, teacher_id: int):
        word_list = self.get_word_list(list_id, teacher_id)
        if not word_list:
            raise HTTPException(status_code=404, detail="단어장을 찾을 수 없어요.")
        return self.session.query(WordModel).filter_by(list_id=list_id).all()

    def delete_word(self, word_id: int, teacher_id: int):
        row = self.session.get(WordModel, word_id)
        if row and row.word_list.teacher_id == teacher_id:
            self.session.delete(row)
            self.session.commit()

    # ---------- 학생 ----------
    def count_students(self, teacher_id: int) -> int:
        return self.session.query(StudentModel).filter_by(teacher_id=teacher_id).count()

    def create_student(self, teacher_id: int, name: str, access_code: str, class_group: str | None = None) -> StudentModel:
        if self.count_students(teacher_id) >= MAX_STUDENTS_PER_TEACHER:
            raise HTTPException(
                status_code=400,
                detail=f"학생 등록은 최대 {MAX_STUDENTS_PER_TEACHER}명까지 가능해요. 졸업생/미사용 학생을 정리해주세요.",
            )
        existing = self.session.query(StudentModel).filter_by(access_code=access_code).first()
        if existing:
            raise HTTPException(status_code=409, detail="이미 사용 중인 학생 코드예요. 다른 코드를 입력해주세요.")
        row = StudentModel(
            teacher_id=teacher_id, name=name, access_code=access_code, class_group=class_group,
            created_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_students(self, teacher_id: int):
        return self.session.query(StudentModel).filter_by(teacher_id=teacher_id).all()

    def get_student_by_code(self, access_code: str) -> StudentModel | None:
        return self.session.query(StudentModel).filter_by(access_code=access_code).first()

    def delete_student(self, student_id: int, teacher_id: int):
        row = self.session.get(StudentModel, student_id)
        if row and row.teacher_id == teacher_id:
            self.session.delete(row)
            self.session.commit()

    # ---------- 퀴즈 결과 (학생이 코드만으로 씀, 로그인 불필요) ----------
    def create_quiz_result(self, student_id: int, list_id: int, score: int, detail: str | None = None) -> QuizResultModel:
        row = QuizResultModel(
            student_id=student_id, list_id=list_id, score=score, detail=detail,
            submitted_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_quiz_results(self, teacher_id: int):
        """선생님이 '결과 보기'에서 자기 학생들 결과 전체를 조회할 때 씀."""
        return (
            self.session.query(QuizResultModel)
            .join(StudentModel, QuizResultModel.student_id == StudentModel.id)
            .filter(StudentModel.teacher_id == teacher_id)
            .all()
        )

    # ---------- 지문 (지문분석/워크북/OX 공용) ----------
    def create_passage(self, teacher_id: int, raw_text: str, title: str | None = None) -> PassageModel:
        row = PassageModel(teacher_id=teacher_id, title=title, raw_text=raw_text, created_at=datetime.utcnow())
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def get_passage(self, passage_id: int, teacher_id: int) -> PassageModel | None:
        row = self.session.get(PassageModel, passage_id)
        if row and row.teacher_id == teacher_id:
            return row
        return None

    def list_passages(self, teacher_id: int):
        return self.session.query(PassageModel).filter_by(teacher_id=teacher_id).all()

    # ---------- 생성물 (지문분석/워크북/OX 결과) ----------
    def create_material(self, passage_id: int, type_: str, content: str, pdf_path: str | None = None) -> MaterialModel:
        row = MaterialModel(passage_id=passage_id, type=type_, content=content, pdf_path=pdf_path, created_at=datetime.utcnow())
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_materials(self, passage_id: int):
        return self.session.query(MaterialModel).filter_by(passage_id=passage_id).all()

    def get_material(self, material_id: int, teacher_id: int) -> MaterialModel | None:
        row = self.session.get(MaterialModel, material_id)
        if not row:
            return None
        passage = self.session.get(PassageModel, row.passage_id)
        if not passage or passage.teacher_id != teacher_id:
            return None
        return row

    def get_material(self, material_id: int, teacher_id: int) -> MaterialModel | None:
        row = self.session.get(MaterialModel, material_id)
        if not row:
            return None
        passage = self.session.get(PassageModel, row.passage_id)
        if not passage or passage.teacher_id != teacher_id:
            return None
        return row


def get_db():
    """FastAPI가 요청 하나당 DB 연결을 열었다가, 끝나면 자동으로 닫아줌."""
    session = SessionLocal()
    try:
        yield RealDB(session)
    finally:
        session.close()
