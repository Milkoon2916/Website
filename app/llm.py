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
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = [1.5, 3.5, 6.0]  # 1차 실패 후 1.5초, 2차 3.5초, 3차 6초 대기 (+ 지터)

# 워크북처럼 스키마가 크고(출력 토큰이 많이 필요) 처리 시간이 긴 요청은 모델이 조금만
# 부하가 걸려도 503(UNAVAILABLE)을 유독 자주 돌려준다는 보고가 있었음. 그래서 같은 모델로만
# 계속 재시도하는 대신, 재시도를 다 써도 503이 반복되면 마지막으로 더 오래된(=사용자가 몰리지
# 않아 여유가 있는) 안정 모델로 한 번 더 자동 전환해서 시도한다.
# (설정 화면에도 "gemini-2.5-flash (구버전, 안정적)"으로 이미 안내되고 있는 모델.)
FALLBACK_MODEL = "gemini-2.5-flash"

# "유효한 JSON을 반환하지 않음" 에러(주로 목표어법 문제처럼 문제 유형이 5가지로 섞여있는
# 복잡한 스키마에서 발생) — 아래 두 가지가 실제 원인이었음:
# 1) 응답이 도중에 잘림(finishReason=MAX_TOKENS): 출력 토큰 한도를 넉넉히 못 잡으면
#    JSON이 중간에 끊겨서 파싱이 실패함. -> 아래에서 finishReason을 확인해서 잘렸으면
#    바로 재시도(+토큰 한도 상향)하도록 처리.
# 2) JSON 강제 모드를 쓰더라도 아주 가끔 ```json 코드펜스나 트레일링 콤마가 섞여 나옴.
#    -> 파싱 전에 가볍게 정리(repair)한 뒤 재시도.


def _extract_error_detail(resp: httpx.Response) -> str:
    """Gemini가 4xx/5xx를 반환했을 때, 응답 바디의 error.message를 최대한 꺼내서 보여준다.
    예전엔 상태 코드만 보여줘서 원인을 전혀 알 수 없었음
    (흔한 원인: 등록된 모델명이 더 이상 존재하지 않음/오타, 잘못된 파라미터 값 등)."""
    try:
        body = resp.json()
        msg = body.get("error", {}).get("message")
        if msg:
            return str(msg)
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text[:300] if text else f"상태 코드 {resp.status_code}"


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


async def _call_gemini_once(
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    max_output_tokens: int,
) -> dict:
    """한 모델을 대상으로 재시도 루프를 돌며 호출. 실패하면 HTTPException을 던진다."""
    url = GEMINI_ENDPOINT.format(model=model)
    current_max_tokens = max_output_tokens

    last_error_detail = "Gemini가 유효한 JSON을 반환하지 않았어요. 다시 시도해주세요."

    for attempt in range(_MAX_ATTEMPTS):
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                # 카멜케이스로 통일 (구글 공식 문서/최신 예제 기준). 스네이크케이스(response_mime_type)도
                # 대개 파싱되긴 하지만, maxOutputTokens 등 나머지 필드와 표기가 섞여 있던 게
                # 잠재적 혼란/오류 요인이었어서 정리함.
                "responseMimeType": "application/json",
                "maxOutputTokens": current_max_tokens,
                "temperature": 0.5,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                # 키를 ?key= 쿼리스트링 대신 x-goog-api-key 헤더로 전달.
                # 구글의 현재 권장 방식이고, URL에 키가 그대로 남아 서버/프록시 로그에 찍히는
                # 문제도 피할 수 있음. (쿼리스트링 방식도 여전히 동작은 하지만 헤더가 표준.)
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
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
        if resp.status_code == 404:
            # 흔한 원인: teacher.gemini_model에 더 이상 존재하지 않거나 오타인 모델명이 저장돼 있음.
            raise HTTPException(
                status_code=400,
                detail=f"설정된 Gemini 모델('{model}')을 찾을 수 없어요. 설정에서 다른 모델을 선택해주세요. ({_extract_error_detail(resp)})",
            )
        if resp.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail=f"Gemini 서버가 일시적으로 과부하 상태예요 (재시도 {_MAX_ATTEMPTS}회 실패).",
            )
        if resp.status_code != 200:
            # 예전엔 상태 코드만 보여줬는데, 실제 원인(잘못된 파라미터, 콘텐츠 정책 위반 등)이
            # error.message에 들어있는 경우가 많아서 그대로 노출하도록 바꿈.
            raise HTTPException(
                status_code=502,
                detail=f"Gemini 호출 중 오류가 발생했어요 ({resp.status_code}): {_extract_error_detail(resp)}",
            )

        data = resp.json()

        # 응답에 candidates 자체가 없는 경우: 프롬프트/지문이 세이프티 필터에 걸려 통째로
        # 차단된 것. 예전엔 이 경우도 KeyError로 떨어져서 "응답 형식이 예상과 달라요"라는
        # 원인 불명 에러만 보여줬음 -> 실제 원인(콘텐츠 차단)을 그대로 안내.
        if not data.get("candidates"):
            block_reason = data.get("promptFeedback", {}).get("blockReason")
            if block_reason:
                raise HTTPException(
                    status_code=400,
                    detail=f"입력한 지문이 Gemini의 콘텐츠 정책에 걸려 처리되지 않았어요 (사유: {block_reason}). 지문 내용을 확인해주세요.",
                )
            raise HTTPException(status_code=502, detail="Gemini가 결과를 반환하지 않았어요. 다시 시도해주세요.")

        candidate = data["candidates"][0]
        finish_reason = candidate.get("finishReason")

        # 콘텐츠가 세이프티/저작권(RECITATION) 사유로 중간에 막히면 parts 자체가 없을 수 있음.
        if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
            raise HTTPException(
                status_code=400,
                detail=f"Gemini가 콘텐츠 정책({finish_reason}) 때문에 응답을 생성하지 못했어요. 지문이나 목표 어법 입력을 조금 바꿔서 다시 시도해주세요.",
            )

        try:
            text = candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise HTTPException(status_code=502, detail=f"Gemini 응답 형식이 예상과 달라요. (finishReason: {finish_reason})")

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


