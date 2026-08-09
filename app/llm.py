"""
Gemini API 호출 담당.
선생님이 등록한 개인 키(복호화된 상태로 db.get_teacher_gemini_key에서 넘어옴)로
서버가 직접 Gemini를 호출함 (예전처럼 브라우저가 직접 호출하는 BYOK 방식이 아니라,
키를 서버 DB에 저장하기로 했으므로 서버가 대신 호출하는 구조로 바뀜).
"""
import json

import httpx
from fastapi import HTTPException

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


async def call_gemini_json(api_key: str, model: str, system_prompt: str, user_message: str) -> dict:
    """Gemini를 호출하고, 응답을 JSON으로 파싱해서 dict로 돌려줌.
    JSON 강제 출력 모드(response_mime_type)를 써서 마크다운 펜스 등이 안 섞이게 함."""
    url = GEMINI_ENDPOINT.format(model=model)
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "maxOutputTokens": 60000,
        },
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, params={"key": api_key}, json=payload)

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Gemini 요청 한도(무료 등급)에 걸렸어요. 잠시 후 다시 시도해주세요.",
        )
    if resp.status_code == 401 or resp.status_code == 403:
        raise HTTPException(status_code=400, detail="등록된 Gemini API 키가 유효하지 않아요. 키 설정을 다시 확인해주세요.")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Gemini 호출 중 오류가 발생했어요 ({resp.status_code}).")

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Gemini 응답 형식이 예상과 달라요.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Gemini가 유효한 JSON을 반환하지 않았어요. 다시 시도해주세요.")
