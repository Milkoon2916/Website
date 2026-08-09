FROM python:3.12-slim

# WeasyPrint(PDF 렌더링)에 필요한 시스템 라이브러리.
# 한글 폰트(나눔고딕)는 apt로 설치하지 않고 app/assets/fonts에 직접 번들해서 씀
# (배포 환경마다 시스템 폰트가 다를 수 있어서, 파일로 직접 지정하는 게 더 안정적)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
