# Local validation recovery after Docker VHD I/O corruption. Not the production/CI recipe.
# The driver verifies this pre-existing image ID before building:
# sha256:0abc1395d9b59a000d3f6571c79f8d7d1cdbff68e783c03697be3f3d8f15a453
FROM solomeal-ocr:compat-1015-01
USER root
RUN mkdir -p /var/lib/solomeal/ocr-models && chown solomeal:solomeal /var/lib/solomeal/ocr-models
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
USER solomeal
CMD ["python", "-m", "app.jobs.supervise"]
