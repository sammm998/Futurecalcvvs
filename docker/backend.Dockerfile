FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Samma systembibliotek som rot-Dockerfilen: OCR-granskningen importerar OpenCV, som länkar mot libGL och glib,
# och slim-imagen bär ingendera. Utan dem svarar granskningen "kunde inte köras" på varje blad - felet var
# lagat i rot-Dockerfilen men inte här, så docker compose gav en annan tjänst än Railway.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY engine /app/engine
COPY backend /app/backend
RUN pip install --no-cache-dir -e /app/engine
WORKDIR /app/backend
ENV VVS_STORAGE_ROOT=/data/storage
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
