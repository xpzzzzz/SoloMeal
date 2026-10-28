# Mem0 延迟观测与客户端复用：离线验证报告

2026-10-28。基于第六阶段诊断（本地保留）进行小范围实现。**本轮没有调用真实 Mem0、真实模型或运行新的真实 A/B；不能据此宣称线上延迟已经降低。**没有修改 P8 冻结协议或既有实验报告、证据和数据，没有部署、提交或推送。原工作区已有修改及未跟踪文件予以保留。

## 修改范围与设计

| 文件 | 本轮用途 |
| --- | --- |
| [memory.py](../backend/app/services/memory.py) | Provider 内按需创建并复用 HTTPX Client；按请求统计、计时和分类搜索异常；拒收服务端 Cookie，防止共享客户端跨用户保留状态。搜索条件、归属校验及读写逻辑保持原样。 |
| [memory_diagnostics.py](../backend/app/services/memory_diagnostics.py) | 新增请求局部的计时、计数和随机关联 ID；ASGI 请求结束时通过标准 logging 输出固定结构，不写入业务内容。 |
| [main.py](../backend/app/main.py) | 注册轻量 ASGI 观测中间件；lifespan 的 `finally` 关闭 Provider 和数据库引擎，包括异常退出及测试中替换 Provider 的情况；为未知/待处理操作标记分类。 |
| [planning.py](../backend/app/services/planning.py) | 包围现有 `read_memories`、状态抑制和候选记忆评分以记录指标；没有调整过滤、评分或排序。 |
| [memory_operations.py](../backend/app/services/memory_operations.py) | 在已有抑制查询结果上统计 unknown、pending/mutating、retired 状态；抑制条件及操作事务保持不变。 |
| [test_memory_diagnostics.py](../backend/tests/test_memory_diagnostics.py) | 新增客户端、应用生命周期、并发隔离、观测脱敏、错误分类和降级离线测试。 |
| 本报告 | 记录实现边界、实测结果与后续验证方法。 |

### 客户端和连接池生命周期

`create_app()` 仍为每个应用实例创建自己的 Provider，Provider 保有该实例的 API 配置。客户端在**首次需要远端请求时惰性创建**；锁保护首次创建，不把用户、请求体或结果放入 Provider 共享状态。多次同步调用使用同一个 HTTPX Client 和其有界默认连接池；不同应用/Provider 使用不同客户端和认证配置。正常关闭或 lifespan 内发生异常时关闭客户端；关闭操作可重复执行，同一应用重新进入 lifespan 后可重新惰性创建。关闭 Mem0 或密钥缺失时，正常业务方法不会创建客户端或发送请求。

客户端继续使用原来的 Authorization/Accept、base URL、timeout、禁重定向、搜索条件和异常降级；显式传入的较短归属核验 timeout 不变。连接是否实际复用受服务端连接关闭、代理、连接空闲期限等影响，MockTransport 能验证**同一个客户端对象被复用**，不能证明真实网络连接或握手节省。应用服务器应在关闭 lifespan 前完成在途请求；没有引入额外的跨进程协调或请求缓存。

复用必须注意 HTTPX 默认 Cookie 持久化：现在使用拒收和拒发 Cookie 的 CookieJar，避免一位用户的远端响应影响另一位用户。以前每次请求新建客户端，后续请求本来也不会复用此前响应的 Cookie。测试用远端模拟响应注入 Set-Cookie，检查后续并发请求不发送 Cookie。

## 计时与隐私边界

通过标准 logger `solomeal.memory.diagnostics` 在 INFO 级输出 `memory_diagnostics` JSON；需要既有日志配置允许该级别才能看到。只在有记忆读取或未知/待处理操作的 HTTP 请求结束后输出；日志调用本身失败被捕获，不改变响应。所有字段是随机关联号、数值或固定分类，不包含路径、认证头、密钥、用户 ID、记忆 ID/文本、搜索原文、请求/响应正文或库存。关联号每次独立生成，不使用用户标识。并发请求通过 ContextVar 隔离诊断对象；不会用日志保存记忆。

