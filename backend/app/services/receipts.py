import asyncio
import hashlib
import logging
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select

from ..core.errors import AppError
from ..models.food import Ingredient, Operation, utcnow
from ..models.identity import User
from ..models.receipts import ReceiptImport
from ..schemas.food import BatchInput
from ..schemas.receipts import ParsedReceipt, ReceiptDraft
from . import food
from .receipt_images import validate_image
from .receipt_parser import failure_diagnostic

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
logger = logging.getLogger(__name__)


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
    return {"id": row.id, "version": row.version, "status": row.status,
            "parse_status": ("failed" if row.parse_status == "parsing" and row.parse_started_at
                             and utcnow() - row.parse_started_at > timedelta(seconds=120) else row.parse_status), "parsed": row.parsed, "draft": row.draft, "result": row.result,
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
        db.flush()
        return view(row)
    return food.run_operation(db, user_id, key, "receipt_" + kind,
                              {"receipt_id": str(receipt_id), **body.model_dump(mode="json")}, action)


def _parse_result(result):
    if result.get("receipt_parse_conflict"):
        raise AppError(409, "RECEIPT_CONFLICT", "Receipt changed; recognition was discarded")
    return result


def _finish_parse(db, user_id, key, receipt_id, version, parsed, status):
    try:
        db.scalar(select(User).where(User.id == user_id).with_for_update())
        db.expire_all()
        current = food.owned(db, ReceiptImport, receipt_id, user_id, lock=True)
        op = db.scalar(select(Operation).where(Operation.user_id == user_id, Operation.key == key))
        if current.parse_finished_at is not None:
            return _parse_result(op.result)
        current.parse_finished_at = utcnow()
        if current.status != "draft" or current.version != version:
            current.parse_status = "discarded"
            op.result = {"receipt_parse_conflict": True}
        else:
            current.parse_status = status
            current.parsed = parsed
            if status == "parsed":
                draft = ReceiptDraft.model_validate(parsed)
                for line in draft.items:
                    # Even a model's confident output cannot skip human review.
                    line.uncertain = True
                    try:
                        line.ingredient_id = UUID(food.resolve(db, user_id, line.name)["id"])
                    except AppError as exc:
                        if exc.code != "NOT_FOUND":
                            raise
                current.draft = match_draft(db, user_id, draft)
            current.version += 1
            db.flush()
            op.result = jsonable_encoder(view(current))
        result = op.result
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _parse_result(result)


async def parse(db, user_id, key, receipt_id, body, root, parser, timeout, daily_limit=10):
    payload = {"receipt_id": str(receipt_id), **body.model_dump(mode="json")}
    claim = []

    def admit(op):
        row = food.owned(db, ReceiptImport, receipt_id, user_id, lock=True)
        require_draft(row, body.expected_version)
        if row.version != 1 or row.parse_started_at is not None:
            raise AppError(409, "RECEIPT_CONFLICT", "This receipt was edited or recognition was already attempted")
        now = utcnow()
        attempts = db.scalar(select(func.count()).select_from(ReceiptImport).where(
            ReceiptImport.user_id == user_id, ReceiptImport.parse_started_at > now - timedelta(days=1)))
        if attempts >= daily_limit:
            raise AppError(429, "RECEIPT_PARSE_LIMIT", "Daily recognition limit reached; use manual entry")
        active = db.scalar(select(ReceiptImport.id).where(
            ReceiptImport.user_id == user_id, ReceiptImport.parse_finished_at.is_(None),
            ReceiptImport.parse_started_at > now - timedelta(seconds=120)))
        if active:
            raise AppError(429, "RECEIPT_PARSE_BUSY", "Recognition is already running; use manual entry or wait")
        claim.append((read_file(root, row), row.media_type))
        row.parse_started_at = now
        row.parse_status = "parsing"
        db.flush()
        return view(row)

    result = food.run_operation(db, user_id, key, "receipt_parse", payload, admit)
    db.rollback()  # Commit admission and release the transaction before network I/O.
    if not claim:
        result = _parse_result(result)
        if result.get("parse_status") == "parsing":
            row = food.owned(db, ReceiptImport, receipt_id, user_id)
            expired = utcnow() - row.parse_started_at > timedelta(seconds=120)
            db.rollback()
            if expired:
                return _finish_parse(db, user_id, key, receipt_id, body.expected_version, {}, "failed")
        return result
    content, media_type = claim[0]
    try:
        validate_image(content, media_type)
        output = await asyncio.wait_for(parser.parse(content, media_type), timeout=timeout)
        parsed = ParsedReceipt.model_validate(output).model_dump(mode="json")
        status = "parsed"
    except Exception as exc:
        logger.warning("Receipt recognition failed receipt_id=%s diagnostic=%s",
                       receipt_id, failure_diagnostic(exc))
        parsed, status = {}, "failed"
    return _finish_parse(db, user_id, key, receipt_id, body.expected_version, parsed, status)
