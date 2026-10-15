FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --uid 10001 --create-home solomeal && mkdir -p /var/lib/solomeal/uploads /var/lib/solomeal/ocr-models && chown -R solomeal:solomeal /var/lib/solomeal
USER solomeal

FROM runtime-base AS worker-deps
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-ocr.lock ./requirements-ocr.lock
RUN pip install --no-cache-dir -c requirements.lock -r requirements-ocr.lock && pip check
ENV OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
USER solomeal

FROM worker-deps AS worker
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
CMD ["python", "-m", "app.jobs.supervise"]

# Keep the default build compatible with existing API-only build commands.
FROM runtime-base AS api
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
