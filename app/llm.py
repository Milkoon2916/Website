"""
Gemini API 호출 담당.
선생님이 등록한 개인 키(복호화된 상태로 db.get_teacher_gemini_key에서 넘어옴)로
서버가 직접 Gemini를 호출함 (예전처럼 브라우저가 직접 호출하는 BYOK 방식이 아니라,
키를 서버 DB에 저장하기로 했으므로 서버가 대신 호출하는 구조로 바뀜).
"""
import asyncio
import json
import random
import re

import httpx
from fastapi import HTTPException

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 503(모델 과부하)/429(요청 한도)는 순간적인 상태일 때가 많아서, 바로 에러를 던지지 않고
# 짧게 재시도한다. 지문분석에서 503이 자주 보고됐던 것도 대부분 이 케이스였음.
# generate-all처럼 여러 자료를 동시에 요청할 때는 각 호출의 재시도 타이밍이 겹치면
# 다시 한꺼번에 부딪힐 수 있어서, 대기 시간에 약간의 무작위 지터를 더해 서로 어긋나게 함.
_RETRY_STATUS_CODES = {429, 503}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = [1.5, 3.5]  # 1차 실패 후 1.5초, 2차 실패 후 3.5초 대기 (+ 지터)

# "유효한 JSON을 반환하지 않음" / 잦은 실패의 진짜 원인 (2026-08 확인):
# Gemini 3.x 계열(3.5/3.6/3.7-flash 등)은 기본적으로 "thinking"이 켜져 있고,
# thinkingConfig를 안 주면 모델이 알아서 thinking 토큰을 쓰는데, 이 thinking 토큰이
# maxOutputTokens 예산을 실제 답변(JSON)과 "공유"함. 그래서 maxOutputTokens을
# 16000~26000으로 넉넉히 잡아도, 그중 상당 부분을 thinking이 먼저 써버리면 정작
# JSON 답변이 중간에 잘리는(finishReason=MAX_TOKENS) 일이 자주 생김.
# -> 이 작업들은 복잡한 추론이 필요한 게 아니라 정해진 스키마로 정보를 뽑아내는
#    작업이라 thinking이 사실상 불필요함. thinkingConfig.thinkingLevel="low"로 낮춰서
#    thinking에 쓰는 토큰을 최소화하고, maxOutputTokens 대부분을 실제 JSON 출력에
#    쓰도록 함(할당량/속도도 함께 개선됨).
# 그 외 두 가지 보조 처리:
# 1) 그래도 잘렸으면(finishReason=MAX_TOKENS) 토큰 한도를 올려서 재시도.
# 2) JSON 강제 모드를 쓰더라도 아주 가끔 ```json 코드펜스나 트레일링 콤마가 섞여 나옴.
#    -> 파싱 전에 가볍게 정리(repair)한 뒤 재시도.


