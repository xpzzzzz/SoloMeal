# SoloMeal Mem0 优化后验收报告

2026-10-28（Asia/Shanghai）。无候选跳过、真实记忆参与推荐和合成数据清理在本次受控环境中通过；**真实 MySQL 并发与行锁验收未执行，因此不能宣称全部验收通过**。本轮真实 Mem0 共 **8 次 HTTP 请求**，没有真实 Agent 模型调用、自动重试、部署、提交或推送。

## 环境与安全检查

- 本轮沿用用户此前确认的独立 Mem0 测试项目。私有密钥配置非空，文件时间未晚于第五阶段实验，进程未用其他密钥覆盖；项目隔离依据用户确认和先前实验记录，本轮未额外发送 ping。常规应用 Mem0 开关保持关闭，仅独立测试进程启用。
- 新建独立 SQLite 与随机合成账号、菜谱、食材和报价；测试数据保存在独立的本机实验目录，没有使用生产账号或改动现有数据库。预检七个既有合成实验数据库的记忆操作，`unknown/pending/mutating` 汇总为 0；新数据库在写入前也无未决记忆操作。此检查不声称审计了所有生产数据库。
- 使用应用实际 `MemoryProvider` 和确认 API；建议由已有 Scripted 测试模型生成，用户确认内容与服务端建议核对后才写入。当前 HTTPX 默认**阶段超时 2 秒**，没有改为 10 秒。只写入并删除一条本轮合成记忆。
- 新增实验专用 受限运行器（保存在本机）和[脱敏证据](mem0-final-validation-evidence.json)：运行器按固定顺序限制最多 8 次远端请求，预留清理和复查额度；未知写入、中断或异常时停止，不盲目重发。证据只保存计数、固定分类和耗时，不含密钥、用户 ID、请求正文或记忆内容。实验 SQLite 和原始合成记录检查点留在独立本机目录，不入报告。
- 先执行 MockTransport 预演验证了完整流程和八次上限；预演不是本节真实服务结果。真实流程独立执行一次。

## MySQL 并发验收：阻塞

当前进程没有配置 `SOLOMEAL_TEST_DATABASE_URL`。只读检查发现运行中的 MySQL 属于现有 SoloMeal 应用或其他项目，未发现可确认的独立测试实例。`backend/tests/conftest.py` 会对测试 schema 反复降级和升级，不能仅凭库名就把现有服务视为可破坏的隔离环境。本轮没有启动或部署数据库，也没有使用现有应用数据库执行测试。

**真实 MySQL：0 项已执行、0 项通过、0 项失败；以下项目均为未执行/阻塞，不是通过：**方案并发确认、方案取消与确认竞争、Agent 会话并发续接、Agent 在释放锁后读取记忆并重新获取锁/复核租约与候选，以及记忆重复确认、状态更新和未知状态抑制在 MySQL 上的行为。`150 通过、3 跳过` 是下面的 SQLite 离线结果，不是 MySQL 结果。

## 无可行候选：零搜索

固定测试使用原规划器与原先“先读记忆”调用顺序作为基线，并用 MockTransport 统计实际应用请求：忌口、时间、厨具和已知预算分别排除全部候选时，新路径各 **0 次**搜索；旧顺序各 **1 次**。四组完整响应相同，涵盖候选、分数、排序、理由、约束和拒绝原因，合计少 4 次 Mock HTTP。预算未知但仍有候选时仍读取记忆；空、无关、重复和冲突记忆以及未知操作状态的可行候选测试保持现有结果。401、422 和他人报价 404 的校验继续生效。

真实流程中的场景 A 使用该次新合成用户及固定硬约束，以空厨具令所有菜不可行：应用 API **200、候选 0、远端搜索 0 次、TestClient 总耗时 33.205 ms**。本次实际 Provider 请求计数器未记录请求，也没有被守卫阻止的意外请求。由于当前诊断只在读取记忆或未知操作时输出，本次零候选请求没有诊断日志，**零请求结论来自受控 Provider 计数器，而非把缺失日志当成证据**。

## 有可行候选：真实检索与推荐

通过认证及确认流程写入一条合成食材正向偏好：确认 API 成功，真实 Mem0 ADD 为 HTTP 200、`status=SUCCEEDED`，本地确认记录为 `saved`。随后发起独立推荐请求：

| 指标 | 本次实际结果 |
| --- | --- |
| 推荐 API / 可行候选 | 200 / 2 道 |
| 本次推荐的真实搜索 | 1 次，HTTP 200，返回 1 条；归属校验通过 |
| 偏好菜原始分 / 记忆分 / 最终分 | 0 / +3 / 3 |
| 排序与理由 | 偏好菜 Top-1；理由与已确认的合成食材和正向偏好一致 |
| 硬约束 | 分别拒绝忌口、超过时间、缺少厨具和已知预算超限的合成菜；返回候选均通过该夹具约束 |
| 降级、超时、未知状态 | 无；默认阶段超时下本次全部成功 |

该案例验证了真实搜索返回的结构化偏好能够参与现有评分；没有以 Fake 记忆补入真实请求。这只是一个固定合成案例，不证明一般推荐质量提升。真实服务本轮只使用一个合成账号，没有再次做第二用户越权试验；本地的认证/跨用户和抑制测试通过，先前真实跨用户结果见[冒烟报告](mem0-live-smoke-report.md)，不能把历史结果写成本轮新观测。

## 时延、连接与请求数

本次 TestClient 计时包含本地应用、SQLite 和受限运行器；运行器在远端调用前后写入合成检查点，该本地写盘会计入 TestClient/ASGI 请求总时间，但不计入表中的 HTTP 包装时间。以下阶段相互嵌套，不能相加；均是客户端测量，不是 Mem0 服务端处理耗时。

