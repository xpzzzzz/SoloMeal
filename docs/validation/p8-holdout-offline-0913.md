# 2026-09-13 留出（A021～A040）离线链路补齐

承接 STATUS 第65节：本轮把“登记 → 执行 → 审计 → 评审 → 聚合”的留出支持全部补到可执行状态，并只做事离线验证。新增模型外发 0、真实数据库 0、新登记批次 0；所有试次都在 pytest 的隔离 SQLite 内完成，`--basetemp` 专用目录已删除。

## 本轮实际改动

- `scripts/cohort_agent.py`：`SPLITS=("debug","holdout")`，`slots(directory, split)` 按冻结 split 取场景，`register(config, directory, output, split)` 与 CLI `--split` 必填，`load_plan` 对缺 `split` 的归档 v3 manifest 按 debug 解释（旧批次仍可复审），`slot_confirmation` 与 `audit` 携带 split。`CONFIRMATION_SCENARIOS` 分开登记：debug 为 A010/A011/A012，holdout 为 A030/A031/A033。已验证每个 split 仍是 20 场景 × 3 模式 × 3 重复 = 180 位置，顺序与冻结标签一致。
- `scripts/evaluate_agent.py`：执行器改从数据集读取 `split`，不再固定 debug；留出三类新增范围——读取型（A021/A022）、规划型（HOLDOUT_PLANNING：A023/A024/A026/A027 等，含 A025/A034 忌口、A037 注入、A028/A029/A032/A038 澄清）、写入与时序（A030 单位换算、A031 两份做饭、A033 只撤销较早记录、A035 两轮条件继承、A036 外部消耗后旧快照批准必须拒绝、A039 取消、A040 模型故障恢复）。`STALE_APPROVAL`、`CANCELLATION_CASES`、`REQUESTED_QUANTITY`、`PENDING_QUANTITY`、`COOKING_SERVINGS`、`COMMITTED_DELTA` 扩展至 A030/A031/A033/A036/A039。CLI 对未登记的“场景 × split”确认扩展直接拒绝，`direct_model` 不得搭配确认扩展。A036 的题干外部做饭以显式 driver 写入执行，因而既真实消耗库存，又不被计入未授权业务 DML。
- `scripts/cohort_metrics.py`：版本升到 `solomeal-cohort-metrics-v3`，输出新增 `gates`、按模式的 `holdout_gate` 与 `task_success.status`；留出用完整分母判定 85% 门槛，缺失/中止绝不变成通过；debug 聚合格式变更不回填 v2 归档摘要，scope 文本区分“调试指标”与“合成留出、无独立真人评审”。
- `scripts/evaluation_measurements.py`：写入正确性范围明确为“已批准预览的写入 + 数量 + 历史 + 重放 oracle”，仅批准路径产生该证据；取消路径为“无该测量”，不是失败也不是通过。
- `app/services/food.py`：`batch_view` 的 `expires_on` 改为 `.isoformat()`。这是本轮发现的真实缺陷，不是评测脚手架问题——带保质期的库存此前在 `get_inventory` 工具边界 `json.dumps` 失败，被统一吞成 `MODEL_PROTOCOL_ERROR`，A021 因此不可能达成；REST 层因 FastAPI `jsonable_encoder` 掩盖了同一缺陷。HTTP 响应字段值不变，与 `planning.py`、`agent_actions.py` 既有约定一致。`tests/test_agent.py` 补一条应用级回归，断言工具边界结果与 REST 视图给出同一个 ISO 字符串。

验证方式（观测项）：冻结数据集、协议与三份 amendments 未改；`AGENTS.md`/`CLAUDE.md` 的 v19 段落未改；`backend/app` 与 `scripts` 的改动只涉及上述文件；`git status` 与本轮开始时一致，无新增 tracked 变更。推断项：留出提示被实现方读过这一点，属于对过程的评价，不是从代码可导出的事实。

## 离线回归与自检

