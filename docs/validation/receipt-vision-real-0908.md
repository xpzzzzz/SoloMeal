# P7 首轮真实中文小票验收（2026-09-08）

用户提供 D:/SoloMeal-Acceptance/manifest.json 及三张授权图片，允许每张字段识别一次、隔离账号页面识别一次。已使用全部6次调用，无自动重试，无额外调用。沿用本项目私有配置，模型qwen3.8-flash，provider host dashscope.aliyuncs.com，prompt receipt-v1，30秒超时、4000输出token上限。没有更换模型、修改.env或修改原始标签。

## 结果

| 样本 | 第一次：字段脚本 | 第二次：真实页面识别 | 人工修正后页面闭环 |
|---|---|---|---|
| receipt-01 | 12.830s，RECEIPT_PARSER_FAILED；当次未保留底层原因，不能认定为401 | parsed，全部字段匹配，所有行待核对 | 9批次通过 |
| receipt-02 | 30.012s，外层超时，报告VISION_ACCEPTANCE_ERROR | failed；适配器底层HTTPStatusError/401，API自身返回已保存失败状态200 | 手工补录6批次通过 |
| receipt-03 | 23.453s，30/34字段匹配，所有行待核对 | parsed，日期与第4行名称/数量/单位共4个字段不匹配，所有行待核对 | 修正8批次通过 |

第三张页面结果将日期识别为2026-08-17，与用户note中的最终人工日期一致，但原始expected为null；因此该差异不能直接认定为幻觉。黄瓜名称包含票面“不定重”前缀，输出1kg，而原expected数量/单位为null；这是约重语义需要明确的边界。首轮脚本只保留字段计数，不能声称首轮的4处差异与第二轮逐项相同。

用户在本轮明确接受票面约重用于库存；云南高原生菜按3包×约450g=1350g修正，其他数量按用户标签及note。此为用户接受的估计值，不是实称结果。原manifest保留450g及其SHA256，不为通过修改答案；修正依据保存在样本目录confirmed-corrections.json。后续识别评分应区分票面标示量、约重、实际入库量，并在下一轮前冻结规则，不能追溯修改本轮得分。

## 页面与数据库证据

一次性Playwright脚本通过真实React页面上传、发送前两步确认、鉴权原图加载、人工修正/保存和两步入库；使用真实VisionReceiptParser，未用脚本模型替代。每张独立账号，数据库和上传目录位于D:/SoloMeal-Acceptance/live-isolated-run1，SQLite仅用于本轮UI闭环，不作为MySQL并发证据。

- 各账号确认前库存为0；页面第一次识别确认按钮未发起模型调用。
- 原始合法解析与人工草稿分开保留；识别失败仍可手工补录。
- 确认模拟服务端提交后响应丢失；再次点击使用相同Idempotency-Key，批次列表完全一致，事件不重复。
- 最终9+8+6=23批次、23库存事件；按食材逐项核对kg→g换算和数量，刷新重登录后完成状态恢复。购买日期保留于小票草稿，到期日期保持未知。
- 首张辅助脚本曾错误断言库存响应存在purchased_on字段；该断言失败前确认/丢包重试/数量核对已执行。修正为核对小票draft日期，重新读取已完成状态，无新增模型调用、上传或确认。
- 三张完成页面截图已本地复核。原图、原始解析、账号及截图不复制进仓库；仅复制脱敏指标报告。

## 复现与限制

字段命令（已执行，不得无授权重跑）：backend/.venv/Scripts/python.exe scripts/validate_receipt_vision.py --manifest D:/SoloMeal-Acceptance/manifest.json --report D:/SoloMeal-Acceptance/vision-fields-run1.json --send-images。

本地一次性服务D:/SoloMeal-Acceptance/live_server.py；浏览器脚本frontend/.tmp-e2e/live-receipt-acceptance.mjs。脚本在发送前持久化每张尝试次数，并在恢复时读取已有receipt状态，首张辅助断言修正没有再次调用。执行完关闭浏览器与本轮127.0.0.1:8027服务，保留隔离数据库作为本地验收证据。

真实票据用户修正/入库/重试闭环已通过；真实识别整体未通过。第二张两次分别超时/401，约重和字段标签规则仍需复核。首张第二轮成功不能抹除首轮失败。本轮没有新运行MySQL专项、业务全量或远程CI，不以历史自动测试充当本轮实测。模型token使用和实际费用未由当前报告采集，不提供猜测数字。

下一步：先无外部调用地整理提供方错误诊断与约重标注规则；需要验证提供方可用性或重跑效果时，说明具体次数后取得新的调用授权。P7仍IN_PROGRESS，P8/P9未开始。
