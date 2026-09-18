"""Render recommendation facts and next steps from server-owned tool results."""

UNITS = {"g": "克", "ml": "毫升", "piece": "个"}
REASONS = {
    "TIME_LIMIT": "用时超过限制", "MISSING_EQUIPMENT": "缺少所需厨具",
    "EXCLUDED_INGREDIENT": "含排除食材", "BUDGET_EXCEEDED": "补购超过预算",
}


def cooking_availability(candidate):
    # Both fields must agree; unknown or inconsistent state never enables a preview.
    if candidate.get("can_cook_now") is not True or candidate.get("shopping") != []:
        return {"enabled": False, "reason": "INSUFFICIENT_STOCK",
                "message": "先购买缺料并确认入库，再重新查询；当前不能生成做饭预览。"}
    if candidate.get("budget_status") not in ("not_requested", "within_estimate"):
        return {"enabled": False, "reason": "BUDGET_UNVERIFIED",
                "message": "预算尚未通过校验，当前不能生成做饭预览。"}
    return {"enabled": True, "reason": None,
            "message": "可选择这道菜请求做饭预览；预览和确认时仍会重新校验库存与条件。"}


def quantity(line, key):
    return f"{line[key]}{UNITS.get(line['unit'], line['unit'])}"


def render(result):
    """Do not splice unrestricted model prose into a verified recommendation."""
    conditions = result["constraints"]
    lines = [f"本次推荐：{conditions['servings']}人份，用时上限{conditions['max_minutes']}分钟。",
             "厨具：" + "、".join(conditions["equipment"]) + "。",
             "生效排除食材：" + ("、".join(conditions["excluded_ingredients"]) or "无") + "。"]
    if conditions["budget"] is not None:
        lines.append(f"补购预算：{conditions['budget']}元。")
    actions = []
    for candidate in result["candidates"]:
        recipe = candidate["recipe"]
        availability = cooking_availability(candidate)
        actions.append({"recipe_id": recipe["id"], "servings": candidate["servings"],
                        "include_optional": candidate["include_optional"],
                        "prepare_cooking": availability})
        lines.append(f"{recipe['name']} · {candidate['servings']}人份 · {recipe['minutes']}分钟")
        lines.append("本餐用量：" + "；".join(
            f"{item['name']} {quantity(item, 'quantity')}" for item in candidate["required_ingredients"]))
        if not candidate["shopping"]:
            lines.append("查询时库存足够。")
        for item in candidate["shopping"]:
            lines.append(f"缺{item['name']} {quantity(item, 'missing_quantity')}。")
            if item["price_status"] == "estimate":
                lines.append(f"整包补购：{item['packages']}包，共{quantity(item, 'purchase_quantity')}，"
                             f"预计{item['estimated_cost']}元。")
            else:
                lines.append("补购价格未知或报价过期，不能保证预算；购买规格需核对。")
            if item.get("source"):
                lines.append(f"报价来源：{item['source']}；日期：{item['observed_on']}。")
        lines.append(availability["message"])
    if not result["candidates"]:
        lines.append("没有符合当前条件的候选。可明确调整时间、人数、厨具或预算后重新查询。")
    reasons = sorted({reason for row in result["rejected"] for reason in row["reasons"]})
    if reasons:
        lines.append("未入选原因（按各菜谱记录）：" + "；".join(REASONS.get(r, r) for r in reasons) + "。")
    lines.append("以上是查询时的建议，未预留库存，也未创建待确认操作。")
    return {"message": "\n".join(lines), "response_source": "recommendation-response-v1",
            "next_actions": actions}
