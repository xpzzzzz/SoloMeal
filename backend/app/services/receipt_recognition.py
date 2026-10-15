"""OCR first, validated assistance and explicit conflict preservation."""
import time
from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import AppError
from ..schemas.receipts import ParsedReceipt
from .food import convert, normalize
from .receipt_ocr import PaddleReceiptOCR
from .receipt_parser import VisionReceiptParser, configured
from .receipt_rules import extract_fields


@dataclass
class RecognitionResult:
    parsed: dict
    metadata: dict


def quantities_equal(first, second):
    if first.get("quantity") is None or second.get("quantity") is None:
        return first.get("quantity") == second.get("quantity") and first.get("unit") == second.get("unit")
    try:
        a, b = first["unit"], second["unit"]
        target = {"kg": "g", "l": "ml"}.get(a, a)
        return convert(Decimal(first["quantity"]), a, target) == convert(Decimal(second["quantity"]), b, target)
    except Exception:
        return False


class ReceiptRecognizer:
    def __init__(self, settings, *, ocr=None, vlm=None):
        self.settings = settings
        self.ocr = ocr or PaddleReceiptOCR(settings)
        self.vlm = vlm or VisionReceiptParser(settings)
        self.last_metadata = None

    async def parse_mode(self, content, media_type, mode):
        started = time.perf_counter()
        meta = {"version": "recognition-v1", "mode": mode, "path": [], "ocr_lines": [],
                "fields": [], "issues": [], "conflicts": [], "vlm_calls": 0, "token_usage": None}
        self.last_metadata = meta

        async def vision(lines):
            meta["vlm_calls"] += 1
            meta["path"].append("vlm")
            try:
                if lines and hasattr(self.vlm, "parse_with_ocr"):
                    value = await self.vlm.parse_with_ocr(content, media_type, lines)
                else:
                    value = await self.vlm.parse(content, media_type)
            except Exception as exc:
                raise AppError(502, "RECEIPT_PARSER_FAILED", "Receipt assistance failed; use manual entry") from exc
            meta["token_usage"] = getattr(self.vlm, "last_usage", None)
            result = ParsedReceipt.model_validate(value)
            for item in result.items:
                item.uncertain = True
                if item.quantity is not None and item.unit is not None:
                    target = {"kg": "g", "l": "ml"}.get(item.unit, item.unit)
                    convert(item.quantity, item.unit, target)
            return result.model_dump(mode="json")

        if mode == "vlm_only":
            parsed = await vision([])
        else:
            try:
                lines = self.ocr.extract(content)
                meta["ocr_lines"] = lines
                meta["path"].append("ocr")
                parsed, fields, issues = extract_fields(lines, self.settings.receipt_ocr_min_confidence)
                meta["fields"], meta["issues"] = fields, issues
            except Exception:
                if mode == "hybrid" and (configured(self.settings) or getattr(self.vlm, "is_mock", False)):
                    meta["issues"].append("ocr_unavailable")
                    parsed = await vision([])
                else:
                    raise AppError(503, "RECEIPT_OCR_UNAVAILABLE", "Use manual receipt entry")
            else:
                if not parsed["items"]:
                    if mode == "hybrid" and (configured(self.settings) or getattr(self.vlm, "is_mock", False)):
                        parsed = await vision(lines)
                    else:
                        raise AppError(503, "RECEIPT_OCR_UNAVAILABLE", "Use manual receipt entry")
                elif mode == "hybrid" and issues:
                    if configured(self.settings) or getattr(self.vlm, "is_mock", False):
                        assisted = await vision(lines)
                        parsed = self.merge(parsed, assisted, fields, meta)
                    else:
                        meta["issues"].append("vlm_unavailable_manual_review")
        if not parsed["items"]:
            raise AppError(502, "RECEIPT_PARSER_FAILED", "No reviewable receipt items; use manual entry")
        meta["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return RecognitionResult(parsed=ParsedReceipt.model_validate(parsed).model_dump(mode="json"), metadata=meta)

    def merge(self, ocr, vlm, fields, meta):
        # Positional alignment is accepted only when counts and names agree; otherwise
        # retain OCR rows, attach both interpretations privately and ask for review.
        meta["vlm_proposal"] = vlm
        if len(ocr["items"]) != len(vlm["items"]):
            meta["conflicts"].append({"field": "item_count", "ocr": len(ocr["items"]), "vlm": len(vlm["items"])})
            return ocr
        for index, (first, second) in enumerate(zip(ocr["items"], vlm["items"], strict=True)):
            if normalize(first["name"]) != normalize(second["name"]):
                meta["conflicts"].append({"item_index": index, "field": "name",
                                          "ocr": first["name"], "vlm": second["name"]})
                first["quantity"] = first["unit"] = None
                continue
            ambiguous = set(fields[index]["issues"]) & {"approximate_or_range", "package_count_unknown", "quantity_invalid", "refund_or_negative"}
            if ambiguous:
                first["quantity"] = first["unit"] = None
                if second["quantity"] is not None:
                    meta["conflicts"].append({"item_index": index, "field": "quantity",
                                              "ocr": None, "vlm": second["quantity"], "reason": "unresolved_quantity"})
            elif first["quantity"] is None and second["quantity"] is not None:
                first["quantity"], first["unit"] = second["quantity"], second["unit"]
                fields[index]["quantity_source"] = "vlm_assistance"
            elif second["quantity"] is not None and not quantities_equal(first, second):
                meta["conflicts"].append({"item_index": index, "field": "quantity", "ocr": first["quantity"], "vlm": second["quantity"]})
                first["quantity"] = first["unit"] = None
            if first["amount"] is None:
                first["amount"] = second["amount"]
                fields[index]["amount_source"] = "vlm_assistance" if second["amount"] is not None else "unknown"
            elif second["amount"] is not None and Decimal(first["amount"]) != Decimal(second["amount"]):
                meta["conflicts"].append({"item_index": index, "field": "amount", "ocr": first["amount"], "vlm": second["amount"]})
                first["amount"] = None
            first["uncertain"] = True
        if ocr["purchased_on"] and vlm["purchased_on"] and ocr["purchased_on"] != vlm["purchased_on"]:
            meta["conflicts"].append({"field": "purchased_on", "ocr": ocr["purchased_on"], "vlm": vlm["purchased_on"]})
            ocr["purchased_on"] = None
        return ocr
