"""
Gemini API가 반환해야 하는 구조화된 분석 결과의 스키마.
스킬(passage-analysis-pdf)의 references/format-guide.md 규칙을 데이터 구조로 옮긴 것.

핵심 설계 원칙: Claude에게 자유 형식 HTML을 직접 만들게 하지 않고,
이 스키마에 맞는 JSON만 반환하도록 강제한다. -> 파싱/렌더링이 훨씬 안정적.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class Token(BaseModel):
    """문장을 이루는 조각 하나. 일반 텍스트이거나, 색상 태그가 붙은 단어/구."""
    type: Literal["text", "tag", "conn", "hl"]
    text: str  # 원문 그대로의 영어 단어/구 (또는 일반 텍스트 조각)
    tag_class: Optional[Literal["g", "v", "gv"]] = None  # type == "tag"일 때만
    caption: Optional[str] = None  # type == "tag"일 때만, 2-6자 한글 캡션

    @field_validator("tag_class", mode="before")
    @classmethod
    def _fallback_unknown_tag_class(cls, v):
        # Gemini가 가끔 type 값("hl", "conn" 등)을 tag_class에 잘못 넣는 경우가 있어,
        # 전체 렌더링이 깨지지 않도록 알 수 없는 값은 "g"로 안전하게 대체한다.
        if v is not None and v not in {"g", "v", "gv"}:
            return "g"
        return v


_VALID_NOTE_CATEGORIES = {"comprehension", "grammar", "blank", "writing", "implication", "theme"}


class Note(BaseModel):
    category: Literal[
        "comprehension",  # 독해 포인트
        "grammar",        # 어법 포인트
        "blank",          # 빈칸
        "writing",        # 서술형
        "implication",    # 함의추론
        "theme",          # 주제/요지
    ]
    body: str  # 2-4문장, 캐주얼한 tutor 어투

    @field_validator("category", mode="before")
    @classmethod
    def _fallback_unknown_category(cls, v):
        # Gemini가 가끔 badge 값("target" 등)을 category에 잘못 넣는 경우가 있어,
        # 전체 렌더링이 깨지지 않도록 알 수 없는 값은 "grammar"로 안전하게 대체한다.
        if v not in _VALID_NOTE_CATEGORIES:
            return "grammar"
        return v


class Sentence(BaseModel):
    num: int
    badge: Optional[Literal["topic", "insert", "target"]] = None  # 주제문 / 문장삽입 / 목표 어법
    tokens: list[Token] = Field(min_length=1)
    translation: str  # 자연스러운 한글 번역 (직역 아님)
    notes: list[Note] = Field(default_factory=list)


class Summary(BaseModel):
    theme: str        # 주제
    flow: str          # 흐름: "도입 (...) → 전개 (...) → 결론 (...)"
    background: str    # 배경지식 4-7문장


class VocabItem(BaseModel):
    """지문에서 뽑은 핵심 어휘 1개. 유의어/반의어 표에 들어가는 한 행."""
    word: str                        # 지문에 쓰인 원형 그대로의 영어 단어/표현
    meaning: str                     # 문맥에 맞는 한글 뜻
    synonym: Optional[str] = None    # 유의어 (영어, 콤마로 여러 개 가능). 마땅한 게 없으면 null
    antonym: Optional[str] = None    # 반의어 (영어, 콤마로 여러 개 가능). 마땅한 게 없으면 null


class PassageAnalysis(BaseModel):
    title_en: str
    title_kr: str
    passage_index: int = 1
    target_grammar: Optional[str] = None  # 사용자가 지정한 목표 어법 (예: "가정법 도치, 분사구문")
    sentences: list[Sentence] = Field(min_length=1)
    summary: Summary
    vocabulary: list[VocabItem] = Field(min_length=5)  # 유의어/반의어 표. 필수 (최소 5개) -- Gemini가
                                                          # 빼먹지 못하도록 default를 두지 않음


# Claude에게 요구할 최종 JSON의 최상위 형태 (여러 지문을 한 번에 받을 수도 있게)
class AnalysisResponse(BaseModel):
    passages: list[PassageAnalysis] = Field(min_length=1)