- 完整 backend 套件：401 通过、16 跳过、289.98 秒。16 项跳过全部是 MySQL 门控用例（Docker 守护进程未运行，本轮未启动它）；不以 SQLite 结果冒充 MySQL 并发证据。
- 评测相关子集单跑：205 通过（`test_agent`、`test_agent_evaluation`、`test_agent_cohort`、`test_cohort_metrics`、`test_evaluation_measurements`、`test_tool_protocol`）。`test_agent_evaluation.py` 共 94 项，其中留出块 42 个用例节点。
- ruff（对改动文件、`--select F,B,I`，与历史轮次同一命令形态）通过。整树 ruff 仍报 116 项 `app/api/*` 的 B008 与 1 项既有 B905，属 FastAPI `Depends` 惯用法的历史基线，本轮未扩大范围处理。
- 首轮结果不是全绿：留出确认扩展用例曾断言“取消也算写入正确性失败”，实际测量设计对取消不产出该证据，已按设计修正断言并保留说明注释；`test_cohort_metrics`、`test_evaluation_measurements`、`test_tool_protocol` 三处旧签名（无 `--split`、手搓 case 字典、三项 `measured_gates`）随之更新。
- 留出检查被判别力自证：读路径在 native 与 json 两种传输下比对同一批行；仅口头声称结果而无工具调用不算通过；规划证据 5 类改写与虚构成本必须失败；A030 预览按服务端换算量判定，250 g 与 0.25 kg 通过、250 kg 与 0.25 g 拒绝；A033 只撤销较早记录、另一条保持完成；A039 取消后库存快照不变；A040 恰好一次合成无请求故障、一次保留的 failed 转换、一次读取事件、3 步。

## 必须与结论一起读的限制

1. 留出是合成集且已被实现方阅读：为编写客观判据，本轮读取了 A021～A040 的提示与 fixture 定义，因此它不是对开发者盲测的泛化样本。
2. 多轮逐字提示由 harness 拟定：冻结数据对 A015、A035 只给一行压缩描述，两个轮次的中文原文由执行器补写（A015 早已如此，A035 沿用同一做法），结构上等价但非冻结逐字。
3. 清晰度门槛按更严方向落地：`clarity_human_score_min` 以“最小值 ≥ 4”聚合，而冻结 README 写的是“均值 ≥ 4”。这只会更难通过，不会造成假通过，但与 README 字面不同，正式验收前需要确认口径。
4. 没有真人评审：Codex 语义分不冒充人工清晰度，留出与调试的真人清晰度目前都是 null。
5. 门槛状态仍为未测量：本轮 0 外发，留出 85% 任务成功率、硬约束 100%、P95 等全部无新数据；不得用调试集 95.00% 代替留出验收。

当前 Agent v19 / direct v1，工具 schema、SYSTEM 正文、JSON 协议、业务权限均未变；提交 HEAD 仍 `a923d77c7c281f2fcd165a71ad062f1ec0d851bc`；后端源码指纹 `2cdd1681d65bc714695268fe2af49006059358fe3056148ddc9c7ae1c3867ce1`（60 个文件，上一版 `ec7c27702426f689096b69d52b795ee734e59662f6b0f11068953532f10fbcaa`）。

## 下一步

1. 先给成本估算（请求数、token、墙钟），由用户决定是否执行：新登记并运行 20 调试三模式 180 位置统一重复（`--split debug`，approve 仅 A010～A012）。
2. 再登记并运行 20 合成留出 180 位置（`--split holdout`，approve 仅 A030/A031/A033），随后独立审计、评审与 v3 聚合。
3. 旧 v16/v13/v12 manifest 与其私有目录一律不重跑、不追加；失败不回填。MySQL 七场景、完整 P4～P6、浏览器与真人清晰度、新小票留出、真人试用及 P9 部署/备份范围不变，PLAN 正式范围不删减。未改 `.env`、开发库、根 `data`、迁移与原插件；无提交推送。