def _repair_and_parse(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 배열/객체 닫기 직전의 트레일링 콤마 제거 후 재시도
    repaired = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


async def call_gemini_json(
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    max_output_tokens: int = 16000,
) -> dict:
    """Gemini를 호출하고, 응답을 JSON으로 파싱해서 dict로 돌려줌.
    JSON 강제 출력 모드(response_mime_type)를 써서 마크다운 펜스 등이 안 섞이게 함.

    지문분석에서 502/503이 자주 나던 원인:
    1) maxOutputTokens가 60000으로 지나치게 커서 응답 생성이 오래 걸렸고,
       Render 등 배포 플랫폼의 프록시가 자체 타임아웃(보통 ~100초)으로 연결을
       먼저 끊어버려 우리 앱의 에러 처리가 실행되기도 전에 502/503이 발생했음.
       -> 기본값을 16000으로 낮춤(지문 분석 결과 크기면 충분히 여유 있음).
    2) httpx 타임아웃 시(ReadTimeout 등) 예외를 잡지 않아서 처리되지 않은 예외가
       그대로 터져 나갔음 -> 아래에서 명시적으로 잡아서 504로 변환.
    3) Gemini가 "모델 과부하(503)"를 순간적으로 반환하는 경우가 꽤 있는데, 예전엔
       바로 에러를 사용자에게 보여줬음 -> 짧은 대기 후 최대 3회까지 자동 재시도하도록 변경.
    4) 목표어법 문제처럼 스키마가 복잡한 경우 응답이 중간에 잘리거나(MAX_TOKENS) 코드펜스/
       트레일링 콤마가 섞여 "유효한 JSON이 아님" 에러가 났음 -> 잘렸으면 토큰 한도를 올려서
       재시도하고, 그 외의 경우도 경미한 포맷 오류는 자동으로 복구해서 재시도함.
    """
    url = GEMINI_ENDPOINT.format(model=model)
    current_max_tokens = max_output_tokens

    last_error_detail = "Gemini가 유효한 JSON을 반환하지 않았어요. 다시 시도해주세요."

    for attempt in range(_MAX_ATTEMPTS):
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "maxOutputTokens": current_max_tokens,
                "temperature": 0.5,
                # Gemini 3.x thinking이 maxOutputTokens를 나눠 쓰는 문제 방지 (위 주석 참고)
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(url, params={"key": api_key}, json=payload)
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Gemini 응답이 90초 안에 오지 않았어요. 지문이 너무 길면 나눠서 시도해보세요.",
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Gemini에 연결하지 못했어요: {e}")

        if resp.status_code in _RETRY_STATUS_CODES and attempt < _MAX_ATTEMPTS - 1:
            await asyncio.sleep(_BACKOFF_SECONDS[attempt] + random.uniform(0, 1.0))
            continue
        if resp.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Gemini 요청 한도(무료 등급)에 걸렸어요. 잠시 후 다시 시도해주세요.",
            )
        if resp.status_code == 401 or resp.status_code == 403:
            raise HTTPException(status_code=400, detail="등록된 Gemini API 키가 유효하지 않아요. 키 설정을 다시 확인해주세요.")
        if resp.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail="Gemini 서버가 일시적으로 과부하 상태예요 (재시도 3회 실패). 잠시 후 다시 시도해주세요.",
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Gemini 호출 중 오류가 발생했어요 ({resp.status_code}).")

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            # candidates가 아예 없는 경우 대부분 안전 필터에 막힌 것 (promptFeedback.blockReason)
            block_reason = (data.get("promptFeedback") or {}).get("blockReason")
            if block_reason:
                raise HTTPException(
                    status_code=422,
                    detail=f"Gemini가 안전 정책({block_reason}) 때문에 이 지문을 처리하지 못했어요. 지문 내용을 확인해주세요.",
                )
            raise HTTPException(status_code=502, detail="Gemini 응답 형식이 예상과 달라요.")

        candidate = candidates[0]
        try:
            text = candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            # 후보는 있는데 본문이 없는 경우 -> 개별 후보가 안전 필터 등으로 막힌 케이스
            reason = candidate.get("finishReason", "알 수 없는 이유")
            raise HTTPException(
                status_code=422,
                detail=f"Gemini가 답변을 생성하지 못했어요 ({reason}). 지문이나 목표 어법 입력을 확인해주세요.",
            )

        finish_reason = candidate.get("finishReason")
        parsed = _repair_and_parse(text)

        if parsed is not None:
            return parsed

        # 파싱 실패: 토큰 한도 때문에 잘렸으면 한도를 올려서, 아니면 그대로 재시도
        if finish_reason == "MAX_TOKENS":
            current_max_tokens = min(current_max_tokens * 2, 48000)
            last_error_detail = "Gemini 응답이 토큰 한도로 잘려서 JSON이 완성되지 않았어요."
        else:
            last_error_detail = "Gemini가 유효한 JSON을 반환하지 않았어요."

        if attempt < _MAX_ATTEMPTS - 1:
            continue
        raise HTTPException(status_code=502, detail=f"{last_error_detail} 다시 시도해주세요.")

    raise HTTPException(status_code=502, detail=f"{last_error_detail} 다시 시도해주세요.")
