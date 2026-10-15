# SoloMeal 后端改造基线报告（M0）

日期：2026-10-14（Asia/Shanghai）。执行依据：[后端工程增强计划 V1.0](backend-engineering-enhancement-plan-v1.0.md)。阶段：**M0 已完成，等待用户确认；M1 未开始**。

本阶段检查源码、配置、迁移、测试收集与运行环境，只新增报告及交接记录。未修改业务代码、依赖、迁移、测试驱动或部署；未运行压测、业务回归、数据库迁移或模型请求。只读环境证据见 [backend-m0-1014-evidence.json](validation/backend-m0-1014-evidence.json)。

## 1. 结论与证据边界

1. **优先测量推荐、菜谱列表及首页。** 推荐和菜谱列表逐道调用 `recipe_view()`，每道菜谱都显式查询菜谱本体与食材列表，存在随菜谱数增长的重复查询结构。首页推荐栏继承这条链路。这是源码确认的查询结构，尚无真实请求的 SQL 计数、QPS 或 P95；不能据此宣称性能瓶颈或优化收益已测得。
2. **小票解析仍在 HTTP 请求内完成。** 当前接口没有 Celery、RabbitMQ、任务表或持久待派发机制；已有解析抢占、操作幂等、版本保护、私有图片与人工确认事务可以复用。现有中断策略是避免再次调用模型并转为失败，不是自动恢复解析任务。
3. **后续 Worker 使用 Linux 容器验证。** 当前开发宿主机为 Windows 11，Celery 官方不支持原生 Windows；不要用 Windows 上的临时执行方式作为可靠性验收依据。[Celery 官方平台说明](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)
4. **已有试用环境必须保留。** 实际运行项目为 `solomeal-features-0921`，入口 18088，web/api/db 均 healthy。此次只请求首页静态入口、健康检查及数据库元数据，没有登录、上传、识别或业务写入。
5. **可以提交 M0 审核，不能自动进入 M1。** 接下来应建立独立性能环境并测量；M3/M4 的异步改造、M4.5 的 OCR 仍未开始。

## 2. 工作树与基线锚点

| 项目 | 本次观察 |
| --- | --- |
| HEAD | `7ccb597e63e17aa0587fab59c4b61c0e621ec5b3` |
| 工作树 | 开始时已有 25 个已跟踪文件修改、5 个未跟踪文件；不是干净 HEAD |
| 已有应用修改 | `recipe_discovery.py` 及相关测试；前端页面、样式与浏览器驱动等，全部保留 |
| 已有规划修改 | AGENTS.md、CLAUDE.md、NEXT_SESSION.md 及新增后端计划，全部保留 |
| 文件保护 | 对开始时 572 个可访问的已跟踪/未忽略未跟踪文件建立 SHA256 快照；收口时核对，交接入口仅追加本次内容 |
| 受权限保护目录 | 根目录五个历史 `.pytest-*` / `.test-tmp-crud-0906` 目录仍不可读；没有清理或改变权限。`git status` 有警告但退出码为 0 |
| 审计源码与运行 API | database、planning、home、food、receipts、receipt_parser、receipts API 和 receipts model 共 8 个文件，只归一 CRLF/LF 后哈希全部相同 |
| 迁移 | 本地 `alembic heads` 与运行库 `alembic_version` 均为 `a7c9e2f10463` |
| 运行前端 | `index-BIfInUpj.js` / `index-Bt3SlEE9.css` |

上述 8 个文件相同只证明被审计文件对应运行代码，不代表整个镜像与当前工作树完全一致。M1 应冻结实际测试代码、数据种子、配置和镜像，不只记录 HEAD；不同工作区换行也不能冒充代码差异或性能变化。

## 3. 当前架构与关键执行链路

独立 Web 应用位于 `backend/`、`frontend/`、`deploy/` 与 Compose 配置；根目录 `src/`、`__init__.py` 等是原 Hermes 插件。此次增强只针对独立应用，不改变插件的标准库/JSON 存储边界，也不改写来源与许可证说明。

**读取链路：** React → Nginx → FastAPI → 每请求 SQLAlchemy Session → MySQL。后端使用同步 SQLAlchemy / PyMySQL；Uvicorn 容器启动参数为单进程 `--workers 1`。普通同步路由由框架调度；小票 async 路由仍调用同步数据库与图片校验代码，异步语法本身不证明吞吐量提高。

