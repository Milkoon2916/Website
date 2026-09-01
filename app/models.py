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

# 로컬 개발: 프로젝트 폴더에 app.db 파일 하나로 저장됨(sqlite)
#
# Render 배포(무료 플랜): 무료 웹서비스는 영구 디스크를 지원하지 않아서, sqlite 파일로는
#   재배포/reactivate(=컨테이너 재생성)될 때마다 데이터가 통째로 사라짐. 이걸 무료로 피하려면
#   Neon/Supabase 같은 외부 무료 Postgres를 하나 만들고, 거기서 발급되는 연결 문자열을
#   DATABASE_URL 환경변수로 넣어주면 됨 (Render 유료 Starter+로 올려서 디스크를 쓰는 것도 대안).
#
# Neon/Supabase가 주는 연결 문자열은 보통 "postgres://"로 시작하는데, SQLAlchemy는
# "postgresql://"만 인식해서 그대로 넣으면 조용히 에러 나므로 여기서 자동 변환해줌.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# check_same_thread는 sqlite 전용 옵션이라, Postgres에 그대로 넘기면 연결 자체가 실패함.
# sqlite일 때만 붙이도록 분기.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# Postgres는 오래 안 쓰면 커넥션이 끊기는 경우가 있어서, 쓰기 전에 살아있는지 확인하는
# pool_pre_ping을 켜둠 (sqlite에는 영향 없음).
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class TeacherModel(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    pin_hash = Column(String, nullable=False)
    gemini_api_key_encrypted = Column(String, nullable=True)
    gemini_model = Column(String, default="gemini-3.7-flash")
    academy_name = Column(String, nullable=True)  # PDF 상단에 찍힐 학원 이름 (선택)
    academy_logo_data_url = Column(String, nullable=True)  # "data:image/png;base64,..." 형태로 통째로 저장 (선택)
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
    _run_light_migrations()


def _run_light_migrations():
    """create_all은 '없는 테이블'만 만들고, 이미 존재하는 테이블에 새로 추가된
    컬럼(예: academy_name, academy_logo_data_url)은 채워주지 않음. 이 프로젝트엔
    별도 마이그레이션 도구(alembic 등)가 없어서, 컬럼이 없으면 여기서 최소한으로
    ALTER TABLE 해줌 (sqlite/Postgres 둘 다 이 문법을 지원함)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_cols = {c["name"] for c in inspector.get_columns("teachers")}
    with engine.begin() as conn:
        if "academy_name" not in existing_cols:
            conn.execute(text("ALTER TABLE teachers ADD COLUMN academy_name VARCHAR"))
        if "academy_logo_data_url" not in existing_cols:
            conn.execute(text("ALTER TABLE teachers ADD COLUMN academy_logo_data_url TEXT"))
