"""
Gemini가 생성한 유의어/반의어(app/prompt.py 6번 항목)를 Datamuse API로 교차 검증한다.
Datamuse(https://www.datamuse.com/api/)는 WordNet 기반 무료 사전 API로, API 키가
필요 없다 (비상업적 이용 기준 1일 10만 건).

검증 규칙:
1. Gemini가 제시한 단어가 Datamuse 결과에도 있으면 -> 그대로 채택 (사전 검증됨)
2. Gemini가 제시한 단어가 Datamuse 결과에 없으면 -> Datamuse 상위 결과로 교체
3. Datamuse에도 결과가 없으면(구어체 표현, 숙어 등 WordNet에 없는 경우)
   -> Gemini 값을 그대로 유지 (사전에 없다고 틀린 건 아니므로)
4. 네트워크 오류/타임아웃 시 -> 조용히 Gemini 원본 값 유지 (렌더링 자체가 실패하면 안 됨)
"""
import httpx
from .schemas import PassageAnalysis

DATAMUSE_URL = "https://api.datamuse.com/words"
_TIMEOUT = 3.0
_MAX_CANDIDATES = 4

# 커넥션 재사용으로 지문 하나당 여러 단어를 조회할 때 오버헤드를 줄인다.
_client = httpx.Client(timeout=_TIMEOUT)


def _lookup(word: str, rel_code: str) -> list[str]:
    """Datamuse에서 word에 대한 rel_syn(유의어) 또는 rel_ant(반의어) 후보를 가져온다.
    실패 시 빈 리스트를 반환해서 호출부가 항상 안전하게 폴백할 수 있게 한다."""
    if not word or not word.strip():
        return []
    try:
        resp = _client.get(
            DATAMUSE_URL,
            params={rel_code: word.strip(), "max": _MAX_CANDIDATES},
        )
        resp.raise_for_status()
        return [item["word"] for item in resp.json() if "word" in item]
    except Exception:
        return []


def _merge(ai_value: str | None, dict_words: list[str]) -> str | None:
    """Gemini 원본 값과 사전 후보를 합쳐서 최종 문자열을 만든다."""
    ai_words = [w.strip() for w in ai_value.split(",") if w.strip()] if ai_value else []
    dict_lower = {w.lower() for w in dict_words}

    verified = [w for w in ai_words if w.lower() in dict_lower]
    if verified:
        extra = [w for w in dict_words if w.lower() not in {v.lower() for v in verified}]
        return ", ".join((verified + extra[:1])[:3])

    if dict_words:
        return ", ".join(dict_words[:2])

    return ai_value  # 사전에 아예 없으면 Gemini 값 유지


def enrich_vocabulary(passage: PassageAnalysis) -> None:
    """passage.vocabulary의 synonym/antonym을 Datamuse로 검증·보강한다 (in-place 수정)."""
    for item in passage.vocabulary:
        syn_candidates = _lookup(item.word, "rel_syn")
        ant_candidates = _lookup(item.word, "rel_ant")
        item.synonym = _merge(item.synonym, syn_candidates)
        item.antonym = _merge(item.antonym, ant_candidates)
