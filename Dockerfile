FROM python:3.12-slim

# WeasyPrint 시스템 의존성 + 한글 폰트 (구문분석/OX/워크북 PDF에서 공통으로 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libharfbuzz-subset0 \
    libjpeg62-turbo \
    libopenjp2-7 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# VOCA 서비스가 생성 파일을 저장하는 폴더 (깃에 안 올라가도 빌드 시 항상 새로 만든다)
RUN mkdir -p voca_service/outputs

# Render는 $PORT 환경변수로 포트를 지정함
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
