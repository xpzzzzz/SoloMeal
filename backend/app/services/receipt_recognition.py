"""OCR first, validated assistance and explicit conflict preservation."""
import re
import time
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from ..core.errors import AppError
from ..schemas.receipts import ParsedReceipt
from .food import convert
from .receipt_ocr import PaddleReceiptOCR
from .receipt_parser import VisionReceiptParser, configured
from .receipt_rules import APPROX, MEASURE, NUMBERED, extract_fields

AMBIGUOUS = {'approximate_or_range', 'package_count_unknown', 'quantity_invalid', 'refund_or_negative'}


def name_key(value):
    value = NUMBERED.sub('', unicodedata.normalize('NFKC', value).lower())
    original = value
    value = MEASURE.sub('', value)
    value = re.sub(r'不定重|大约|约', '', value)
    # Damaged specifications can aid identity matching, never quantity recovery.
    value = re.sub(r'\d+[a-z\d.]*$', '', value.strip())
    value = re.sub(r'(?:kg|ml)$', '', value)
    return re.sub(r'[^a-z\d\u3400-\u9fff]', '', value) or re.sub(r'[^a-z\d\u3400-\u9fff]', '', original)


def align_items(ocr, vlm, fields):
    """Monotonic product alignment; no positional assumption after an insertion."""
    n, m = len(ocr), len(vlm)
    keys_a, keys_b = [name_key(x['name']) for x in ocr], [name_key(x['name']) for x in vlm]
    scores, steps = [[0.] * (m + 1) for _ in range(n + 1)], {}
    for i in range(1, n + 1):
        scores[i][0], steps[i, 0] = -.4 * i, 'ocr'
    for j in range(1, m + 1):
        scores[0][j], steps[0, j] = -.4 * j, 'vlm'
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            a, b = keys_a[i-1], keys_b[j-1]
            similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
            contained = min(len(a), len(b)) >= 2 and (a in b or b in a)
            choices = [(scores[i-1][j] - .4, 'ocr'), (scores[i][j-1] - .4, 'vlm')]
            damaged = bool(set(fields[i-1]['issues']) & {'low_confidence', 'quantity_missing'})
            correction = (damaged and (similarity >= .5 or contained)) or (min(len(a), len(b)) >= 4 and similarity >= .75)
            if a and b and (a == b or correction):
                choices.append((scores[i-1][j-1] + (2 if a == b else similarity), 'pair'))
            scores[i][j], steps[i, j] = max(choices, key=lambda x: x[0])
    result = []
    i, j = n, m
    while i or j:
        step = steps[i, j]
        if step == 'pair':
            result.append((i-1, j-1))
            i, j = i-1, j-1
        elif step == 'ocr':
            result.append((i-1, None))
            i -= 1
        else:
            result.append((None, j-1))
            j -= 1
    return list(reversed(result))


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
        meta = {"version": "recognition-v2", "mode": mode, "path": [], "ocr_lines": [],
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
            except Exception as exc:
                if mode == "hybrid" and (configured(self.settings) or getattr(self.vlm, "is_mock", False)):
                    meta["issues"].append("ocr_unavailable")
                    parsed = await vision([])
                else:
                    raise AppError(503, "RECEIPT_OCR_UNAVAILABLE", "Use manual receipt entry") from exc
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
        meta["vlm_proposal"] = deepcopy(vlm)
        if len(ocr["items"]) != len(vlm["items"]):
            meta["conflicts"].append({"field": "item_count", "ocr": len(ocr["items"]), "vlm": len(vlm["items"])})
        alignment = align_items(ocr['items'], vlm['items'], fields)
        meta['alignment'] = [{'ocr_index': a, 'vlm_index': b} for a, b in alignment]
        unresolved = any(set(fields[a]['issues']) & AMBIGUOUS for a, b in alignment if a is not None and b is None)
        result, evidence = [], []
        for a, b in alignment:
            index = len(result)
            field = deepcopy(fields[a]) if a is not None else {'line_orders': [], 'issues': ['vlm_only_item']}
            field['item_index'] = index
            if a is None or b is None:
                first = deepcopy(vlm['items'][b] if a is None else ocr['items'][a])
                source = 'vlm_assistance' if a is None else 'ocr_unmatched'
                field['source'] = source
                meta['conflicts'].append({'item_index': index, 'field': 'item', 'reason': source})
                if a is None and (unresolved or APPROX.search(first['name'])):
                    first['quantity'] = first['unit'] = None
                    field['issues'].append('unresolved_quantity')
                first['uncertain'] = True
                result.append(first)
                evidence.append(field)
                continue
            first, second = deepcopy(ocr['items'][a]), vlm['items'][b]
            if name_key(first['name']) != name_key(second['name']):
                meta["conflicts"].append({"item_index": index, "field": "name",
                                          "ocr": first["name"], "vlm": second["name"]})
                first['name'] = unicodedata.normalize('NFKC', second['name'])
                field['name_source'] = 'vlm_assistance'
            ambiguous = set(field["issues"]) & AMBIGUOUS
            if ambiguous:
                first["quantity"] = first["unit"] = None
                if second["quantity"] is not None:
                    meta["conflicts"].append({"item_index": index, "field": "quantity",
                                              "ocr": None, "vlm": second["quantity"], "reason": "unresolved_quantity"})
            elif first["quantity"] is None and second["quantity"] is not None:
                first["quantity"], first["unit"] = second["quantity"], second["unit"]
                field["quantity_source"] = "vlm_assistance"
            elif second["quantity"] is not None and not quantities_equal(first, second):
                meta["conflicts"].append({"item_index": index, "field": "quantity", "ocr": first["quantity"], "vlm": second["quantity"]})
                first["quantity"] = first["unit"] = None
            if first["amount"] is None:
                first["amount"] = second["amount"]
                field["amount_source"] = "vlm_assistance" if second["amount"] is not None else "unknown"
            elif second["amount"] is not None and Decimal(first["amount"]) != Decimal(second["amount"]):
                meta["conflicts"].append({"item_index": index, "field": "amount", "ocr": first["amount"], "vlm": second["amount"]})
                first["amount"] = None
            first["uncertain"] = True
            result.append(first)
            evidence.append(field)
        ocr = {**ocr, 'items': result}
        meta['fields'] = evidence
        if ocr["purchased_on"] and vlm["purchased_on"] and ocr["purchased_on"] != vlm["purchased_on"]:
            meta["conflicts"].append({"field": "purchased_on", "ocr": ocr["purchased_on"], "vlm": vlm["purchased_on"]})
            ocr["purchased_on"] = None
        elif ocr['purchased_on'] is None:
            ocr['purchased_on'] = vlm['purchased_on']
        return ocr