| 字段 | 精确含义 |
| --- | --- |
| `correlation_id` | 随机生成的单次 ASGI HTTP 请求关联号。 |
| `business_request_ms` | ASGI 应用接收 HTTP 调用至响应发送结束或异常退出的本机墙钟时间；包含认证、业务和序列化/发送，不含进入 ASGI 之前的外部网络。Agent advance 若包含模型执行，也会包含这部分；流式响应覆盖实际 ASGI 调用生命周期。 |
| `memory_reads`, `memory_read_ms` | `read_memories()` 的调用数及其累计本机墙钟时间，包含用户偏好读取、Provider 查询、校验和状态抑制；关闭、异常降级也计入。 |
| `http_requests`, `search_http_requests`, `http_request_ms` | 调用 HTTPX `client.request` 的尝试数、其中搜索次数、每次调用及状态检查的本机耗时数组；连接失败也算尝试，不代表 Mem0 确实收到请求。时间包含连接/网络、服务端等待和收包，**不等于服务端处理时间**。 |
| `client_setup_ms` | 获取客户端（包括首次构造和锁等待）的累计时间，位于 HTTP 调用计时之外。 |
| `response_json_ms`, `memory_conversion_ms` | 分别为 HTTP JSON 解码与 `_decode` 结构化转换的累计耗时；后者不包含缺失归属时的远端 GET。 |
| `search_results`, `ownership_lookups` | 搜索结果封套中的条数与因缺失用户归属而发起补查的次数；不记录条目内容。 |
| `suppression_ms`，`suppressed_unknown/pending/retired` | 本地 `operations` 查询与抑制的累计时间及对应状态记录数；pending 包括 mutating。状态数为数据库记录数，不是用户数。 |
| `candidate_scoring_ms`, `candidates_scored`, `candidates_matched` | 所有可行候选的 `score_memories()` 累计耗时、调用数和有非冲突匹配理由的候选数；即使不同理由加减抵消也按理由计数。 |
| `read_status`, `timeout_phase`, `operation_status` | 读取结果包括 `ok`、`empty`、`disabled`、`timeout`、`timeout_budget`、`rate_limited`、`unavailable`、`invalid_response`、`invalid_provider`、`unverified`；网络超时阶段为 connect/read/write/pool/other；操作状态可为 unknown 或 pending。若远端正常但某项被本地 unknown 状态抑制，读取仍可为 ok，以 `suppressed_unknown` 区分。 |

`business_request_ms` 包含 `memory_read_ms`，后者包含客户端获取、HTTP、JSON、转换和抑制；候选评分在另一阶段。归属补查的 HTTP 与 JSON 又嵌套在读取内。**这些计时不能全部相加**；累计的 `http_request_ms` 数组也不应与包含它的上层时间重复相加。当前没有 DNS、TCP、TLS、连接命中或 Mem0 服务端处理的独立计时。默认 2 秒是 HTTPX 网络阶段超时，现有跨请求预算不是严格端到端时限，行为未改。

第五阶段运行器在计时区间写证据文件，历史数据未改。将来设计新实验时，应把证据写盘移出被测业务时间段，保留原始边界并避免把带额外追踪 I/O 的旧数字当成精确对照。

## 离线测试与检查

各次运行使用独立 SQLite 测试数据库；测试进程临时强制关闭普通应用的 Mem0 开关、清空该进程中的密钥变量，并移除测试数据库环境覆盖；这些设置不修改用户配置文件。启用 Provider 的测试仅使用 `httpx.MockTransport` 或 Fake，Agent 使用 Scripted/Fake。以下命令从 `backend` 目录运行（运行前设置上述进程级隔离变量）；统计彼此有重叠，不应相加为独立用例数。

```powershell
$env:SOLOMEAL_MEM0_ENABLED='false'
$env:SOLOMEAL_MEM0_API_KEY=''
Remove-Item Env:SOLOMEAL_TEST_DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest tests/test_memory_diagnostics.py tests/test_memory_provider.py tests/test_memory_operations.py tests/test_memory_agent_api.py tests/test_memory_recommendations.py tests/test_personalization.py tests/test_recommendation_scenarios.py tests/test_recommendation_diagnostic.py tests/test_recommendation_response.py tests/test_planning.py tests/test_home.py tests/test_agent.py tests/test_agent_actions.py tests/test_agent_sessions.py tests/test_agent_recovery.py tests/test_agent_review.py -o addopts='' -q -ra
.\.venv\Scripts\python.exe -m pytest tests/test_plans.py tests/test_plan_lifecycle.py tests/test_personal_time.py -o addopts='' -q -ra -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_memory_diagnostics.py tests/test_memory_provider.py tests/test_memory_operations.py tests/test_memory_agent_api.py tests/test_memory_recommendations.py -o addopts='' -q -ra -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_memory_diagnostics.py tests/test_memory_provider.py -o addopts='' -q -ra -p no:cacheprovider
```

