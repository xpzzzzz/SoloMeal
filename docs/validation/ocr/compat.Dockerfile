# M4.5 isolated dependency experiment; formal production Worker image is finalized in M5.
FROM solomeal-api:backend-m4-1015-01
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
COPY compat-requirements.txt /tmp/ocr-requirements.txt
RUN pip install --no-cache-dir -c /app/requirements.lock -r /tmp/ocr-requirements.txt
ENV OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
USER solomeal
