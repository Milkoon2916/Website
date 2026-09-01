from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import init_db
from .routes_auth import router as auth_router
from .routes_generate import router as generate_router
from .routes_public import router as public_router
from .routes_words import router as words_router

app = FastAPI(title="영어 학습자료 제작소 (통합)")


@app.on_event("startup")
def on_startup():
    # 서버가 켜질 때 필요한 테이블이 없으면 자동으로 만들어줌
    init_db()


app.include_router(auth_router)     # 선생님 회원가입/로그인
app.include_router(words_router)    # 단어장/학생/결과 관리 (로그인 필요)
app.include_router(generate_router)  # 지문분석/워크북/OX 생성 (로그인 필요)
app.include_router(public_router)   # 학생용 (링크+코드, 로그인 불필요)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def homepage():
    return FileResponse("static/index.html")


@app.get("/vocabulary/")
def vocabulary_page():
    return FileResponse("static/vocabulary.html")


@app.get("/quiz.html")
def quiz_page():
    return FileResponse("static/quiz.html")


@app.get("/generate/")
def generate_page():
    # 지문분석/워크북/OX/목표어법 문제는 전부 여기 통합생성 화면 하나로 만듦.
    # (예전에는 /passage-analyzer/, /workbook/, /comprehension/, /grammar/ 로
    #  각각 따로 페이지가 있었지만, 통합생성이 4개를 다 커버해서 중복이라 정리함)
    return FileResponse("static/generate.html")

# 학생용 라우트(/quiz/{access_code} 등)는 별도 라우터로 분리해서 인증 없이 공개.
