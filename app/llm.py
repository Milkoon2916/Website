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
# 짧게 재시도한다. 503 응답 자체는 거의 즉시(수백 ms) 돌아오기 때문에, 재시도 횟수를 늘리고
# 대기 시간을 좀 더 넉넉히 잡아도 전체 응답 시간에는 큰 영향이 없음(반면 배포 플랫폼의
# 프록시 타임아웃 ~100초는 넘지 않도록 여유를 둠).
# generate-all처럼 여러 자료를 동시에 요청할 때는 각 호출의 재시도 타이밍이 겹치면
# 다시 한꺼번에 부딪힐 수 있어서, 대기 시간에 무작위 지터를 더해 서로 어긋나게 함.
_RETRY_STATUS_CODES = {429, 503}
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = [1.5, 3.5, 7.0]  # 1차 실패 후 1.5초, 2차 3.5초, 3차 7초 대기 (+ 지터)

# 재시도를 다 써도 계속 503(과부하)이면, 상대적으로 수요가 적어 덜 붐비는 안정적인
# 구버전 모델로 한 번 더 시도해봄. 같은 회사 API라도 모델별로 과부하 상황이 따로
# 걸리는 경우가 많아서(신규 모델일수록 사람들이 몰려서 더 자주 막힘), 이렇게 하면
# 원래 모델이 계속 막혀 있어도 결과를 받을 수 있는 경우가 꽤 있음.
FALLBACK_MODEL = "gemini-2.5-flash"
_FALLBACK_ATTEMPTS = 2
_FALLBACK_BACKOFF_SECONDS = [2.0]

# "유효한 JSON을 반환하지 않음" / 잦은 실패의 진짜 원인 (2026-08 확인):
# Gemini 3.x 계열(3.5/3.6/3.7-flash 등)은 기본적으로 "thinking"이 켜져 있고,
# thinkingConfig를 안 주면 모델이 알아서 thinking 토큰을 쓰는데, 이 thinking 토큰이
# maxOutputTokens 예산을 실제 답변(JSON)과 "공유"함. 그래서 maxOutputTokens을
# 16000~26000으로 넉넉히 잡아도, 그중 상당 부분을 thinking이 먼저 써버리면 정작
# JSON 답변이 중간에 잘리는(finishReason=MAX_TOKENS) 일이 자주 생김.
# -> 이 작업들은 복잡한 추론이 필요한 게 아니라 정해진 스키마로 정보를 뽑아내는
#    작업이라 thinking이 사실상 불필요함. thinking을 최소화해서 maxOutputTokens
#    대부분이 실제 JSON 출력에 쓰이도록 함(할당량/속도도 함께 개선됨).
#    단, Gemini 2.5 계열은 thinkingLevel이 아니라 thinkingBudget 파라미터를 쓰므로
#    모델 세대에 따라 올바른 파라미터를 골라서 보내야 함 (아래 _thinking_config_for).
# 그 외 두 가지 보조 처리:
# 1) 그래도 잘렸으면(finishReason=MAX_TOKENS) 토큰 한도를 올려서 재시도.
# 2) JSON 강제 모드를 쓰더라도 아주 가끔 ```json 코드펜스나 트레일링 콤마가 섞여 나옴.
#    -> 파싱 전에 가볍게 정리(repair)한 뒤 재시도.


def _thinking_config_for(model: str) -> dict:
    """Gemini 2.5(및 그 이전) 계열은 thinkingBudget(정수, 0=끄기)만 지원하고,
    Gemini 3.x 계열은 thinkingLevel(low/medium/high)을 씀. 둘을 같이 보내면
    400 에러가 나는 모델도 있어서 모델 이름으로 분기함."""
    if model.startswith("gemini-2.5") or model.startswith("gemini-1."):
        return {"thinkingBudget": 0}
    return {"thinkingLevel": "low"}


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


async def _call_with_retries(
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    max_output_tokens: int,
    max_attempts: int,
    backoff_seconds: list[float],
) -> dict:
    """한 모델을 대상으로 재시도 루프를 도는 실제 구현. call_gemini_json이 이걸 감싸서
    503 과부하가 끝까지 안 풀리면 대체 모델로 한 번 더 이 함수를 호출함."""
    url = GEMINI_ENDPOINT.format(model=model)
    current_max_tokens = max_output_tokens

    last_error_detail = "Gemini가 유효한 JSON을 반환하지 않았어요. 다시 시도해주세요."

    for attempt in range(max_attempts):
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "maxOutputTokens": current_max_tokens,
                "temperature": 0.5,
                "thinkingConfig": _thinking_config_for(model),
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

        if resp.status_code in _RETRY_STATUS_CODES and attempt < max_attempts - 1:
            # Gemini가 Retry-After를 내려주면 그 값을 우선 쓰고, 없으면 정해둔 스케줄을 씀.
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
            else:
                wait = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
            await asyncio.sleep(wait + random.uniform(0, 1.5))
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
                detail=f"Gemini 서버가 일시적으로 과부하 상태예요 ({model}, 재시도 {max_attempts}회 실패).",
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

        if attempt < max_attempts - 1:
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
    JSON 강제 출력 모드(response_mime_type)를 써서 마크다운 펜스 등이 안 섞이게 함.

    503(모델 과부하) 대응 2단계:
    1) 같은 모델로 지수 백오프(1.5초 → 3.5초 → 7초 + 지터) 재시도를 최대 4회.
    2) 그래도 계속 503이면, 상대적으로 덜 붐비는 gemini-2.5-flash로 한 번 더
       (최대 2회) 시도해보고, 그것마저 실패하면 원래 모델의 에러를 그대로 보여줌.
    """
    try:
        return await _call_with_retries(
            api_key, model, system_prompt, user_message, max_output_tokens,
            max_attempts=_MAX_ATTEMPTS, backoff_seconds=_BACKOFF_SECONDS,
        )
    except HTTPException as e:
        if e.status_code == 503 and model != FALLBACK_MODEL:
            try:
                return await _call_with_retries(
                    api_key, FALLBACK_MODEL, system_prompt, user_message, max_output_tokens,
                    max_attempts=_FALLBACK_ATTEMPTS, backoff_seconds=_FALLBACK_BACKOFF_SECONDS,
                )
            except HTTPException:
                pass  # 대체 모델도 실패하면 원래 모델의 에러 메시지를 그대로 보여줌
        raise
