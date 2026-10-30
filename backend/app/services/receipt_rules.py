"""Conservative extraction of explicit quantities; confidence never creates a number."""
import re
import unicodedata
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
FOOT = re.compile(r"^(?:商品(?:合计|总计)|原价[:：]|优惠[:：]|应收[:：]|实付[:：]|"
                  r"(?:优惠|订单)(?:总额|金额|明细|合计)|合计|总计|支付|现金|找零|活动优惠|社群福利|小红书)")
CODE = re.compile(r"^[A-Za-z]?\d{6,20}$")
NUMBERED = re.compile(r"^\s*\d{1,3}[.、．]\s*(?=[^\d\s])")
PURCHASE = re.compile(r"^\s*(?:[×xX*]\s*)?(\d+(?:\.\d+)?)\s*[（(]")
DECIMAL_MONEY = re.compile(r"\d+\.\d{2}")


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


def table_header(text):
    return bool(re.search(r"品名|商品", text) and re.search(r"金额|小计", text)
                and not re.search(r"\d", text))


def price_boundary(tokens):
    prices = [t for t in tokens if re.search(r"单价|小计|金额", t['text'])
              and not re.search(r"品名|商品", t['text'])]
    others = [t for t in tokens if t not in prices]
    if not prices or not others or any(not t.get('box') for t in tokens):
        return None
    left = min(min(x for x, _ in t['box']) for t in prices)
    previous = [max(x for x, _ in t['box']) for t in others
                if max(x for x, _ in t['box']) < left]
    return (max(previous) + left) / 2 if previous else left


def table_columns(text, tokens, boundary):
    """Read explicit right-hand subtotals; never calculate price times count."""
    right = [t for t in tokens if boundary is not None and t.get('box')
             and min(x for x, _ in t['box']) >= boundary
             and re.fullmatch(r"[-−]?\s*[¥￥]?\s*(?:\d+\.\d{2}\s*)+", t['text'].strip())]
    left = ' '.join(t['text'] for t in tokens if t not in right).strip()
    if right:
        values = [m.group() for t in right for m in DECIMAL_MONEY.finditer(t['text'])]
        return left, values[-1] if values else None
    if MONEY.search(text):
        return text, None
    # Whole-row OCR boxes need a text fallback. Exclude decimals inside weight
    # specifications and unit-price parentheses; glued columns such as 3.962.68
    # still contain two explicit two-decimal numbers.
    measures = list(MEASURE.finditer(text))
    values = [m for m in DECIMAL_MONEY.finditer(text)
              if not any(a.start() <= m.start() < a.end() for a in measures)]
    if values and values[-1].end() == len(text.rstrip()) and '元/' not in text and '元／' not in text:
        return text[:values[0].start()].strip(), values[-1].group()
    return left, None


def logical_rows(rows):
    """Assemble a bounded product block from a detected receipt table.

    SKU or numbered-name rows start blocks. A purchase/weight row continues
    its preceding name; standalone discount rows never become products.
    Without a recognized table, preserve the original name-only fallback.
    """
    header = next((i for i, (text, _) in enumerate(rows) if table_header(text)), None)
    if header is None:
        for text, tokens in rows:
            if not DATE.search(text) and not HEAD.match(text.strip()):
                yield text, tokens
        return
    boundary = price_boundary(rows[header][1])
    parts, evidence, amount = [], [], None
    complete = False

    def assembled():
        value = ' '.join(parts)
        return (value + (' 小计' + amount if amount is not None else ''), evidence[:])

    for text, tokens in rows[header + 1:]:
        text = text.strip()
        if FOOT.match(text):
            break
        if table_header(text):
            boundary = price_boundary(tokens)
            continue
        if DATE.search(text) or HEAD.match(text):
            continue
        if CODE.fullmatch(text):
            if parts:
                yield assembled()
            parts, evidence, amount, complete = [], tokens[:], None, False
            continue
        left, subtotal = table_columns(text, tokens, boundary)
        purchase = PURCHASE.match(left)
        if purchase:
            left = '×' + purchase.group(1)
        elif not re.search(r"[A-Za-z\u3400-\u9fff]", left):
            # Includes negative discounts and discounts whose minus was missed.
            continue
        if not left:
            continue
        is_name = bool(re.search(r"[A-Za-z\u3400-\u9fff]", MEASURE.sub('', left))) and not purchase
        if parts and (NUMBERED.match(left) or (complete and is_name)):
            yield assembled()
            parts, evidence, amount, complete = [], [], None, False
        parts.append(NUMBERED.sub('', left))
        evidence.extend(tokens)
        if subtotal is not None:
            amount = subtotal
        complete = complete or purchase is not None or subtotal is not None or MONEY.search(left) is not None
    if parts:
        yield assembled()


def extract_fields(lines, min_confidence):
    items, evidence, problems = [], [], []
    purchased_on = None
    rows = list(grouped_rows(lines))
    for text, _ in rows:
        found_date = DATE.search(text)
        if found_date:
            try:
                purchased_on = date(*(int(x) for x in found_date.groups())).isoformat()
            except ValueError:
                problems.append("invalid_date")
    for text, tokens in logical_rows(rows):
        money = MONEY.search(text)
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
        name = unicodedata.normalize('NFKC', candidate).strip()
        name = NUMBERED.sub('', name)
        if not approximate and not negative:
            name = re.sub(r"[（(]单果[^）)]*[）)]", "", name)
            # Keep '(3颗装)' as part of the product name, but remove ordinary size suffixes.
            name = re.sub(r"\d+(?:\.\d+)?\s*(?:kg|千克|公斤|ml|毫升|g|克|l|升)(?:[/／](?:盒|袋|杯|瓶|包|份))?", "", name, flags=re.I)
            name = re.sub(r"\d+(?:\.\d+)?\s*(?:个|颗|只|piece)(?!装)", "", name, flags=re.I)
        name = MULTIPLIER.sub("", name).strip()
        name = re.sub(r"[/／]\s*(?:盒|袋|杯|瓶|包|份)\s*$", "", name)
        name = re.sub(r"^\d{5,}\s+", "", name).strip()
        name = re.sub(r"\s+", ' ', name)
        if approximate:
            name = re.sub(r"\s*(约(?=\s*(?:\d|kg|g|ml|毫升)))", r" \1", name).strip()
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
