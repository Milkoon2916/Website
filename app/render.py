from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from .schemas import AnalysisResponse

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
