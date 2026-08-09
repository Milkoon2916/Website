"""
실제 데이터베이스 테이블 정의.
쉽게 말하면: "선생님 정보를 저장할 서랍"을 여기서 진짜로 만듦.

지금은 teachers(선생님 계정)만 우선 구현. 단어장/학생/지문/결과 테이블은
인증 흐름이 실제로 동작하는 걸 확인한 다음 순서대로 추가하면 됨.
"""
import os
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

# 로컬 개발: 프로젝트 폴더에 app.db 파일 하나로 저장됨
# Render 배포: DATABASE_URL 환경변수로 영구 디스크 경로(예: sqlite:////app/data/app.db)를 지정해야
#   재배포할 때마다 데이터가 사라지지 않음 (render.yaml의 disk 설정과 짝을 이룸)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class TeacherModel(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    pin_hash = Column(String, nullable=False)
    gemini_api_key_encrypted = Column(String, nullable=True)
    gemini_model = Column(String, default="gemini-3-flash")
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 단어장 ----------
# 제한: 선생님 1명 기준 word_lists(단어장 폴더) 최대 100개, words(단어) 총 최대 5000개, students 최대 100개
# 실제 개수 검사는 db.py에서 저장 직전에 함 (여기 모델에는 제약을 걸지 않음 — DB 제약보다
# "정원이 다 찼어요" 같은 안내 메시지를 보여주는 게 더 친절해서 애플리케이션 레벨에서 체크)

class WordListModel(Base):
    __tablename__ = "word_lists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    words = relationship("WordModel", back_populates="word_list", cascade="all, delete-orphan")


class WordModel(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    list_id = Column(Integer, ForeignKey("word_lists.id"), nullable=False)
    english = Column(String, nullable=False)
    korean = Column(String, nullable=False)
    example = Column(String, nullable=True)

    word_list = relationship("WordListModel", back_populates="words")


class StudentModel(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    name = Column(String, nullable=False)
    access_code = Column(String, unique=True, nullable=False)  # 학생이 링크에 쓰는 코드
    class_group = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class QuizResultModel(Base):
    __tablename__ = "quiz_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    list_id = Column(Integer, ForeignKey("word_lists.id"), nullable=False)
    score = Column(Integer, nullable=False)
    detail = Column(String, nullable=True)  # JSON 문자열 (문항별 정오답 등)
    submitted_at = Column(DateTime, default=datetime.utcnow)


# ---------- 지문분석 / 워크북 / OX 공용 ----------
class PassageModel(Base):
    __tablename__ = "passages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    title = Column(String, nullable=True)
    raw_text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MaterialModel(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    passage_id = Column(Integer, ForeignKey("passages.id"), nullable=False)
    type = Column(String, nullable=False)  # "analysis" / "workbook" / "ox"
    content = Column(String, nullable=False)  # Gemini 응답 JSON을 문자열로 저장
    pdf_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """서버 처음 시작할 때 한 번 실행 — 테이블이 없으면 만들어줌."""
    Base.metadata.create_all(bind=engine)
