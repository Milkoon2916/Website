import html
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from .schemas import AnalysisResponse, ComprehensionRequest

TEMPLATE_DIR = Path(__file__).parent / "templates"

NOTE_LABELS = {
    "comprehension": "독해 포인트",
    "grammar": "어법 포인트",
    "blank": "빈칸",
    "writing": "서술형",
    "implication": "함의추론",
    "theme": "주제",
}

_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def render_html(analysis: AnalysisResponse) -> str:
    template = _env.get_template("passage.html.j2")
    return template.render(
        passages=analysis.passages,
        note_labels=NOTE_LABELS,
    )


def render_pdf(analysis: AnalysisResponse, output_path: str) -> str:
    html_str = render_html(analysis)
    HTML(string=html_str).write_pdf(output_path)
    return output_path


def _esc(s: str | None) -> str | None:
    return html.escape(s) if s is not None else None


def render_comprehension_html(req: ComprehensionRequest) -> str:
    """OX 워크북 결과(브라우저에서 이미 Gemini로 생성한 JSON)를 인쇄용 PDF HTML로 렌더링.
    passage.html.j2와 달리 이쪽은 사용자가 붙여넣은 순수 텍스트만 다루므로 escape 처리한다."""
    template = _env.get_template("comprehension.html.j2")
    group_a = [{"num": it.num, "text": _esc(it.text), "answer": it.answer} for it in req.groupA]
    group_b = [{"num": it.num, "text": _esc(it.text), "answer": it.answer} for it in req.groupB]
    ko_range = f"01~{req.groupA[-1].num}"
    en_range = f"{req.groupB[0].num}~{req.groupB[-1].num}"
    return template.render(
        title_ko=_esc(req.titleKo),
        title_en=_esc(req.titleEn),
        source=_esc(req.source),
        passage=_esc(req.passage),
        group_a=group_a,
        group_b=group_b,
        ko_range=ko_range,
        en_range=en_range,
        watermark=req.watermark,
    )


def render_comprehension_pdf(req: ComprehensionRequest, output_path: str) -> str:
    html_str = render_comprehension_html(req)
    HTML(string=html_str).write_pdf(output_path)
    return output_path
