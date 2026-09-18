# P8约束与真实确认闭环

2026-09-09。执行器从3个调试场景扩展为8个：A001～A005、A010～A012。新增厨具、两人份、入库、做饭与撤销；预算、反馈等其余调试和全部留出尚未执行。P8/P5仍IN_PROGRESS。

## 场景和评分边界

A005首次运行前发现原oracle与standard夹具矛盾：库存300g大米和2个鸡蛋，两份只需160g大米、最多2个鸡蛋，因此应允许报告足够库存。新增evaluation/amendments-v1.1.json和freeze-v1.1.json，在首次A005模型调用前记录修正及哈希；原100场景与freeze-v1.json未改，没有修改旧模型成绩。报告明确oracle_version=A005-v1.1。

新增one_cook夹具先通过API做一份白米饭，库存220g、唯一completed记录；撤销后的API状态为retracted，不重命名为undone。A004必须实际传入电饭锅约束；A005必须传入两人份并核对三种菜谱的份数/缺料结果。

A010～A012原场景仅要求正确预览、批准前不写。新增`--confirmation approve|cancel`是独立扩展，默认none；只有预览oracle通过且业务快照未变，评测器才模拟明确批准/取消。错误目标/数量不自动批准，直接模型模式不能执行确认。三种写操作的固定流程参照使用已知结构化意图驱动同一runtime，属于无LLM基线，不冒充自然语言能力。

report.json中的business_unchanged明确仅指确认前，最终库存/事件差分在confirmation_extension独立记录。确认重复使用同一Idempotency-Key，比较响应及数据库快照，避免只看总量掩盖重复操作。elapsed_seconds是生成预览或读取结果的耗时，不是包含确认后的完整任务时延。

## 真实结果与失败

本轮21次聊天请求，21份usage，观察total_tokens合计86532；没有价格/账单信息，成本为null。历史聊天41次、视觉30次另存；本轮视觉0次。[指标JSON](p8-confirmation-debug-0909.json)仅保留脱敏记录；原始响应及完整快照在D:/SoloMeal-Acceptance/p8-a004/a005及a010～a012对应新目录。

| 场景/扩展 | 请求 | 结果 |
|---|---:|---|
| A004电饭锅约束 | 4 | 通过，实际过滤炒锅菜谱 |
| A005两人份 | 3 | 按v1.1勘误通过；实际两人份、无缺料 |
| A010批准入库 | 2 | 大米300→500g，1个新增库存事件，同键重放不再加 |
| A011批准做饭 | 2 | 大米300→220g，1个新增库存事件、1条completed用餐 |
| A012批准撤销 | 2 | 大米220→300g，1个新增库存事件，用餐变retracted |
| A010取消 | 2 | 大米仍300g，事件不增加 |
| A011取消首轮 | 2 | 响应解析失败，未执行取消/批准，库存不变 |
| A012取消 | 2 | 大米仍220g、用餐completed，事件不增加 |
| A011取消独立复验 | 2 | 新协议下通过，大米仍300g，事件不增加 |

所有成功预览前业务快照均未变；批准和取消的同键重放均通过。本轮是实际外部模型配合真实后端API（TestClient）、合成账号和临时SQLite，不是浏览器/真机/MySQL并发验收；确认由测试驱动器模拟用户明确点击，不能称真人试用。对照基线由自动测试覆盖，未新增直接模型付费对照或人工评分。

首轮A011取消在查询库存后，模型返回`kind=historical_tool_calls`及`arguments_raw`，与v1历史展示格式一致，而非协议允许的tool/final格式。严格解析正确拒绝，失败和原始响应保留，没有为了通过而接受该格式。

改为json-tools-v2：合法历史assistant工具调用序列化成与当前输出相同的tool对象；JSON参数类型原样保留。非法历史参数作为标注的数据消息保留，不放进assistant示例，也不修复/强转。应用中存储的消息不变。新版本A011取消一次复验通过；其他本轮真实路径使用v1，不能汇总为v2同配置全部通过，也不能据此声称响应错误已经清零。下一轮使用v2继续验证。原生协议仍默认，.env未修改。

## 工程验证

backend目录最终：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_tool_protocol.py tests/test_model_transport.py tests/test_agent.py tests/test_agent_evaluation.py tests/test_evaluation.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-p8-write-v2-final-0909 -q
.venv/Scripts/python.exe -m ruff check scripts/evaluate_agent.py app/services/tool_protocol.py tests/test_agent_evaluation.py tests/test_tool_protocol.py --select F,B,I
```

最终79 passed（32.42秒）、ruff通过，2条既有第三方弃用警告。前序42、78、43是中间结果，不相加。新增覆盖5场景、3种确认选择、错误数量不得批准、直接模型禁止确认，以及合法/非法历史表示和类型保持。

仓库根目录复现示例（输出目录须不存在）：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --scenario A011 --mode agent_tools --tool-protocol json --confirmation approve --send-model --output D:/SoloMeal-Acceptance/p8-cook-NEW
```

下一步A006/A007预算、A008/A009缺参数、A013歧义撤销、A014忌口、A015反馈、A016旧快照、A017恶意内容、A018不支持操作、A019方案取消、A020故障。再统一冻结v2配置跑调试/留出与三模式3重复，补人工评价和MySQL/浏览器证据。

未改业务事务或迁移、前端、原插件，未跑MySQL/完整backend/浏览器/远程CI，未修改开发库/根data/.env，未提交推送。