| 项目 | 耗时 ms |
| --- | ---: |
| A 无候选 TestClient 请求 | 33.205 |
| B 有候选 TestClient 请求 | 581.103 |
| B 应用 ASGI 请求 | 579.981 |
| B `read_memories()` | 556.398 |
| B 搜索 HTTPX 请求 | 553.627 |
| B 搜索外层包装 | 553.703 |
| B JSON 解码 / 结构转换 / 本地抑制 / 候选记忆评分 | 0.032 / 0.030 / 1.434 / 0.018 |
| 删除后再推荐 TestClient / 记忆读取 / 搜索 HTTPX | 584.293 / 560.596 / 559.532 |

| 次序 | 真实 Mem0 操作 | HTTP | 包装耗时 ms | TCP / TLS 启动事件 |
| --- | --- | ---: | ---: | --- |
| 1 | 新增 | 200 | 2465.987 | 1 / 1 |
| 2 | 有候选推荐搜索 | 200 | 553.703 | 0 / 0 |
| 3 | 清理前管理列表 | 200 | 495.579 | 0 / 0 |
| 4 | 删除前单条归属读取 | 200 | 517.219 | 0 / 0 |
| 5 | 删除时列表核对 | 200 | 500.646 | 0 / 0 |
| 6 | 删除前再次单条归属读取 | 200 | 508.263 | 0 / 0 |
| 7 | 删除 | 200 | 697.318 | 0 / 0 |
| 8 | 删除后推荐搜索 | 200 | 559.583 | 0 / 0 |

八次均观察到 HTTP/1.1 请求头发送，首次建立 TCP/TLS，后七次没有新的建立事件；本次序列与连接复用一致。没有保存或输出完整 URL、认证头及网络地址。首次新增的 2465.987 ms 是包装墙钟，超过 2 秒仍成功：阶段超时不等于单次 HTTP 的端到端总时限。没有探测真实超时概率、DNS 分解或 Mem0 服务端处理时间。

历史第五阶段 B 组推荐中位数约 **1443.30 ms**，第八阶段五次热连接的 `read_memories()` 中位数约 **552.09 ms**；本次 B 是单次 **556.398 ms** 记忆读取、**581.103 ms** 整个 TestClient 请求。用户、数据、记录方式、搜索结果和运行时间均不同，不能当作严格的优化前后或统计性对照；A 与 B 条件也不同，不能用两者差值直接归因于记忆。服务端耗时、Token、模型用量和可确认实际费用均为**未知**，不是零。

## 清理与记忆状态

删除前，管理列表中只有本次创建的合成记忆，ID、内容和用户归属与确认结果一致，业务数据库状态为 `active`。通过应用删除 API 再次执行单条归属和完整列表核验后删除；远端 DELETE 成功。本轮没有修改或删除其他记忆。

删除后独立推荐搜索返回 **0 条**，候选不再带记忆分；合成数据库中 `memory_confirmation=saved` 1 条、`memory_preference=retired` 1 条，未决状态 0。一次搜索为空证明此次复查时不可见，不能保证所有索引副本和在途请求立即更新。此轮没有残留需人工核销的未知写入或未确认删除。

## 离线回归与静态检查

本轮在独立临时 SQLite 中设置进程级 Mem0 关闭、清空模型及 Mem0 凭据，使用 MockTransport 或 Fake；以下命令未连接真实 Mem0：

```powershell
$env:SOLOMEAL_MEM0_ENABLED='false'
$env:SOLOMEAL_MEM0_API_KEY=''
$env:SOLOMEAL_MODEL_API_KEY=''
Remove-Item Env:SOLOMEAL_TEST_DATABASE_URL -ErrorAction SilentlyContinue
$testRoot=Join-Path $env:TEMP ('solomeal-final-offline-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest tests/test_memory_no_candidates.py tests/test_memory_operations.py tests/test_memory_provider.py tests/test_memory_agent_api.py tests/test_memory_recommendations.py tests/test_home.py tests/test_personalization.py tests/test_recommendation_scenarios.py tests/test_plans.py tests/test_plan_lifecycle.py tests/test_agent_sessions.py tests/test_agent_recovery.py tests/test_planning_performance.py tests/test_memory_diagnostics.py --basetemp $testRoot -o addopts='' -q -ra --tb=short -p no:cacheprovider
```

结果 **150 通过、0 失败、3 跳过**，有两条依赖弃用警告。三项跳过分别为 MySQL 下方案并发确认、取消与确认竞争、Agent 会话并发续接。其他 SQLite 测试包括 Mock 记忆重复确认、未知状态、Agent 锁外读取与租约复核的模拟，不证明 MySQL 行锁。仓库根目录执行 `backend\.venv\Scripts\ruff.exe check evaluation/mem0_final_validation_probe.py backend/app backend/tests --select F,E9` **通过**。未改前端，未运行前端测试。

## 结论与后续条件

当前证据支持在本次合成环境下的功能正确性和一次真实服务往返，但**尚不具备宣称 MySQL 并发验收完成或大规模真实用户 A/B 已就绪的条件**。下一步应先提供可确认独立、允许迁移测试清空的 MySQL 测试实例，串行运行上述行锁和记忆操作用例；同时明确未知写入的人工核销方法、真实服务费用上限和默认 2 秒阶段超时下的可靠性。更大规模 A/B 还需预先固定样本、隐私边界与质量指标，并单独授权。P8、±6 评分和普通用户 Mem0 开关保持不变。