async def call_gemini_json(
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    max_output_tokens: int = 16000,
) -> dict:
    """Gemini를 호출하고, 응답을 JSON으로 파싱해서 dict로 돌려줌.
    JSON 강제 출력 모드(responseMimeType)를 써서 마크다운 펜스 등이 안 섞이게 함.

    지문분석/워크북에서 502/503이 자주 나던 원인:
    1) maxOutputTokens가 지나치게 커서 응답 생성이 오래 걸렸고, Render 등 배포 플랫폼의
       프록시가 자체 타임아웃(보통 ~100초)으로 연결을 먼저 끊어버려 앱의 에러 처리가
       실행되기도 전에 502/503이 발생했음 -> 기본값을 16000으로 낮춤.
    2) httpx 타임아웃 시(ReadTimeout 등) 예외를 잡지 않아서 처리되지 않은 예외가
       그대로 터져 나갔음 -> 명시적으로 잡아서 504로 변환.
    3) Gemini가 "모델 과부하(503)"를 순간적으로 반환하는 경우가 꽤 있는데, 예전엔
       바로 에러를 사용자에게 보여줬음 -> 짧은 대기 후 최대 4회까지 자동 재시도.
    4) 워크북·목표어법 문제처럼 스키마가 크고 출력 토큰이 많이 필요한 요청은, 재시도를
       다 써도 503이 반복되는 경우가 있었음(모델 자체가 혼잡한 시간대) -> 같은 모델로만
       계속 재시도하지 않고, 마지막엔 안정적인 폴백 모델(gemini-2.5-flash)로 자동 전환해서
       한 번 더 시도함.
    5) 목표어법 문제처럼 스키마가 복잡한 경우 응답이 중간에 잘리거나(MAX_TOKENS) 코드펜스/
       트레일링 콤마가 섞여 "유효한 JSON이 아님" 에러가 났음 -> 잘렸으면 토큰 한도를 올려서
       재시도하고, 그 외의 경우도 경미한 포맷 오류는 자동으로 복구해서 재시도함.
    """
    try:
        return await _call_gemini_once(api_key, model, system_prompt, user_message, max_output_tokens)
    except HTTPException as e:
        # 지금 쓰던 모델이 이미 폴백 모델이었거나, 실패 원인이 과부하/요청한도(503/429)가
        # 아니면(예: 키 오류, 콘텐츠 정책 위반) 폴백해봐야 똑같이 실패하므로 그대로 던짐.
        if model == FALLBACK_MODEL or e.status_code not in (503, 429):
            raise
        try:
            return await _call_gemini_once(api_key, FALLBACK_MODEL, system_prompt, user_message, max_output_tokens)
        except HTTPException:
            # 폴백까지 실패하면, 폴백을 시도했다는 사실을 알 수 있게 원래 에러 메시지에 덧붙여서 던짐.
            raise HTTPException(
                status_code=e.status_code,
                detail=f"{e.detail} (안정 모델 '{FALLBACK_MODEL}'로도 재시도했지만 실패했어요. 잠시 후 다시 시도해주세요.)",
            )
