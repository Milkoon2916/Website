"""
지문분석/워크북 결과를 PDF로 렌더링.
나눔고딕 폰트를 프로젝트에 직접 번들해서 씀 (app/assets/fonts) — 배포 서버가
구글 폰트 CDN에 접속 못 해도 항상 정확히 나눔고딕으로 렌더링되게 하기 위함.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
FONTS_DIR = BASE_DIR / "assets" / "fonts"

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

FONT_REGULAR = (FONTS_DIR / "NanumGothic.ttf").as_uri()
FONT_BOLD = (FONTS_DIR / "NanumGothicBold.ttf").as_uri()


def render_analysis_pdf(result: dict, title: str | None = None) -> bytes:
    template = env.get_template("analysis_pdf.html")
    html_str = template.render(result=result, title=title, font_regular=FONT_REGULAR, font_bold=FONT_BOLD)
    return HTML(string=html_str, base_url=str(BASE_DIR)).write_pdf()


def render_workbook_pdf(result: dict, title: str | None = None) -> bytes:
    template = env.get_template("workbook_pdf.html")
    html_str = template.render(result=result, title=title, font_regular=FONT_REGULAR, font_bold=FONT_BOLD)
    return HTML(string=html_str, base_url=str(BASE_DIR)).write_pdf()


def render_ox_pdf(result: dict, title: str | None = None) -> bytes:
    template = env.get_template("ox_pdf.html")
    html_str = template.render(result=result, title=title, font_regular=FONT_REGULAR, font_bold=FONT_BOLD)
    return HTML(string=html_str, base_url=str(BASE_DIR)).write_pdf()
