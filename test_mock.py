"""
Claude API 호출 없이, 미리 만든 mock JSON으로 렌더링→PDF 파이프라인만 검증하는 스크립트.
(실제 배포 시에는 app/main.py의 /analyze 엔드포인트가 Claude API 응답을 이 스키마로 파싱해서 넘김)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.schemas import AnalysisResponse
from app.render import render_pdf, render_html

MOCK_DATA = {
    "passages": [
        {
            "title_en": "Limiting Visits for Flu Prevention",
            "title_kr": "독감 예방을 위한 방문 제한 조치",
            "passage_index": 1,
            "target_grammar": "현재완료, to부정사",
            "sentences": [
                {
                    "num": 1,
                    "badge": "target",
                    "tokens": [
                        {"type": "text", "text": "Since our last communication, new "},
                        {"type": "tag", "text": "developments", "tag_class": "v", "caption": "새로운 상황"},
                        {"type": "text", "text": " on the flu "},
                        {"type": "tag", "text": "epidemic", "tag_class": "v", "caption": "유행병"},
                        {"type": "tag", "text": "have", "tag_class": "g", "caption": "현재완료"},
                        {"type": "text", "text": " moved "},
                        {"type": "hl", "text": "from day-to-day to moment-to-moment", "tag_class": None, "caption": None},
                        {"type": "text", "text": "."},
                    ],
                    "translation": "지난번 연락을 드린 이후로, 독감 유행에 관한 새로운 상황들이 매일 변하던 것에서 매 순간 변하는 것으로 바뀌었습니다.",
                    "notes": [
                        {"category": "comprehension", "body": "독감 유행 상황이 'from day-to-day to moment-to-moment'(매일에서 매 순간으로) 급박하게 변하고 있다는 배경을 제시하며 글을 시작하고 있어."},
                        {"category": "grammar", "body": "'Since + 과거 시점, 주어 + 현재완료'는 '~이후로 지금까지'라는 의미를 나타낼 때 쓰이는 표현이야."},
                    ],
                },
                {
                    "num": 2,
                    "badge": "topic",
                    "tokens": [
                        {"type": "conn", "text": "Since", "tag_class": None, "caption": None},
                        {"type": "text", "text": " we believe "},
                        {"type": "tag", "text": "that", "tag_class": "g", "caption": "명사절 접속사"},
                        {"type": "text", "text": " "},
                        {"type": "tag", "text": "minimizing", "tag_class": "gv", "caption": "동명사"},
                        {"type": "text", "text": " the number of social contacts "},
                        {"type": "tag", "text": "is", "tag_class": "g", "caption": "주어에 수일치"},
                        {"type": "text", "text": " important "},
                        {"type": "tag", "text": "to prevent", "tag_class": "g", "caption": "to부정사(목적)"},
                        {"type": "text", "text": " the spread of the disease, we "},
                        {"type": "tag", "text": "have decided", "tag_class": "g", "caption": "현재완료"},
                        {"type": "tag", "text": "to take", "tag_class": "g", "caption": "to부정사(명사적)"},
                        {"type": "text", "text": " an "},
                        {"type": "tag", "text": "urgent", "tag_class": "v", "caption": "긴급한"},
                        {"type": "tag", "text": "measure", "tag_class": "v", "caption": "조치"},
                        {"type": "text", "text": "."},
                    ],
                    "translation": "우리는 사회적 접촉의 수를 최소화하는 것이 질병의 확산을 막기 위해 중요하다고 믿기 때문에, 긴급한 조치를 취하기로 결정했습니다.",
                    "notes": [
                        {"category": "comprehension", "body": "질병 확산을 막기 위해 사회적 접촉 최소화가 필수적이라는 판단 하에 긴급 조치를 취하게 되었다는 인과관계가 뚜렷해."},
                        {"category": "grammar", "body": "that절 안에서 동명사구 주어는 단수 취급하여 'is'로 수일치 시킨 부분에 주목해야 해."},
                    ],
                },
            ],
            "summary": {
                "theme": "독감 예방을 위한 방문 제한 안내",
                "flow": "상황 변화 → 조치 결정 → 제한 안내 → 대안 제시 → 문의 및 안내",
                "background": "전염병 유행 시 공동주택/실버타운에서의 방역 조치에 관한 글로, 수능 독해에서 자주 출제되는 주제야.",
            },
            "vocabulary": [
                {"word": "development", "meaning": "(새로운) 상황, 사태", "synonym": "situation, occurrence", "antonym": None},
                {"word": "epidemic", "meaning": "유행병, 전염병", "synonym": "outbreak", "antonym": None},
                {"word": "minimize", "meaning": "최소화하다", "synonym": "reduce, lessen", "antonym": "maximize"},
                {"word": "urgent", "meaning": "긴급한", "synonym": "pressing, immediate", "antonym": "trivial"},
                {"word": "measure", "meaning": "조치", "synonym": "step, action", "antonym": None},
            ],
        }
    ]
}

if __name__ == "__main__":
    analysis = AnalysisResponse.model_validate(MOCK_DATA)
    print("스키마 검증 통과 ✓")

    html_out = Path("test_output.html")
    html_out.write_text(render_html(analysis), encoding="utf-8")
    print(f"HTML 생성 완료: {html_out.resolve()}")

    pdf_out = "test_output.pdf"
    render_pdf(analysis, pdf_out)
    print(f"PDF 생성 완료: {Path(pdf_out).resolve()}")
