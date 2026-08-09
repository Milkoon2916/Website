"""
지문분석 / 워크북 / OX 생성 라우트.
로그인한 선생님만 접근 가능, 본인이 등록한 개인 Gemini 키로 서버가 대신 호출함.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import get_current_teacher_id
from .db import get_db
from .llm import call_gemini_json
from .pdf_render import render_analysis_pdf, render_ox_pdf, render_workbook_pdf
from .prompts import (
    ANALYSIS_MODEL,
    OX_MODEL,
    OX_SYSTEM_PROMPT,
    WORKBOOK_MODEL,
    WORKBOOK_SYSTEM_PROMPT,
    build_analysis_prompt,
    build_analysis_user_message,
    build_ox_user_message,
    build_workbook_user_message,
)

router = APIRouter(prefix="/api", tags=["generate"])


class GenerateRequest(BaseModel):
    passage_text: str
    title: str | None = None
    target_grammar: str | None = None  # 지문분석 전용, 나머지는 무시됨


async def _get_teacher_gemini(teacher_id: int, db):
    teacher = db.get_teacher(teacher_id)
    if not teacher or not teacher.gemini_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Gemini API 키가 등록되어 있지 않아요. 먼저 'AI 키 설정'에서 등록해주세요.")
    from .auth import decrypt_api_key
    return decrypt_api_key(teacher.gemini_api_key_encrypted), teacher.gemini_model


@router.post("/passage-analysis")
async def generate_analysis(
    body: GenerateRequest,
    teacher_id: int = Depends(get_current_teacher_id),
    db=Depends(get_db),
):
    api_key, model = await _get_teacher_gemini(teacher_id, db)
    passage = db.create_passage(teacher_id, body.passage_text, body.title)

    system_prompt = build_analysis_prompt()
    user_message = build_analysis_user_message(body.passage_text, body.target_grammar)
    result = await call_gemini_json(api_key, model or ANALYSIS_MODEL, system_prompt, user_message)

    material = db.create_material(passage.id, "analysis", json.dumps(result, ensure_ascii=False))
    return {"passage_id": passage.id, "material_id": material.id, "result": result}


@router.post("/workbook")
async def generate_workbook(
    body: GenerateRequest,
    teacher_id: int = Depends(get_current_teacher_id),
    db=Depends(get_db),
):
    api_key, model = await _get_teacher_gemini(teacher_id, db)
    passage = db.create_passage(teacher_id, body.passage_text, body.title)

    user_message = build_workbook_user_message(body.passage_text)
    result = await call_gemini_json(api_key, model or WORKBOOK_MODEL, WORKBOOK_SYSTEM_PROMPT, user_message)

    material = db.create_material(passage.id, "workbook", json.dumps(result, ensure_ascii=False))
    return {"passage_id": passage.id, "material_id": material.id, "result": result}


@router.post("/ox")
async def generate_ox(
    body: GenerateRequest,
    teacher_id: int = Depends(get_current_teacher_id),
    db=Depends(get_db),
):
    api_key, model = await _get_teacher_gemini(teacher_id, db)
    passage = db.create_passage(teacher_id, body.passage_text, body.title)

    user_message = build_ox_user_message(body.passage_text)
    result = await call_gemini_json(api_key, model or OX_MODEL, OX_SYSTEM_PROMPT, user_message)

    material = db.create_material(passage.id, "ox", json.dumps(result, ensure_ascii=False))
    return {"passage_id": passage.id, "material_id": material.id, "result": result}


@router.get("/passages/{passage_id}/materials")
def get_materials(passage_id: int, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    passage = db.get_passage(passage_id, teacher_id)
    if not passage:
        raise HTTPException(status_code=404, detail="지문을 찾을 수 없어요.")
    rows = db.list_materials(passage_id)
    return [{"id": r.id, "type": r.type, "content": json.loads(r.content), "pdf_path": r.pdf_path} for r in rows]


@router.get("/materials/{material_id}/pdf")
def download_material_pdf(material_id: int, teacher_id: int = Depends(get_current_teacher_id), db=Depends(get_db)):
    material = db.get_material(material_id, teacher_id)
    if not material:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없어요.")

    content = json.loads(material.content)
    passage = db.get_passage(material.passage_id, teacher_id)
    title = (passage.title if passage else None) or "학습자료"

    if material.type == "analysis":
        pdf_bytes = render_analysis_pdf(content, title=title)
    elif material.type == "workbook":
        pdf_bytes = render_workbook_pdf(content, title=title)
    elif material.type == "ox":
        pdf_bytes = render_ox_pdf(content, title=title)
    else:
        raise HTTPException(status_code=400, detail="이 자료 유형은 아직 PDF 다운로드를 지원하지 않아요.")

    filename = f"{title}_{material.type}.pdf"
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"material.pdf\"; filename*=UTF-8''{encoded_filename}"},
    )
