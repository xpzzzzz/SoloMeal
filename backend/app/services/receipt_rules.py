"""Conservative extraction of explicit quantities; confidence never creates a number."""
import re
from datetime import date
from decimal import Decimal

from ..schemas.receipts import ParsedReceipt, ReceiptLine
from .food import convert

UNIT = {"kg": "kg", "千克": "kg", "公斤": "kg", "g": "g", "克": "g",
        "ml": "ml", "毫升": "ml", "l": "l", "升": "l",
        "个": "piece", "颗": "piece", "只": "piece", "piece": "piece"}
MEASURE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|千克|公斤|ml|毫升|piece|g|克|l|升|个|颗|只)(?![a-z])", re.I)
MULTIPLIER = re.compile(r"[×xX*]\s*(\d+(?:\.\d+)?)\s*(?:盒|袋|杯|瓶|包|份)?")
MONEY = re.compile(r"(?:小计|金额|总价)\s*[:：]?\s*[¥￥]?\s*(\d+(?:\.\d{1,2})?)(?!\d)")
APPROX = re.compile(r"约|不定重|大约|[~～]|\d+\s*[-–至]\s*\d+")
DATE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
HEAD = re.compile(r"^(?:合计|总计|支付|现金|找零|优惠金额|折扣金额|会员|单号|收银|电话|地址|欢迎|商品\s)")


def grouped_rows(lines):
    """Keep tokens and their order, grouping columns with overlapping vertical centres."""
    groups = []
    for token in lines:
        box = token.get("box") or [[0, token["order"] * 30], [100, token["order"] * 30 + 20]]
        ys = [point[1] for point in box]
        centre, height = (min(ys) + max(ys)) / 2, max(1, max(ys) - min(ys))
        match = next((g for g in groups if abs(g["centre"] - centre) <= min(g["height"], height) * .45), None)
        if match is None:
            match = {"centre": centre, "height": height, "tokens": []}
            groups.append(match)
        match["tokens"].append(token)
    for group in sorted(groups, key=lambda g: g["centre"]):
        tokens = sorted(group["tokens"], key=lambda t: min(p[0] for p in t.get("box") or [[0, 0]]))
        yield " ".join(t["text"] for t in tokens), tokens


def extract_fields(lines, min_confidence):
    items, evidence, problems = [], [], []
    purchased_on = None
    header_amount = False
    for text, tokens in grouped_rows(lines):
        found_date = DATE.search(text)
        if found_date:
            try:
                purchased_on = date(*(int(x) for x in found_date.groups())).isoformat()
            except ValueError:
                problems.append("invalid_date")
            continue
        if "商品" in text and "金额" in text:
            header_amount = True
            continue
        if HEAD.match(text.strip()):
            continue
        money = MONEY.search(text)
        if money is None and header_amount:
            money = re.search(r"\s(\d+\.\d{2})\s*$", text)
        amount = money.group(1) if money else None
        candidate = text[:money.start()] if money else text
        # Per-fruit size notes do not invalidate an explicitly printed total weight.
        sizing = re.sub(r"[（(]单果[^）)]*[）)]", "", candidate)
        measure, multiplier = MEASURE.search(sizing), MULTIPLIER.search(sizing)
        # An unrecognized row may be an item with every numeric field missing.
        # Keep it for review rather than silently dropping it from the receipt.
        reasons = []
        quantity = unit = None
        package_spec = measure.group(0) if measure else None
        approximate = bool(APPROX.search(sizing))
        negative = bool(re.search(r"退货|退款|[-−]\s*\d+(?:\.\d+)?\s*(?:kg|g|ml|l|个|颗|只)", sizing, re.I))
        packaged = bool(re.search(r"[/／]\s*(?:盒|袋|杯|瓶|包|份)|装", sizing))
        if negative:
            reasons.append("refund_or_negative")
        elif approximate:
            reasons.append("approximate_or_range")
        elif measure and packaged and multiplier is None:
            reasons.append("package_count_unknown")
        elif measure:
            try:
                quantity = Decimal(measure.group(1))
                unit = UNIT[measure.group(2).lower()]
                if multiplier:
                    count = Decimal(multiplier.group(1))
                    if count <= 0 or count != count.to_integral_value():
                        raise ValueError("Ambiguous package count")
                    quantity *= count
                target = {"kg": "g", "l": "ml"}.get(unit, unit)
                quantity = str(convert(quantity, unit, target))
                unit = target
            except Exception:
                quantity = unit = None
                reasons.append("quantity_invalid")
        else:
            reasons.append("quantity_missing")
        name = candidate.strip()
        if not approximate and not negative:
            name = re.sub(r"[（(]单果[^）)]*[）)]", "", name)
            # Keep '(3颗装)' as part of the product name, but remove ordinary size suffixes.
            name = re.sub(r"\d+(?:\.\d+)?\s*(?:kg|千克|公斤|ml|毫升|g|克|l|升)(?:[/／](?:盒|袋|杯|瓶|包|份))?", "", name, flags=re.I)
            name = re.sub(r"\d+(?:\.\d+)?\s*(?:个|颗|只|piece)(?!装)", "", name, flags=re.I)
        name = MULTIPLIER.sub("", name).strip()
        name = re.sub(r"[/／]\s*(?:盒|袋|杯|瓶|包|份)\s*$", "", name)
        name = re.sub(r"^\d{5,}\s+", "", name).strip()
        if len(name) > 80:
            reasons.append("name_truncated")
        name = name[:80]
        if not name:
            problems.append("name_missing")
            continue
        confidence = min(t["confidence"] for t in tokens)
        if confidence < min_confidence:
            reasons.append("low_confidence")
        if amount is None:
            reasons.append("amount_missing")
        try:
            item = ReceiptLine(name=name, quantity=quantity, unit=unit, amount=amount, uncertain=True)
        except ValueError:
            item = ReceiptLine(name=name, uncertain=True)
            reasons.append("field_validation_failed")
        items.append(item.model_dump(mode="json"))
        evidence.append({"item_index": len(items) - 1, "line_orders": [t["order"] for t in tokens],
                         "confidence": confidence, "package_spec": package_spec,
                         "purchase_count": multiplier.group(1) if multiplier else None, "issues": reasons})
        problems.extend(reasons)
    if not items:
        problems.append("no_items")
    return ParsedReceipt(purchased_on=purchased_on, items=items).model_dump(mode="json"), evidence, sorted(set(problems))