| 运行 | 结果 | 备注 |
| --- | --- | --- |
| 第一条：Provider、操作、推荐、首页与 Agent 等回归 | **161 通过，1 跳过，0 失败** | 在最后补充 Cookie 策略和小幅生命周期收尾之前运行；其涉及的 Provider 与诊断测试之后另行复跑。一次 pytest 缓存目录权限警告及两项依赖弃用警告。 |
| 第二条：方案、方案生命周期与个人用时 | **26 通过，2 跳过，0 失败** | SQLite；两项依赖弃用警告。 |
| 第三条：Cookie 策略后的记忆相关回归 | **71 通过，0 跳过，0 失败** | 包括 Provider、操作、API、推荐和当时的诊断测试；最后补充了替换 Provider 时的关闭保护及相应专项测试。 |
| 第四条：最终 Provider 和诊断专项 | **36 通过，0 跳过，0 失败** | 覆盖最终版本及替换 Provider 生命周期。两项依赖弃用警告。 |

三个跳过项均要求真实 MySQL 行锁：`test_agent_sessions.py::test_mysql_concurrent_session_continuation`、`test_plans.py::test_concurrent_confirmation` 和 `test_plan_lifecycle.py::test_mysql_cancel_confirm_race`。本轮使用 SQLite，未配置或运行隔离 MySQL 验证，**不计为通过**。未改前端，故未运行前端测试。仓库根目录执行 `backend\.venv\Scripts\ruff.exe check backend/app backend/tests --select F,E9`，**通过**；未声称执行了整个项目其他静态检查或全量测试。

离线测试检查了同一客户端多次及并发请求、两套认证配置分离、Cookie 隔离、请求参数/超时/禁重定向、应用正常与异常关闭、重复生命周期和构造异常；检查了日志脱敏、单请求与并发关联、搜索/补查计数、unknown 抑制、日志失败、超时、限流及连接错误。既有测试覆盖禁用、失败降级、用户隔离、记忆修正删除、确认幂等、硬约束和推荐结果。保持一致的结论仅限这些离线测试范围；没有实测生产负载、真实连接池行为、真实服务延迟或账单。

## 未实施和未来验证

本轮没有改变 ±6、搜索 top_k/阈值、用户过滤、operations 状态、幂等和硬约束，也没有跨请求记忆缓存。无可行候选时仍会先检索；要跳过检索需先将 planner 的候选硬过滤阶段复用，并确保保留输入/报价校验、错误响应、方案版本与事务语义、用户隔离、Agent 锁边界及全部排序理由；需要离线逐项比较后才适合实施，不应仅凭 S8 重构。

真实连接复用收益、DNS/TCP/TLS/服务端分解、默认 2 秒配置下成功率、远端索引延迟和 unknown 写入人工核销仍待验证；服务端可能主动关闭连接、代理可能影响复用；应用日志开销与线上并发影响也尚未量化。外部项目隔离、数据库 operations 抑制及在途旧快照风险保持此前边界。

下一步若用户另行授权少量真实请求：先确认隔离项目、合成用户及无未决操作，选择已知合成记忆，只读执行几次固定搜索（例如原实现与复用实现各两次，首个和后续请求分别标记，严格限制次数和费用），比较相同检索结果、认证隔离、业务响应与客户端 HTTP/端到端耗时。连接新建/复用需额外隐私安全的传输层观测或可信服务端信息，不能只凭时间差认定；不记录密钥、用户内容或原始响应。旧版运行器的证据写盘应排除在新计时之外。少量样本仅验证契约与可能的机制，不能证明长期 P50/P95 改善；成本/Token 不可核实则记为未知。此步骤本轮未执行。
