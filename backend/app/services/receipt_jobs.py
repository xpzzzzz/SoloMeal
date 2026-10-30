"""Durable admission, fenced execution and outbox recovery. No inventory writes."""
import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_, select

from ..core.errors import AppError
from ..models.food import Operation, utcnow
from ..models.identity import User
from ..models.receipts import ReceiptImport, ReceiptParseTask
from ..schemas.receipts import ParsedReceipt, ReceiptDraft
from . import food, receipts
from .receipt_images import validate_image
from .receipt_parser import failure_diagnostic
from .receipt_recognition import RecognitionResult

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")


def enqueue(db, user_id, key, receipt_id, body, settings):
    # An omitted optional mode must preserve the hash of pre-OCR parse operations.
    payload = {"receipt_id": str(receipt_id), **body.model_dump(mode="json", exclude_none=True)}

    def admit(op):
        row = food.owned(db, ReceiptImport, receipt_id, user_id, lock=True)
        receipts.require_draft(row, body.expected_version)
        if row.version != 1 or row.parse_started_at is not None:
            raise AppError(409, "RECEIPT_CONFLICT", "Recognition was already attempted or the receipt was edited")
        now = utcnow()
        attempts = db.scalar(select(func.count()).select_from(ReceiptImport).where(
            ReceiptImport.user_id == user_id, ReceiptImport.parse_started_at > now - timedelta(days=1)))
        if attempts >= settings.receipt_parse_daily_limit:
            raise AppError(429, "RECEIPT_PARSE_LIMIT", "Daily recognition limit reached; use manual entry")
        active = db.scalar(select(ReceiptImport.id).where(
            ReceiptImport.user_id == user_id, ReceiptImport.parse_finished_at.is_(None),
            or_(ReceiptImport.parse_deadline_at > now,
                and_(ReceiptImport.parse_task_id.is_(None),
                     ReceiptImport.parse_started_at > now - timedelta(seconds=120)))))
        if active:
            raise AppError(429, "RECEIPT_PARSE_BUSY", "Recognition is already pending; use manual entry or wait")
        receipts.read_file(settings.receipt_storage_dir, row)
        deadline = now + timedelta(seconds=settings.receipt_task_deadline_seconds)
        task = ReceiptParseTask(user_id=user_id, receipt_id=row.id, operation_id=op.id,
                                mode=getattr(body, "mode", None) or settings.receipt_recognition_mode,
                                expected_version=row.version, max_attempts=settings.receipt_task_max_attempts,
                                deadline_at=deadline, available_at=now, dispatch_after=now)
        db.add(task)
        db.flush()
        row.parse_task_id, row.parse_started_at, row.parse_deadline_at = task.id, now, deadline
        row.parse_status, row.parse_error = "queued", None
        db.flush()
        return receipts.view(row)

    food.run_operation(db, user_id, key, "receipt_parse", payload, admit)
    # Replay returns current state, including completion or cancellation after acceptance.
    return receipts.view(food.owned(db, ReceiptImport, receipt_id, user_id))


def _locked(db, task_id):
    initial = db.get(ReceiptParseTask, task_id)
    if initial is None:
        return None, None
    owner, receipt_id = initial.user_id, initial.receipt_id
    db.scalar(select(User).where(User.id == owner).with_for_update())
    db.expire_all()
    row = food.owned(db, ReceiptImport, receipt_id, owner, lock=True)
    task = db.scalar(select(ReceiptParseTask).where(ReceiptParseTask.id == task_id).with_for_update())
    return task, row


def _sync_operation(db, task, row):
    op = db.get(Operation, task.operation_id)
    op.result = jsonable_encoder(receipts.view(row))


def _terminal(db, task, row, state, error=None):
    now = utcnow()
    task.status, task.last_error, task.finished_at = state, error, now
    task.lease_token = task.lease_until = task.publish_token = task.publish_until = None
    row.parse_finished_at, row.parse_error = now, error
    if row.status != "draft" or row.version != task.expected_version:
        row.parse_status = "discarded"
        task.status = "discarded"
    else:
        row.parse_status = "parsed" if state == "succeeded" else state
        row.version += 1
    _sync_operation(db, task, row)


def invalidate(db, row):
    """Called under the existing owner/receipt mutation locks, in that transaction."""
    if row.parse_task_id:
        task = db.scalar(select(ReceiptParseTask).where(
            ReceiptParseTask.id == row.parse_task_id, ReceiptParseTask.user_id == row.user_id).with_for_update())
        if task and task.status in ACTIVE:
            _terminal(db, task, row, "discarded")


def _eligible(db, task, row, now):
    if task.status not in ACTIVE:
        return False
    if row.status != "draft" or row.version != task.expected_version:
        _terminal(db, task, row, "discarded")
        return False
    if now >= task.deadline_at:
        _terminal(db, task, row, "failed", "deadline_exceeded")
        return False
    return True


def claim(factory, task_id, settings):
    with factory() as db:
        task, row = _locked(db, task_id)
        now = utcnow()
        if not task or not _eligible(db, task, row, now):
            db.commit()
            return None
        if ((task.status == "running" and task.lease_until and task.lease_until > now)
                or (task.status == "queued" and task.available_at > now)):
            return None
        if task.attempts >= task.max_attempts:
            _terminal(db, task, row, "failed", "attempts_exhausted")
            db.commit()
            return None
        token = str(uuid4())
        task.status, task.lease_token = "running", token
        task.lease_until = now + timedelta(seconds=settings.receipt_task_lease_seconds)
        task.attempts += 1
        task.last_error, row.parse_error, row.parse_status = None, None, "parsing"
        source = {name: getattr(row, name) for name in ("file_key", "file_hash", "byte_size", "media_type")}
        source["mode"] = task.mode
        db.commit()
        return token, source


