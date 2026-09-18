# 2026-09-13 第66节独立审阅

审阅结论：库存日期序列化修复正确，评测子集205项已独立复跑通过，但不能据此认定留出全链路已按冻结契约完成。发现以下三个需要在真实批次登记前修正的问题。本次只审阅，未改生产/评测源码，未登记或外发模型请求。

## P1：夹具及客观判据偏离冻结契约

`backend/scripts/evaluate_agent.py:100–108` 与 `evaluation/README.md` 的夹具契约不一致：

| 夹具 | 冻结定义 | 当前实现 |
|---|---|---|
| expiry / A021 | 大米100g过期、100g今天到期、100g无日期；鸡蛋沿用standard | 大米150g过期、200g七天后到期；鸡蛋也改为七天后到期 |
| stale_quotes / A027 | quoted的两种报价均改为D−31；大米与鸡蛋均无库存 | 大米50g、无鸡蛋库存；只有大米过期报价 |

A021题目要求区分快到期和过期食材，当前数据没有快到期批次，也未覆盖无日期边界。`read_check`反而要求fresh=200g/expired=150g。将冻结的三个100g批次传入此判据，实际返回False。说明测试和判据一起迁就了新夹具，205项通过不能证明冻结契约得到执行。A027也丢失鸡蛋的过期报价，改变了缺料量及价格来源证据。注入步骤文字同样与README逐字内容不同，恢复契约时应一并核对。

修正方向：恢复冻结夹具和对应判据，并增加直接验证冻结数量、日期、报价种类/日期的测试；如确需修改契约，沿用事前独立amendment，不以“冻结文件未改”代替执行一致性证明。

## P1：holdout_gate无法达到passed

`backend/scripts/cohort_metrics.py:193–201` 将所有模式的全部门槛合并。fixed_workflow的hard_constraints又只读取review中的constraint_pass；`review_agent.py:109–111`明确禁止给固定流程填写任何语义评分，因此固定流程必定保留60个硬约束missing。

离线构造完整180个位置：所有适用任务成功、参数与写入正确、无未授权写入、延迟合格、模型模式真人清晰度5分，固定流程按合法评审规则保持constraint_pass=null。实际结果agent_tools.task_success.status=passed，而fixed_workflow.hard_constraints.status=incomplete、holdout_gate=incomplete。该阻塞不能通过增加真实调用或补人工评审消除。

修正方向：明确应用验收与对照指标的作用范围；为固定流程提供符合冻结规则的客观硬约束证据，或明确其不适用并独立汇报。不能直接伪造语义评分true。补完整成功、真实失败、缺失三类聚合回归。

## P2：清晰度使用了未冻结的统计量

`backend/scripts/cohort_metrics.py:184` 使用min≥4，冻结README明确均值≥4。离线输入[3,5]按冻结均值为passed，当前实现为failed。更严格也属于改变已冻结判定方式；第66节已披露此限制，但正式跑批前仍应解决。恢复mean，保留完整性检查，不改冻结门槛值。

## 已核实与边界

- 后端app/scripts共60文件，SHA256确为`2cdd1681d65bc714695268fe2af49006059358fe3056148ddc9c7ae1c3867ce1`。
- 独立复跑六个评测相关测试文件：205 passed，116.61秒，2个既有弃用警告。测试路径为test_agent、test_agent_evaluation、test_agent_cohort、test_cohort_metrics、test_evaluation_measurements、test_tool_protocol；专用basetemp `.tmp-pytest-independent-review-66`，禁用pytest缓存。
- `food.batch_view`将日期转为ISO字符串与REST原有编码结果一致，工具边界回归通过；没有发现此修复引入新问题。
- 没有独立重跑完整401/16后端、MySQL、浏览器或真实模型，原完整结果为第66节报告值。本次未核验提供方现价，不把其费用外推当账单。
- 旧`.tmp-context-v19-*`脚本保留，未删除；本次没有执行它们或旧manifest。

下一步先修正上述离线问题并回归，再按修正后的新源码哈希登记调试/留出批次。P8/P5继续未完成，旧证据与第66节原报告保留。