**推荐链路：** 加载偏好、报价、历史、忌口、库存与菜谱 ID → 逐道装配菜谱 → 时间、厨具、忌口与预算筛选 → 库存/临期/重复/偏好评分 → 排序输出候选及拒绝理由。该接口只读，不调用模型、不预留或扣减库存。首页四栏逐栏构建并支持局部错误；推荐栏直接复用该 planner。

**写入链路：** `food.run_operation()` 对用户行加锁 → 校验同用户幂等键与请求摘要 → 执行业务动作 → 保存操作结果并提交。库存单位转换、整单事务、批次事件、做饭与撤销继续使用现有能力，性能优化不得绕开用户归属或锁。

## 4. P0：待测接口与瓶颈候选

| 优先级 | 接口 | 源码证据与 M1 应测内容 |
| --- | --- | --- |
| 首要 | `POST /api/v1/recommendations` | `planning.py:126` 先取用户全部菜谱 ID，`:129` 逐道调用 `food.recipe_view()`；`:185` 逐候选计算偏好。测菜谱规模、SQL 数量、数据库耗时、Python 计算和响应体大小 |
| 首要 | `GET /api/v1/recipes` | `api/food.py:132` 先分页取 ID，再逐道 `recipe_view()`；列表反馈已经批量查询。测同页条数 10/100/200 及跨页总量 |
| 首要 | `GET /api/v1/home` / `/home/recommendations` | `home.py:94` 调 planner；`shown_limit=3` 是展示信息，后端仍返回 planner 的候选集合。测完整聚合、推荐单栏、三个便宜栏分别耗时 |
| 对照 | `GET /api/v1/inventory` | `food.py:181` 在一条查询中 join 批次与食材，已有 SQL 分页，未见逐批次装配查询。测过滤、排序、页大小和批次数增长 |
| 次要 | `GET /api/v1/cooking` | 用户过滤后按日期/ID 排序分页；每行含 JSON 菜谱快照。测历史规模、排序执行计划与序列化成本 |
| 补充 | `/home/attention`、`/home/shopping`、`/home/recent` | attention 为列表及两次计数；shopping 为全量草稿读取后 Python 汇总再截取前三；recent 为计数及前五条。测过滤/汇总，不把展示上限当 SQL 读取上限 |

### 已确认的查询结构

`food.recipe_view()`（`food.py:374`）先经 `owned()` 发出菜谱 SELECT，再 join 查询该菜谱所有食材。两处调用都在菜谱循环内，因此每道菜谱增加 **2 条显式 SELECT**，形成常数查询加 `2N` 的结构。这里不是 ORM 隐式懒加载，而是显式循环查询。总 SQL 数还包括认证、偏好、报价、历史、反馈等，M1 必须按实际请求计数，不能直接把 `2N` 当整个接口统计。

已有批量能力应保留：个人耗时历史一次读取，隐式偏好历史最多读取最新 200 条，反馈通过 `feedback_map()` 一次批量查询；库存先集中读取再内存汇总。

另有两个计算/读取候选：`personalization.score_candidate()` 每次都会调用 `_weights()`，对同一历史集合重复计算衰减权重；`duration_samples()` 先读取 180 天内所有有效耗时记录，再在 Python 中限制每菜谱最多 20 条。这些需要 M1 区分数据库、Python 与响应序列化成本，不能只盯索引。

### 当前索引与测量边界

已检查模型、Alembic 与运行库 `information_schema.STATISTICS`。关键索引包括：

| 表 | 已有索引/约束 | 需要结合 EXPLAIN 验证的访问 |
| --- | --- | --- |
| recipes | user_id；主键；(id,user_id) 唯一 | 用户内列表按 name/id 排序 |
| recipe_ingredients | (recipe_id,user_id)、(ingredient_id,user_id)；user_id；(recipe_id,ingredient_id) 唯一 | 单菜 join 与未来批量装配 |
| inventory_batches | user_id；(ingredient_id,user_id)；(id,user_id) 唯一 | 用户+archived、created_at/id 排序及到期筛选 |
| cooking_records | user_id；主键；(id,user_id) 唯一 | 用户+status+created_at 窗口及历史排序 |
| shopping_lists | user_id；主键 | 用户+draft 状态与日期排序 |
| price_quotes | user_id；(user_id,ingredient_id) 唯一；归属外键索引 | 用户内批量报价 |
| receipt_imports | user_id；(user_id,file_hash)；(user_id,parse_started_at)；file_key 唯一 | 重复提示、滚动额度与解析占用检查 |
| operations | user_id；(user_id,key) 唯一；(id,user_id) 唯一 | 操作重放与用户隔离 |

