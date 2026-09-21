FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
COPY detection_v2/requirements.txt ./requirements-v2.txt
RUN pip install -r requirements.txt -r requirements-v2.txt
COPY pipe_seg.py pipe_types.py pipe_rules.py pipe_ai.py pipe_signature.py ./
COPY models/ ./models/
# The exact same engine and published styles as Pipe Studio; no legacy API.
COPY vectorascore/*.py ./vectorascore/
COPY vectorascore/data/ ./vectorascore/data/
COPY studio/*.py ./studio/
COPY detection_v2/ ./detection_v2/
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
RUN python -m detection_v2.runtime
ENV PORT=5005
EXPOSE 5005
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1
ENTRYPOINT ["sh", "./detection_v2/entrypoint.sh"]