def finish(factory, task_id, token, settings, parsed=None, diagnostic=None, recognition=None):
    with factory() as db:
        task, row = _locked(db, task_id)
        now = utcnow()
        if (not task or task.status != "running" or task.lease_token != token
                or not task.lease_until or task.lease_until <= now):
            return False
        if not _eligible(db, task, row, now):
            db.commit()
            return False
        if recognition is not None:
            row.recognition = recognition
        if parsed is not None:
            draft = ReceiptDraft.model_validate(parsed)
            for line in draft.items:
                line.uncertain = True
                try:
                    line.ingredient_id = UUID(food.resolve(db, task.user_id, line.name)["id"])
                except AppError as exc:
                    if exc.code != "NOT_FOUND":
                        raise
            row.parsed, row.draft = parsed, receipts.match_draft(db, task.user_id, draft)
            _terminal(db, task, row, "succeeded")
        else:
            category = diagnostic["category"]
            retryable = category in ("timeout", "provider_transport", "provider_rate_limit", "storage") or (
                category == "provider_http" and diagnostic.get("provider_http_status", 0) >= 500)
            if retryable and task.attempts < task.max_attempts:
                task.status, task.last_error = "queued", category
                task.lease_token = task.lease_until = None
                task.dispatch_after = now + timedelta(seconds=settings.receipt_retry_seconds * task.attempts)
                task.available_at = task.dispatch_after
                row.parse_status, row.parse_error = "retrying", category
                _sync_operation(db, task, row)
            else:
                _terminal(db, task, row, "failed", category)
        db.commit()
        return True


def execute(factory, settings, parser, task_id):
    task_id = str(UUID(task_id))
    claimed = claim(factory, task_id, settings)
    if not claimed:
        return
    token, source = claimed
    recognition = None
    if hasattr(parser, "last_metadata"):
        parser.last_metadata = None  # Never attach a prior user's evidence after an early file failure.
    # The claim transaction and its connection are closed before image/model work.
    try:
        content = receipts.read_file(settings.receipt_storage_dir, SimpleNamespace(**source))
        validate_image(content, source["media_type"])

        async def invoke():
            operation = (parser.parse_mode(content, source["media_type"], source["mode"])
                         if hasattr(parser, "parse_mode") else parser.parse(content, source["media_type"]))
            return await asyncio.wait_for(operation, timeout=settings.receipt_parser_timeout_seconds)

        result = asyncio.run(invoke())
        if isinstance(result, RecognitionResult):
            recognition, result = result.metadata, result.parsed
        output = ParsedReceipt.model_validate(result)
        for line in output.items:
            line.uncertain = True
        parsed, diagnostic = output.model_dump(mode="json"), None
    except Exception as exc:
        recognition = getattr(parser, "last_metadata", None)
        diagnostic = failure_diagnostic(exc)
        if isinstance(exc, AppError) and exc.code == "RECEIPT_STORAGE":
            diagnostic = {"category": "storage"}
        parsed = None
        logger.warning("Receipt recognition failed task_id=%s diagnostic=%s", task_id, diagnostic)
    finish(factory, task_id, token, settings, parsed, diagnostic, recognition)


def dispatch(factory, settings, publish, *, limit=50):
    """Short DB claims around bounded publishing; a lost confirm is safe to resend."""
    now = utcnow()
    with factory() as db:
        ids = db.scalars(select(ReceiptParseTask.id).where(
            ReceiptParseTask.status.in_(ACTIVE),
            or_(ReceiptParseTask.deadline_at <= now,
                and_(ReceiptParseTask.status == "queued", ReceiptParseTask.dispatch_after <= now),
                and_(ReceiptParseTask.status == "running", ReceiptParseTask.lease_until <= now)))
            .order_by(ReceiptParseTask.created_at, ReceiptParseTask.id).limit(limit)).all()
    published = 0
    for task_id in ids:
        with factory() as db:
            task, row = _locked(db, task_id)
            now = utcnow()
            if not task or not _eligible(db, task, row, now):
                db.commit()
                continue
            if task.publish_until and task.publish_until > now:
                continue
            if task.status == "queued" and task.dispatch_after > now:
                continue
            if task.status == "running":
                if task.lease_until and task.lease_until > now:
                    continue
                task.status, row.parse_status = "queued", "retrying"
                task.available_at = now
                task.lease_token = task.lease_until = None
            if task.attempts >= task.max_attempts:
                _terminal(db, task, row, "failed", "attempts_exhausted")
                db.commit()
                continue
            token = str(uuid4())
            task.publish_token, task.publish_until = token, now + timedelta(seconds=30)
            task.dispatch_attempts += 1
            deadline = task.deadline_at
            db.commit()
        # No database connection or row lock is held during broker I/O.
        try:
            publish(task_id, deadline)
            sent = True
        except Exception:
            sent = False
        with factory() as db:
            task, row = _locked(db, task_id)
            if task and task.publish_token == token:
                task.publish_token = task.publish_until = None
                if task.status in ACTIVE:
                    task.dispatch_after = utcnow() + timedelta(seconds=30 if sent else settings.receipt_retry_seconds)
                    task.dispatched_at = utcnow() if sent else task.dispatched_at
                    task.last_error = None if sent else "broker_unavailable"
                db.commit()
        published += int(sent)
    return published