目前未见针对库存/烹饪/采购这些过滤与排序的相应复合索引，但不能据此断言全表扫描或索引一定有收益。本阶段未跑 EXPLAIN、EXPLAIN ANALYZE 或 SQL 事件计数，也未读取用户业务内容、估算真实数据量。

M1 按相同固定种子，建议 10/100/500 道菜谱及合理批次/历史规模，低到高 1/5/20 并发起步并按本机资源调整。记录 QPS/RPS、P50/P95、错误率、SQL 次数、运行时配置和波动；Nginx 限流入口与隔离 API 直连分开测量，原限流不修改。当前不生成任何优化百分比。

## 5. SQLAlchemy 连接池与隔离级别

`backend/app/core/database.py` 明确设置 `pool_pre_ping=True`，非 SQLite 配置 `connect_timeout=5` 与 `isolation_level="READ COMMITTED"`；未显式设置池大小、溢出、回收与等待时限。运行 API 中实际探测得到：

| 参数 | 当前值 |
| --- | --- |
| 数据库/驱动 | MySQL 8.0.46 / PyMySQL |
| 池类型 | QueuePool |
| pool_size / max_overflow | 5 / 10，每个 Engine 最多 15 个池内及溢出连接 |
| pool_timeout | 30 秒 |
| pool_recycle | -1，未设置定期回收 |
| pool_pre_ping | true |
| 新连接 connect_timeout | 5 秒 |
| 应用连接 session 隔离级别 | READ-COMMITTED |
| MySQL global 默认隔离级别 | REPEATABLE-READ |
| MySQL max_connections | 151 |

