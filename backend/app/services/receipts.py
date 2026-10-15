import hashlib
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select

from ..core.errors import AppError
from ..models.food import Ingredient, utcnow
from ..models.receipts import ReceiptImport
from ..schemas.food import BatchInput
from ..schemas.receipts import ReceiptDraft
from . import food
from .receipt_images import validate_image

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def validate_upload(content, media_type):
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise AppError(413, "RECEIPT_SIZE", "Upload a non-empty image up to 5 MiB")
    # Reject obvious format mismatches before invoking the bounded decoder.
    valid = ((media_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
             or (media_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff")))
    if not valid:
        raise AppError(415, "RECEIPT_TYPE", "Only PNG and JPEG images are supported")
    validate_image(content, media_type)


def file_path(root: Path, key: str):
    name = str(UUID(key))
    base = root.resolve()
    path = (base / name).resolve()
    if path.parent != base:
        raise AppError(503, "RECEIPT_STORAGE", "Receipt storage is unavailable")
    return path


def read_file(root, row):
    try:
        with file_path(root, row.file_key).open("rb") as source:
            content = source.read(MAX_UPLOAD_BYTES + 1)
        if len(content) != row.byte_size or hashlib.sha256(content).hexdigest() != row.file_hash:
            raise OSError("Receipt content changed")
        return content
    except (OSError, ValueError) as exc:
        raise AppError(503, "RECEIPT_STORAGE", "Receipt storage is unavailable") from exc


def view(row):
    expired = (row.parse_finished_at is None and row.parse_deadline_at
               and utcnow() >= row.parse_deadline_at)
    legacy_expired = (row.parse_task_id is None and row.parse_status == "parsing"
                      and row.parse_started_at and utcnow() - row.parse_started_at > timedelta(seconds=120))
    return {"id": row.id, "version": row.version, "status": row.status,
            "parse_status": "failed" if expired or legacy_expired else row.parse_status,
            "parse_task_id": row.parse_task_id, "parse_deadline_at": row.parse_deadline_at,
            "parse_error": "deadline_exceeded" if expired else row.parse_error,
            "recognition": row.recognition,
            "parsed": row.parsed, "draft": row.draft, "result": row.result,
            "parse_started_at": row.parse_started_at, "parse_finished_at": row.parse_finished_at,
            "media_type": row.media_type, "byte_size": row.byte_size, "created_at": row.created_at}


def upload(db, user_id, key, content, media_type, root):
    validate_upload(content, media_type)
    digest = hashlib.sha256(content).hexdigest()
    created = []

    def action(op):
        duplicate = db.scalar(select(ReceiptImport.id).where(
            ReceiptImport.user_id == user_id, ReceiptImport.file_hash == digest)
            .order_by(ReceiptImport.created_at, ReceiptImport.id))
        file_key = str(uuid4())
        path = file_path(root, file_key)
        try:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("xb") as target:
                created.append(path)
                target.write(content)
        except OSError as exc:
            raise AppError(503, "RECEIPT_STORAGE", "Receipt storage is unavailable") from exc
        row = ReceiptImport(user_id=user_id, file_key=file_key, file_hash=digest,
                            media_type=media_type, byte_size=len(content))
        db.add(row)
        db.flush()
        return {**view(row), "duplicate_of": duplicate}

    try:
        return food.run_operation(db, user_id, key, "receipt_upload",
                                  {"hash": digest, "media_type": media_type}, action)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def require_draft(row, version):
    if row.status != "draft" or row.version != version:
        raise AppError(409, "RECEIPT_CONFLICT", "Receipt changed; reload before continuing")


def match_draft(db, user_id, draft):
    value = draft.model_dump(mode="json")
    for line in value["items"]:
        if line["ingredient_id"]:
            food.owned(db, Ingredient, line["ingredient_id"], user_id)
    return value


def edit(db, user_id, key, receipt_id, body):
    def action(op):
        row = food.owned(db, ReceiptImport, receipt_id, user_id, lock=True)
        require_draft(row, body.expected_version)
        row.draft = match_draft(db, user_id, body.draft)
        row.version += 1
        from .receipt_jobs import invalidate
        invalidate(db, row)
        db.flush()
        return view(row)
    return food.run_operation(db, user_id, key, "receipt_edit",
                              {"receipt_id": str(receipt_id), **body.model_dump(mode="json")}, action)


def change(db, user_id, key, receipt_id, body, kind):
    def action(op):
        row = food.owned(db, ReceiptImport, receipt_id, user_id, lock=True)
        require_draft(row, body.expected_version)
        if kind == "cancel":
            row.status = "cancelled"
        else:
            draft = ReceiptDraft.model_validate(row.draft)
            batches = []
            for index, line in enumerate(draft.items, start=1):
                if line.excluded:
                    continue
                if line.uncertain or line.ingredient_id is None or line.quantity is None or line.unit is None:
                    raise AppError(422, "RECEIPT_REVIEW_REQUIRED", f"Review receipt line {index} before confirming")
                try:
                    batch = BatchInput.model_validate(line.model_dump(include={
                        "ingredient_id", "quantity", "unit", "expires_on", "expiry_source", "location"}))
                except ValidationError as exc:
                    raise AppError(422, "RECEIPT_DATE_REQUIRED", f"Check date and source on receipt line {index}") from exc
                item = food.owned(db, Ingredient, batch.ingredient_id, user_id)
                food.convert(batch.quantity, batch.unit, item.unit)
                batches.append((index, batch))
            if not batches:
                raise AppError(422, "RECEIPT_EMPTY", "Include at least one reviewed ingredient")
            results = [{"line": index, "batch": food.add_batch(db, user_id, key, batch, operation=op)}
                       for index, batch in batches]
            row.result = jsonable_encoder({"batches": results, "operation_id": op.id})
            row.status = "completed"
        row.version += 1
        from .receipt_jobs import invalidate
        invalidate(db, row)
        db.flush()
        return view(row)
    return food.run_operation(db, user_id, key, "receipt_" + kind,
                              {"receipt_id": str(receipt_id), **body.model_dump(mode="json")}, action)
