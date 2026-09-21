# Single-container image: engine + API + built frontend (served by FastAPI). Used by Railway / any Docker host.
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# What the OCR cross-check needs from the system, checked rather than guessed: the recogniser imports OpenCV,
# whose extension links against libGL and glib, and the slim image carries neither. Because the recogniser is
# imported on first use, the miss surfaced as "the check could not be run" on every sheet instead of as a
# missing dependency at build time. tests/test_image_dependencies.py reads this line against what the installed
# packages actually ask the loader for, so the two cannot drift apart.
#
# fonts-liberation is what the tender is set in. A slim Python image carries no fonts at all, so the font file
# the tender asked for was not there and every tender request answered with an error - the page said only
# "Hämtning misslyckades". The code now falls back to a built-in font rather than failing, and the package is
# installed so the fallback is never the one that is used.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 fonts-liberation tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/requirements-ocr.txt /app/backend/requirements-ocr.txt
COPY backend/requirements-native.txt /app/backend/requirements-native.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt -r /app/backend/requirements-ocr.txt -r /app/backend/requirements-native.txt
COPY engine /app/engine
COPY backend /app/backend
COPY models /app/models
COPY reference_sources /app/reference_sources
RUN pip install --no-cache-dir -e /app/engine
COPY --from=frontend /fe/dist /app/frontend/dist
# Left empty on purpose: an image that bakes in the word "unknown" answers the question "which code is running?"
# with something that looks like an answer, and the platform's own commit variable is then never consulted.
ARG VVS_BUILD=""
ENV VVS_BUILD=${VVS_BUILD}
ENV VVS_STATIC_DIR=/app/frontend/dist \
    VVS_STORAGE_ROOT=/data/storage \
    VVS_DATABASE_URL=sqlite:////data/vvs.db
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
