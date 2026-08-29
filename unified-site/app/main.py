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
    return FileResponse("static/generate.html")


@app.get("/passage-analyzer/")
def passage_analyzer_page():
    return FileResponse("static/passage-analyzer.html")


@app.get("/workbook/")
def workbook_page():
    return FileResponse("static/workbook.html")


@app.get("/comprehension/")
def comprehension_page():
    return FileResponse("static/comprehension.html")


@app.get("/grammar/")
def grammar_page():
    return FileResponse("static/grammar.html")

# 이후 여기에 기존 워크북/지문분석/OX 라우터, 그리고 새로 옮길 단어장 라우터를
# 각각 Depends(get_current_teacher_id)로 보호해서 include_router 하면 됨.
# 학생용 라우트(/quiz/{access_code} 등)는 별도 라우터로 분리해서 인증 없이 공개.
