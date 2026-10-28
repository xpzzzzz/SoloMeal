"""Durable coordination for confirmations and remote preference changes.

The existing operations table stores permanent confirmation receipts and per-user
preference tombstones. No database transaction is held during provider I/O.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from ..core.errors import AppError
from ..models.agent import AgentRun, ToolExecution
from ..models.food import Operation
from ..models.identity import User
from . import memory_diagnostics as diagnostics
from .memory import (
    MemoryPreference,
    MemoryProvider,
    MemoryReadError,
    MemoryWriteResult,
    ReconciliationCandidate,
    ReconciliationEvidence,
)


def _semantic(preference):
    return {"category": preference.category, "target": preference.target.strip().lower(),
            "polarity": preference.polarity}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _pref_key(preference):
    return "memory-pref-" + _digest(_semantic(preference))


def _confirmation_key(run_id, step):
    return f"memory-confirm-{run_id}-{step}"


def _lookup(db, user_id, key, *, lock=False):
    query = select(Operation).where(Operation.user_id == user_id, Operation.key == key)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def _owner_lock(db, user_id):
    if db.scalar(select(User).where(User.id == user_id).with_for_update()) is None:
        raise AppError(404, "NOT_FOUND", "User not found")


def _slot(db, user_id, preference):
    key = _pref_key(preference)
    slot = _lookup(db, user_id, key, lock=True)
    if slot is None:
        slot = Operation(user_id=user_id, key=key, kind="memory_preference",
                         request_hash=_digest(_semantic(preference)), result={"state": "new"})
        db.add(slot)
        db.flush()
    if slot.kind != "memory_preference" or slot.request_hash != _digest(_semantic(preference)):
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Memory operation key is unavailable")
    return slot


def _unknown():
    raise AppError(503, "MEMORY_OUTCOME_UNKNOWN", "Memory operation outcome is unknown; do not retry blindly")


def _pending():
    raise AppError(409, "MEMORY_PENDING", "Memory operation is pending or requires reconciliation")


def _record_reconciliation(receipt, operator, before, after, basis, detail="none"):
    result = dict(receipt.result or {})
    audit = list(result.get("reconciliation_audit", []))
    audit.append({"operator": operator, "at": datetime.now(timezone.utc).isoformat(),
                  "before": before, "after": after, "basis": basis, "detail": detail})
    receipt.result = {**result, "reconciliation_audit": audit}


def _verified_suggestion(db, user_id, run_id, step, preference):
    run = db.scalar(select(AgentRun).where(AgentRun.id == str(run_id), AgentRun.user_id == user_id))
    event = db.scalar(select(ToolExecution).where(ToolExecution.run_id == str(run_id),
                      ToolExecution.user_id == user_id, ToolExecution.step == step,
                      ToolExecution.tool == "suggest_memory"))
    expected = {"category": preference.category, "target": preference.target, "polarity": preference.polarity}
    if run is None or event is None or not isinstance(event.result, dict) or event.result.get("memory_suggestion") != expected:
        raise AppError(404, "MEMORY_SUGGESTION_NOT_FOUND", "Memory suggestion not found or does not match")


def confirm(db, user_id, run_id, step, preference, provider):
    """Persist one receipt, commit, then make at most one external add call."""
    if not getattr(provider, "enabled", False):
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory provider is unavailable")
    key = _confirmation_key(str(run_id), step)
    request_hash = _digest({"run_id": str(run_id), "step": step, **_semantic(preference)})
    try:
        _owner_lock(db, user_id)
        _verified_suggestion(db, user_id, run_id, step, preference)
        prior = _lookup(db, user_id, key, lock=True)
        if prior is not None:
            if prior.kind != "memory_confirmation" or prior.request_hash != request_hash:
                raise AppError(409, "IDEMPOTENCY_CONFLICT", "Confirmation already used")
            state = (prior.result or {}).get("state")
            slot = _lookup(db, user_id, _pref_key(preference), lock=True)
            slot_state = (slot.result or {}).get("state") if slot is not None else None
            db.commit()
            if state == "saved" and slot_state == "active":
                return {"saved": True}
            if state == "saved" and slot_state == "retired":
                raise AppError(409, "MEMORY_RETIRED", "This confirmation was already applied and later changed")
            if state == "not_sent":
                raise AppError(409, "MEMORY_RETIRED", "This confirmation was resolved without retry")
            if state == "pending":
                _pending()
            _unknown()
        slot = _slot(db, user_id, preference)
        state = (slot.result or {}).get("state")
        if state in ("pending", "mutating", "unknown"):
            db.commit()
            _pending()
        operation_id = str(uuid4())
        binding = {"operation_id": operation_id, "slot_key": slot.key,
                   "run_id": str(run_id), "step": step}
        receipt = Operation(user_id=user_id, key=key, kind="memory_confirmation",
                            request_hash=request_hash, result={"state": "pending", **binding})
        db.add(receipt)
        if state == "active":
            receipt.result = {"state": "saved"}
            db.commit()
            return {"saved": True}
        slot.result = {"state": "pending", "operation_id": operation_id}
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent reservation won. Never perform an extra external write.
        _pending()
    except OperationalError as exc:
        db.rollback()
        if db.bind.dialect.name == "sqlite" and "locked" in str(exc).lower():
            _pending()
        raise
    except Exception:
        db.rollback()
        raise

    try:
        if isinstance(provider, MemoryProvider):
            outcome = provider.add_confirmed(user_id, preference, operation_id=operation_id)
        else:
            success = provider.add(user_id, preference, operation_id=operation_id) is True
            outcome = MemoryWriteResult("saved" if success else "unknown")
    except Exception:
        outcome = MemoryWriteResult("unknown")
    # A failure, timeout, or lost response is indistinguishable from a committed add.
    try:
        _owner_lock(db, user_id)
        receipt = _lookup(db, user_id, key, lock=True)
        slot = _lookup(db, user_id, _pref_key(preference), lock=True)
        state = outcome.state if outcome.state in {"saved", "unknown", "not_sent"} else "unknown"
        receipt.result = {**binding, "state": state,
                          **({"memory_id": outcome.memory_id} if outcome.memory_id else {}),
                          **({"event_id": outcome.event_id} if outcome.event_id else {}),
                          **({"observed_memory_id": outcome.observed_memory_id} if outcome.observed_memory_id else {})}
        slot.result = {"state": {"saved": "active", "unknown": "unknown", "not_sent": "retired"}[state],
                       "operation_id": operation_id}
        db.commit()
    except Exception:
        db.rollback()
        _unknown()
    if state == "not_sent":
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory was not sent; confirmation was not retried")
    if state != "saved":
        _unknown()
    return {"saved": True}


def reconcile_confirmation(db, receipt_id, provider, *, operator):
    """Operator-only service; provider I/O is outside transactions, with locked recheck.

    No API route exposes this operation. An authoritative evidence provider must
    guarantee complete, stable results, ownership and correlation verification.
    """
    if not isinstance(operator, str) or not operator or len(operator) > 128:
        raise ValueError("A verified operator identity is required")
    receipt = db.get(Operation, str(receipt_id))
    if receipt is None or receipt.kind != "memory_confirmation":
        db.rollback()
        return "not_found"
    user_id, receipt_key = receipt.user_id, receipt.key
    _owner_lock(db, user_id)
    db.expire(receipt)
    receipt = _lookup(db, user_id, receipt_key, lock=True)
    if receipt is None or receipt.kind != "memory_confirmation":
        db.rollback()
        return "not_found"
    before = dict(receipt.result or {})
    if before.get("state") != "unknown":
        _record_reconciliation(receipt, operator, before.get("state", "missing"),
                               before.get("state", "missing"), "not_unknown")
        db.commit()
        return "not_unknown"
    operation_id, slot_key = before.get("operation_id"), before.get("slot_key")
    try:
        if str(UUID(operation_id)) != operation_id:
            raise ValueError
        run_id, step = before["run_id"], before["step"]
        event = db.scalar(select(ToolExecution).where(ToolExecution.run_id == run_id,
            ToolExecution.user_id == user_id, ToolExecution.step == step,
            ToolExecution.tool == "suggest_memory"))
        data = event.result["memory_suggestion"]
        preference = MemoryPreference(data["category"], data["target"], data["polarity"])
        _verified_suggestion(db, user_id, run_id, step, preference)
        if (receipt.key != _confirmation_key(run_id, step) or slot_key != _pref_key(preference)
                or receipt.request_hash != _digest({"run_id": run_id, "step": step, **_semantic(preference)})):
            raise ValueError
    except (TypeError, ValueError, KeyError, AttributeError, AppError):
        _record_reconciliation(receipt, operator, "unknown", "unknown", "legacy_or_invalid")
        db.commit()
        return "legacy_or_invalid"
    slot = _lookup(db, user_id, slot_key, lock=True)
    slot_before = dict(slot.result or {}) if slot else {}
    if (slot is None or slot.kind != "memory_preference" or slot.request_hash != _digest(_semantic(preference))
            or slot_before.get("state") != "unknown" or slot_before.get("operation_id") != operation_id):
        _record_reconciliation(receipt, operator, "unknown", "unknown", "slot_changed")
        db.commit()
        return "changed"
    receipt_key = receipt.key
    db.commit()
    detail = "none"
    try:
        evidence = provider.inspect_reconciliation(user_id, operation_id)
        if (not isinstance(evidence, ReconciliationEvidence)
                or any(type(v) is not bool for v in (evidence.authoritative, evidence.not_sent, evidence.conflict))):
            raise ValueError("Invalid provider evidence")
        candidates = evidence.candidates
        if (not isinstance(candidates, tuple) or any(not isinstance(c, ReconciliationCandidate) for c in candidates)):
            raise ValueError("Invalid provider evidence")
        conflict = evidence.conflict or len(candidates) > 1
        if evidence.conflict:
            detail = "provider_conflict"
        if len(candidates) > 1:
            detail = "multiple_candidates"
        for candidate in candidates:
            p = candidate.preference
            try:
                valid_id = str(UUID(p.id)) == p.id
            except (ValueError, TypeError, AttributeError):
                valid_id = False
            if (candidate.user_id != user_id or candidate.operation_id != operation_id or not valid_id
                    or not isinstance(p, MemoryPreference)
                    or (p.category, p.target, p.polarity) != (preference.category, preference.target, preference.polarity)):
                conflict = True
                detail = ("owner_mismatch" if candidate.user_id != user_id else
                          "correlation_mismatch" if candidate.operation_id != operation_id else
                          "invalid_id" if not valid_id else "content_mismatch")
        if conflict:
            decision = "conflict"
        elif evidence.authoritative and len(candidates) == 1 and not evidence.not_sent:
            decision = "saved"
        elif evidence.authoritative and evidence.not_sent and not candidates:
            decision = "not_sent"
        else:
            decision = "inconclusive"
    except MemoryReadError as exc:
        decision = {"unverified": "conflict", "incomplete": "inconclusive"}.get(exc.reason, "unavailable")
        detail, candidates = exc.reason if exc.reason in {"unverified", "incomplete", "unavailable"} else "unavailable", ()
    except Exception:
        decision, candidates = "unavailable", ()
    try:
        # Sessions use expire_on_commit=False. Force the locked re-read to see
        # commits made while remote I/O was in progress, not identity-map data.
        db.expire_all()
        _owner_lock(db, user_id)
        receipt = _lookup(db, user_id, receipt_key, lock=True)
        slot = _lookup(db, user_id, slot_key, lock=True)
        if (receipt is None or slot is None or (receipt.result or {}) != before
                or (slot.result or {}) != slot_before):
            if receipt is not None:
                _record_reconciliation(receipt, operator, "unknown", (receipt.result or {}).get("state", "missing"),
                                       "changed")
            db.commit()
            return "changed"
        _record_reconciliation(receipt, operator, "unknown", decision if decision in {"saved", "not_sent"} else "unknown",
                               decision, detail)
        result = dict(receipt.result)
        if decision == "saved":
            result.update(state="saved", memory_id=candidates[0].preference.id)
            slot.result = {"state": "active", "operation_id": operation_id}
        elif decision == "not_sent":
            result["state"] = "not_sent"
            slot.result = {"state": "retired", "operation_id": operation_id}
        receipt.result = result
        db.commit()
        return decision
    except Exception:
        db.rollback()
        raise


def filter_suppressed(db, user_id, memories):
    """Suppress pending/uncertain or retired facts, including stale remote hits."""
    if not memories:
        return memories
    keys = {_pref_key(p) for p in memories}
    rows = db.scalars(select(Operation).where(Operation.user_id == user_id,
                      Operation.kind == "memory_preference", Operation.key.in_(keys))).all()
    diagnostics.increment("suppressed_unknown", sum((row.result or {}).get("state") == "unknown" for row in rows))
    diagnostics.increment("suppressed_pending", sum((row.result or {}).get("state") in ("pending", "mutating") for row in rows))
    diagnostics.increment("suppressed_retired", sum((row.result or {}).get("state") == "retired" for row in rows))
    blocked = {row.key for row in rows if (row.result or {}).get("state") != "active"}
    return [p for p in memories if _pref_key(p) not in blocked]


def _change(db, user_id, memory_id, replacement, provider):
    """Suppress the old fact before remote mutations and reconcile all duplicates."""
    if not getattr(provider, "enabled", False):
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory provider is unavailable")
    # End the authentication read transaction before any network operation.
    db.commit()
    try:
        previous = provider.get_owned(user_id, memory_id)
    except MemoryReadError as exc:
        code = "MEMORY_OWNERSHIP_UNVERIFIED" if exc.reason == "unverified" else "MEMORY_UNAVAILABLE"
        raise AppError(503, code, "Memory could not be verified") from exc
    except Exception as exc:
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory could not be verified") from exc
    if previous is None:
        raise AppError(404, "MEMORY_NOT_FOUND", "Memory not found")
    if not isinstance(previous, MemoryPreference):
        raise AppError(503, "MEMORY_UNAVAILABLE", "Memory could not be verified")
    same = replacement is not None and _semantic(previous) == _semantic(replacement)
    try:
        _owner_lock(db, user_id)
        old_slot = _slot(db, user_id, previous)
        old_state = (old_slot.result or {}).get("state")
        old_result = dict(old_slot.result or {})
        if old_state in ("pending", "mutating", "unknown"):
            db.commit()
            _pending()
        new_slot = old_slot if same else (_slot(db, user_id, replacement) if replacement else None)
        new_result = dict(new_slot.result or {}) if new_slot is not None else None
        if new_slot is not None and new_slot is not old_slot and (new_slot.result or {}).get("state") in ("pending", "mutating", "unknown"):
            db.commit()
            _pending()
        old_slot.result = {"state": "mutating"}
        if new_slot is not None:
            new_slot.result = {"state": "mutating"}
        db.commit()
    except IntegrityError:
        db.rollback()
        _pending()
    except Exception:
        db.rollback()
        raise

    try:
        records = provider.list_for_management(user_id)
        if not isinstance(records, list):
            raise MemoryReadError("unavailable")
    except Exception as exc:
        # The listing is read-only: no remote mutation has been attempted.
        # Restore the original slots instead of inventing an unknown write.
        try:
            _owner_lock(db, user_id)
            old_slot = _lookup(db, user_id, _pref_key(previous), lock=True)
            new_slot = _lookup(db, user_id, _pref_key(replacement), lock=True) if replacement and not same else None
            if (old_slot is None or (old_slot.result or {}).get("state") != "mutating"
                    or (replacement and not same and (new_slot is None
                        or (new_slot.result or {}).get("state") != "mutating"))):
                raise RuntimeError("Memory reservation changed during preflight")
            for slot, original in ((old_slot, old_result), (new_slot, new_result)):
                if slot is not None:
                    if original.get("state") == "new":
                        db.delete(slot)
                    else:
                        slot.result = original
            db.commit()
        except Exception:
            db.rollback()
            _unknown()
        reason = exc.reason if isinstance(exc, MemoryReadError) else "unavailable"
        code = {"incomplete": "MEMORY_INCOMPLETE", "unverified": "MEMORY_OWNERSHIP_UNVERIFIED"}.get(
            reason, "MEMORY_UNAVAILABLE")
        raise AppError(503, code, "Memory list could not be verified") from exc

    try:
        duplicates = [p for p in records if isinstance(p, MemoryPreference)
                      and _semantic(p) == _semantic(previous)]
        if not any(p.id == str(memory_id) for p in duplicates):
            _unknown()
        if replacement is None:
            success = all(provider.delete(user_id, p.id) is True for p in duplicates)
        else:
            target_duplicates = [p for p in records if isinstance(p, MemoryPreference)
                                 and _semantic(p) == _semantic(replacement)]
            if target_duplicates and not same:
                # The corrected fact already exists: retain one copy and remove all
                # old copies, rather than creating another duplicate remotely.
                retained = provider.get_owned(user_id, target_duplicates[0].id)
                success = (isinstance(retained, MemoryPreference)
                           and _semantic(retained) == _semantic(replacement))
                if success:
                    to_delete = duplicates + target_duplicates[1:]
                    success = all(provider.delete(user_id, p.id) is True for p in to_delete)
            else:
                success = provider.update(user_id, str(memory_id), replacement) is True
                if success:
                    success = all(provider.delete(user_id, p.id) is True for p in duplicates if p.id != str(memory_id))
    except Exception:
        success = False

    try:
        _owner_lock(db, user_id)
        old_slot = _lookup(db, user_id, _pref_key(previous), lock=True)
        new_slot = _lookup(db, user_id, _pref_key(replacement), lock=True) if replacement else None
        old_slot.result = {"state": "unknown" if not success else ("active" if same else "retired")}
        if new_slot is not None and not same:
            new_slot.result = {"state": "active" if success else "unknown"}
        db.commit()
    except Exception:
        db.rollback()
        _unknown()
    if not success:
        _unknown()
    return {"updated": True} if replacement else {"deleted": True}


def update(db, user_id, memory_id, preference, provider):
    return _change(db, user_id, memory_id, preference, provider)


def delete(db, user_id, memory_id, provider):
    return _change(db, user_id, memory_id, None, provider)
