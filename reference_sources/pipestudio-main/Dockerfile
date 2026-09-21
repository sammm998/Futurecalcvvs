# Pipe detection microservice — FutureCalc `detect-pipes` contract.
#
# Tesseract is a hard runtime dependency: label text is read by rendering the
# drawing's glyph strokes and running one OCR pass over them.  Without it the
# service still segments pipes but classifies nothing, so it is installed in
# the image rather than left to the host.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-service.txt

# only what the service needs at runtime — the review app and its assets are
# a separate, local-only tool and are deliberately not shipped here
COPY pipe_seg.py pipe_types.py pipe_rules.py pipe_ai.py pipe_signature.py ./
# the ML label / joining-point detector (35 MB ONNX).  Override the location
# with AI_MODEL_PATH; AI_DETECTOR=0 restores the vector/glyph rules.
COPY models/ ./models/
# reviewapp supplies the detection stages the review UI edits; service/review.py
# calls into it so the deployed service and the local tool cannot drift apart
COPY reviewapp/ ./reviewapp/
COPY service/ ./service/
COPY vectorascore/ ./vectorascore/
COPY studio/ ./studio/
RUN chmod +x service/entrypoint.sh

# drop root
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Documentation only: the contract's port locally, while Cloud Run and friends
# inject their own $PORT, which the entrypoint honours.
ENV PORT=5005
EXPOSE 5005

# Cloud Run runs its own health probes and rejects images whose HEALTHCHECK
# hardcodes a port, so this stays runtime-resolved too.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["./service/entrypoint.sh"]