池值来自本轮创建相同配置 Engine 的参数探测，隔离级别来自实际连接的只读 SELECT；没有测运行服务的连接池占用或等待事件。QueuePool 默认参数可对照 [SQLAlchemy 官方说明](https://docs.sqlalchemy.org/en/20/core/pooling.html)。迁移脚本另外使用 NullPool，其配置不能当作 API 连接池配置。

M1 如发现等待才考虑 M2 调整。M3 增加 Worker/派发进程后需计算每进程独立 Engine 的总连接预算；不应把 151 直接平均后盲目扩池，也不在 fork 前复用已经建立的数据库连接。

## 6. 小票当前行为与可复用能力

### 上传、识别和保存

1. 原图只支持 PNG/JPEG，最多 5 MiB；Pillow 验证格式、完整解码、20MP、单边 12000px 与单帧边界。随机 UUID 文件名保存至受保护目录/卷，下载须用户归属校验，文件读取再次核对大小与 SHA256。
2. 上传经操作幂等保护。同用户同图片 hash 只返回 `duplicate_of` 提示，**不会阻止以新操作键再次上传**；不是全局图片去重，更不能跨用户合并图片。
3. `POST /receipts/{id}/parse` 当前正常受理最终返回 HTTP 200 小票对象。请求内完成 `await receipts.parse()`，首次请求会等待识别结束，不是 202 排队受理。
4. 受理时锁用户与小票、校验 draft/version=1、要求从未解析/编辑，检查最近 24 小时额度与最近 120 秒同用户活跃解析；提交 `parsing` 和操作记录后释放事务，再读取/校验图片并等待 parser。
5. 默认超时 30 秒（配置允许 >0 且 ≤60）、每日默认 10 次（范围 1～100）；外层 `asyncio.wait_for` 与 HTTPX 均有时限。VLM 响应最多 256KiB、输出预算 4000 Token，拒绝非正常结束、工具调用、refusal、非法 JSON 或 Schema。
6. `_finish_parse()` 重新获取锁与当前版本。用户已编辑或取消时，旧结果标 discarded 并返回冲突；合法结果保存到 `parsed`，形成 `draft`，所有行重新强制 `uncertain=true`。异常保存 failed；诊断日志仅允许错误类别与必要 ID，不回显密钥/图片/模型正文。
7. 同操作键重放不会再调用模型。进程中断后，120 秒过期在查询投影中显示 failed；相同键再次调用可把失败落库。**没有自动重新派发或重做识别**，现有测试明确验证“中断后不再次请求模型”。

### 状态和人工确认

业务状态为 `draft/completed/cancelled`；解析状态为 `manual/parsing/parsed/failed/discarded`。原始 `parsed` 与用户修改后的 `draft` 分开保存，另有 version、parse_started_at、parse_finished_at 与确认 result。

确认前重新校验未排除行：必须取消 uncertain、选定同用户食材并填写有效数量/单位；库存日期来源与单位转换复用 `BatchInput`、`food.convert()`。全部行通过后，以同一 Operation 调用 `food.add_batch(..., operation=op)`，整单一次提交；任何一行失败全单回滚。未确认识别不写库存。取消与完成终态不能再次入库。

前端已提供原图、可编辑草稿、逐行数量/单位冲突提示、二次确认、手动录入、取消和手动刷新。发送视觉模型前有费用提示与明确用户操作；当前没有 queued 状态或自动轮询。操作键缓存在组件 ref 中，受理响应丢失、切页和刷新后的新异步恢复需在 M3/M4 专门验证，不能把该 ref 视为持久任务标识。

### 限流

Compose 的 Nginx 按来源 IP：普通 API 20次/秒+burst80，认证 5次/分钟+burst10，Agent advance/小票 parse 共享 30次/分钟+burst16；429 为 JSON 并带 Retry-After:60。健康检查豁免。后端另有用户额度与同用户活跃解析限制；两层目的不同，不能相互替代。直接启动 API 不自带 Nginx 的 IP 桶。

## 7. P2：预计改动模块、复用与风险

以下是后续阶段建议，不是本轮已实现内容。

| 阶段/模块 | 预计职责 | 必须保持的边界 |
| --- | --- | --- |
| M3：receipts API/service | 分离受理与执行；处理异步状态码/响应契约 | 前后端及测试同时更新；沿用版本、归属、操作幂等和额度 |
| M3：模型/迁移/持久派发 | MySQL 任务与 outbox（同事务记录待发送消息） | 受理和待派发同事务；Broker 失败仍可查；允许重复派发并幂等消费 |
| M3：Celery Worker | 由 task ID 加载任务和受保护图片，调用现有 parser | 消息不携带图片二进制、Key 或正文；模型等待不持有数据库锁 |
| M3/M4：执行权与恢复 | 租约、尝试数、时限、重试、终态提交 | 不能直接用单一 parse_finished_at 代替每次执行身份；旧 attempt 不能盖新结果 |
| M3：ReceiptPanel/session | 排队/识别/失败展示、有限轮询与重新登录恢复 | 保留草稿编辑与人工确认，验证原操作键/任务 ID 的恢复 |
| M4：可靠性测试 | 重复投递、Broker 断连、Worker 退出、响应丢失、编辑/取消与跨用户 | 用真实 RabbitMQ/Worker；Mock/eager 不足以证明可靠性 |
| M4.5：OCR | 兼容性检查、解析、三模式、冲突和降级 | 只在 M4 获确认后开始，复用同一 Worker；本轮没有安装或试验 OCR |
| M5：部署/备份/CI | Broker/Worker 健康、共享卷、锁定依赖、集成检查 | 私有卷与新增表纳入备份；维护窗口须考虑 Worker 和派发器 |

主要兼容性风险：

- 现有每票仅识别一次且失败不重做，与“有限重试、过期恢复”有行为差异。M3/M4 须区分同业务操作、同任务的内部 attempt 与用户另起操作，防止重复消耗额度、无界模型调用或重复覆盖草稿。
- 同一数据库同时保存业务与派发记录仍不能跨 MySQL/RabbitMQ 原子提交，需要 outbox 重发及消费端幂等。发布确认与消费确认分别保护不同方向，不能承诺自动“恰好执行一次”。[RabbitMQ 官方确认机制](https://www.rabbitmq.com/docs/confirms)
- Worker 并发/fork、模型时限、租约时长、RabbitMQ 重投与数据库最终提交必须配合；只增加 Celery task 装饰器不能解决这些风险。
- `deploy/manage.py` 当前备份只停止 web/api。新增 Worker/派发器后仍可能写库，因此 M5 必须更新维护窗口逻辑，不能原样声称联合备份一致。
- 新异步解析与未来模式选择可能改变原接口/能力字段及既有 E2E 断言；需兼容历史 draft/manual/parsed/failed 记录，不迁移或清空已有用户数据来简化实现。

## 8. 新依赖与配置建议

| 阶段 | 最小新增依赖/服务 | 建议 |
| --- | --- | --- |
| M1 | Locust（压测客户端） | 安装在独立工具环境或测试容器，不加进原插件依赖；验证 Python 3.13 的 gevent 等二进制依赖，再锁定实际可用版本。[Locust 官方安装说明](https://docs.locust.io/en/stable/installation.html) |
| M2 | 通常无需新增依赖 | 优先批量查询/复用计算；是否增加索引或改池由 M1 结果决定 |
| M3 | Celery 及 AMQP 依赖、RabbitMQ 服务 | 采用 Linux Worker；具体 Celery/RabbitMQ 版本与镜像 digest 在隔离环境验证后锁定。本轮没有安装 |
| M3/M4 | 沿用 SQLAlchemy/Pydantic/MySQL | MySQL 业务任务表作为状态来源，可不启用 Celery 结果后端；无 Redis，也不另建任务状态真相来源 |
| M4.5 | PaddleOCR CPU 与对应推理运行时 | 此时仅列计划，版本、Windows/Linux wheel、模型下载缓存和资源消耗留待该阶段实际验证 |

M3 需明确 Broker URL/私有凭据、队列/vhost、发布确认、持久化、连接超时、prefetch/concurrency、Worker 软硬时限、attempt/退避、租约/扫描周期和 MySQL 连接预算。任务消息只允许 JSON 等受限序列化；密钥在环境中注入，日志不打印完整配置。M3/M4 不引入 Redis、监控平台、Kubernetes 或微服务拆分。

## 9. 已有测试、CI 与部署覆盖

| 层面 | 已有配置/代码覆盖 | 本轮实际结果及不能推断的内容 |
| --- | --- | --- |
| pytest | MySQL/SQLite fixture、迁移、核心业务、首页、推荐、小票安全/确认/并发、模型 MockTransport、备份恢复保护等 | 收集 **662 用例**，退出 0；未执行用例，不宣称 662 通过 |
| MySQL 测试 | `conftest.py` 只接受 MySQL 库名 solomeal_test，每例 downgrade/base → upgrade/head，末尾降级 | 会销毁测试 schema，且仅校验库名不足以隔离主机；本轮不运行，M1/M3 使用全新项目与专用测试库 |
| 小票专项 | 四个后端测试文件检查隐私、重复请求、限额、超时、非法响应、人工确认与迟到结果；MySQL 竞争用例在 SQLite 上 skip | 检查了测试实现，未重跑或把历史结果登记为本轮通过 |
| 前端单测/构建 | npm test 为 TypeScript 辅助模块编译+node:test；build 为 tsc --noEmit+Vite | 现有环境有 node_modules；本轮没有 build/test，保留既有 dist |
| 浏览器 | Playwright Chromium + 临时 SQLite + 脚本 parser/provider；小票 4 个场景含人工确认、取消、窄屏冲突与响应丢失 | 不能代替真实 MySQL 锁、MQ 或视觉模型；本轮未运行 |
| GitHub Actions | 插件 Python3.12/3.13/3.14、types、coverage≥91；独立 backend（真实 MySQL+SQLite）、frontend、browser-e2e 汇入 ci-complete | 检查 YAML 与执行命令；没有触发或核验当前远程运行。无现成 MQ/OCR 集成作业 |
| Compose | MySQL→migrate→API→web，health/ready 校验迁移 head；应用非 root、私有 uploads 卷、备份/恢复工具 | 18088 live/ready 均200，三服务 healthy；本轮未迁移、备份、重建或重启 |

收集命令（以 backend 为工作目录）：

```text
.venv/Scripts/python.exe -B -m pytest --collect-only -q --disable-warnings -o "addopts=-p no:cacheprovider"
.venv/Scripts/python.exe -B -m alembic heads
```

pytest 子进程显式禁用 Agent/视觉/发现开关，移除测试数据库 URL 并禁止 pyc 写入；不执行数据库 fixture。第一次收集输出的末行是警告说明，未获得计数，随后使用明确参数重新收集，得到 `662 tests collected in 0.59s`。这两次均是收集，不是测试执行。

审计过程中两条只读检索命令的 PowerShell/路径写法未成功：一条 rg 在没有额外 AGENTS/CLAUDE 文件时退出 1；另一条误用 shell brace 展开导致 PowerShell 解析失败。已用明确文件路径完成读取；没有业务执行失败或数据修改。

## 10. 环境保护与隔离方案

宿主：Windows 11 / AMD64，Python 3.13.13、Node 24.16.0。Docker Engine 29.6.1、Compose 5.1.4；Linux x86_64 引擎报告 16 CPU、约 7.68GiB 内存额度，实际可用资源受其他负载影响。本轮没有进行负载归因或资源压测。

本地 `backend/.venv`、`frontend/node_modules`、私有 `.env` 与 `backend/private_uploads` 已存在。私有开发配置指向 127.0.0.1:13316/solomeal，对应 `solomeal-dev-mysql` 当前停止；本地视觉配置和密钥存在。运行 18088 的 Agent/视觉/发现开关均已开启，所以审计不能随意使用识别或 advance 路由。配置仅提取白名单元数据，未输出任何密码、Token、模型密钥或图片内容。

保护对象为 `solomeal-features-0921_database` 和 `_uploads`；历史 acceptance-0916a/b、combined-0917、agent-weaknet-0917、fault 项目及其卷均保留。其他项目/匿名卷同样不触碰。当前 Docker 列表中没有运行的 SoloMeal 18080 web；这不构成复用或清理 18080 资源的授权，本轮未请求该端口。

M1 隔离方案建议：

1. 建立全新 `solomeal-perf-m1-*` Compose 项目，使用独立数据库和 uploads 卷，私有 env 新建不覆盖。端口在执行前检查空闲；不复用 18080/18088、13316 或任何历史项目。
2. 合成数据固定种子，仅连接该项目；模型相关开关关闭。业务库与 destructive pytest 的 solomeal_test 库分离，测试串行，不借用试用环境的 MySQL。
3. API 直连入口仅绑定回环并只用于该隔离项目；Nginx 对照保留原有限流。压测先低负载、记录实际机器/容器额度与并发，避免把入口429误判为 SQL 容量。
4. 使用当前待测工作树快照构建或拷贝到专用目录，记录内容哈希与镜像；不能复用一个不确定来源的 local tag 来作前后对照。
5. SQL 监听、脱敏执行计划、Locust 脚本与结果在 M1 实现；本轮不创建数据生成/压测工具，不启动隔离容器，不修改现有部署。

## 11. 阶段收口

**阶段：** M0。

**目标是否达成：** 完成。已回答七个审计问题，明确可测入口、现有复用能力、依赖与 Windows/Linux 风险、隔离边界和未验证项。

**解决的具体业务问题：** 为性能测量与异步小票改造建立可核对的起点，避免把 UI 展示上限当数据库读取上限、把现有中断失败当可靠任务恢复、把历史测试当本轮成绩。

**采用的技术方案：** 源码/配置审计、白名单环境探测、只读数据库元数据、迁移 head 检查、测试收集与文件哈希保护；未安装新工具或写测试工具。

**实际改动文件：** 本报告、脱敏 evidence JSON、后端增强执行记录；AGENTS.md、CLAUDE.md、NEXT_SESSION.md 追加 M0 交接入口。原规划与应用代码保持原字节。

**测试与结果：** pytest 收集 662、alembic head 一致、live/ready 各200、三容器 healthy、8 个审计文件与运行 API 归一行尾哈希匹配。未执行单测/E2E/真实 MySQL 竞争/压测/MQ/OCR 验证。

**兼容性与风险：** 后续重点为原解析“一次尝试”与任务重试的边界、数据库/Broker 双写、执行权 fencing、前端受理响应丢失恢复、Worker 连接预算与备份维护窗口；全部留待原定阶段实现。

**下一阶段建议：** 用户审核确认 M0 后进入 M1，先建立隔离性能环境并测量。本轮停止，M1～M5 未开始，M4.5 未提前实现。
