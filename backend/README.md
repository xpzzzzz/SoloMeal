2026-09-16部署更新：本地Compose空环境启动、关闭模型降级及真实MySQL与私有图片联合恢复已通过，见[部署说明](../deploy/README.md)和[验收范围](../docs/validation/deployment-restore-0916.md)。P9整体及真人/新主机验收未完成；以下旧部署未交付描述保留为历史。

# SoloMeal backend

2026-09-14第71节：v20补通用ID查询/结构化只读恢复反馈及澄清、报价查询规则；194回归通过/1 MySQL跳过、ruff通过。9个已暴露场景诊断6通过3失败（A026编造报价日期、A027不查询、A035首轮回答超时），原失败保留。新增17请求/已观察94749token/1缺usage，累计1615；17输入三哈希匹配，源码33816f7d…；P8/P5未完成。 [本轮报告](../docs/validation/p8-recovery-v20-0914.md)。下一步先离线处理报价事实来源/任意缺口计算工具边界与必要查询完成状态，分析A035既有超时证据；不要仅继续堆提示。v20九目录及v19旧manifest禁止重跑/追加；回归不冒充新盲测，原留出48/60不变。

2026-09-14第70节：v19合成留出180位置执行、审计、评审与聚合完成；Agent48/60（80%，未达85%）、固定60/60、直接26/42适用另18不适用。12个Agent失败全部保留，171退出码0/9退出码1。185请求/795947token，累计1598；恢复新增0，输入三哈希全匹配，源码7f8ab812…未变。holdout_gate=failed，真人清晰度null，P8/P5未完成。

下一步先离线修复通用查询/ID获取与错误恢复、澄清完整性、基于实际结果的后续建议；不能向旧manifest追加或重跑。源码变更后另登记有界诊断，原留出失败保留，修复后复验属于已暴露场景回归，不冒充新的盲测。

2026-09-14第69节：昨天v19统一debug 180位置已完成，恢复后离线审计评审聚合完成，新增外发0。Agent58/60、固定60/60、直接17/42适用另18不适用；A008-01漏问净含量、A014-01错误后续建议保留。190请求/833620token，累计1413；输入三哈希全匹配，180退出码均0，源码7f8ab812…不变。P8/P5未完成。

下文带日期旧段为历史，当前以第69～70节为准。

2026-09-13第68节：第67节三项离线问题已修复：恢复expiry/stale_quotes/注入文本冻结契约，metrics-v4将固定流程语义硬约束标不适用（客观判据保留），清晰度恢复mean≥4。222个不同回归用例通过、ruff通过，85%边界/完整成功/失败/缺失均有测试。源码7f8ab81290559aba68d70a2b8e672bcad78af6b6b2c413d4086292996915d79a；模型外发0/新登记0。下一步按新哈希登记调试统一重复，再合成留出；P8/P5未完成。

最新先读[修复报告](../docs/validation/p8-holdout-fix-0913.md)。当前Agent v19/direct-v1/json-tools-v2未变，聚合器v4；完整调试与留出均未登记/执行。先新源码debug 180位置、approve仅A010～12，独立审计评审聚合后再holdout 180位置、approve仅A030/31/33，执行前冻结参考价格与配置。不得重跑或追加旧manifest。语义不适用不等于客观约束免检，固定流程任务及写入等门槛仍保留。下文第67节问题为修复前历史，详情和局限见本轮报告。

2026-09-13第66节：留出A021～A040登记/执行/审计/评审/聚合离线补齐（`cohort_agent register --split`必填、每split仍180位置、确认扩展分置debug A010～A012与holdout A030/31/33、聚合升cohort-metrics-v3并按全分母判定留出85%）；并修复`food.batch_view`返回date导致`get_inventory`在工具边界`json.dumps`失败、被吞成MODEL_PROTOCOL_ERROR的真实缺陷（A021此前不可能达成，REST因jsonable_encoder被掩盖）。完整401通过/16 MySQL跳过（Docker未运行）、评测子集205通过、改动文件ruff通过。外发0、新登记0，两批统一重复均未启动，P8/P5未完成。

最新先读[本轮报告](../docs/validation/p8-holdout-offline-0913.md)。当前Agent v19/direct-v1（SYSTEM正文、工具schema、json-tools-v2、业务权限未变），HEAD仍a923d77c，源码由ec7c27702426f689096b69d52b795ee734e59662f6b0f11068953532f10fbcaa改为2cdd1681d65bc714695268fe2af49006059358fe3056148ddc9c7ae1c3867ce1。留出为合成集且本轮已为编写oracle读过其提示与fixture、A015/A035逐字两轮提示由harness拟定、清晰度以min≥4聚合（README为mean≥4，更严不假通过）、真人清晰度仍null、85%门槛未测量。下一步先给请求/token/墙钟估算并由用户选择，再登记20调试与20留出两批180位置；旧v16/v13/v12批次禁止重跑或追加。下文第65节及更早为历史快照。

2026-09-13第65节：v19将短/长续聊历史统一归入文本摘录，仅本轮工具结果作为活动消息；三轮回归及A015三次独立真实复验通过，旧v18失败保留。相关98项最终通过/1 MySQL跳过（分组复验有重叠），ruff通过。新增12请求/70071token，累计1223。下一步先离线补留出登记/执行/评审/聚合全链路，再新源码统一调试与留出；本轮未启动完整重复，P8/P5未完成。

最新先读[本轮报告](../docs/validation/p8-context-v19-0913.md)。当前Agent v19/direct-v1，源码ec7c27702426f689096b69d52b795ee734e59662f6b0f11068953532f10fbcaa。私有p8-A015-context-v19-0913-01～03已执行、审计、评审，禁止重跑；12份输入三哈希匹配，语义3/3仅为本次诊断，真人清晰度null。先实现cohort slots/register/load_plan、evaluate范围与split、review rubric及聚合的留出支持并补离线回归，保持冻结标签/门槛；随后按新源码哈希登记20调试三模式统一重复，再20合成留出。当前均未登记/执行，不向旧批次追加。下文第64节及更早为历史快照。

2026-09-13第64节：v16独立r2评审更正为Agent56/60、固定60/60、直接27/42适用另18不适用；退出码178个0/2个1。v17三类通用修复6/9、v18进一步修复8/9，A015-v18-02旧轮用量复用失败保留。106回归通过/1 MySQL跳过，最终22通过/1跳过、ruff通过。新增46请求/277153token，累计1211。下一步先离线处理多轮最新结果引用，再有界复验及留出全链路支持；不启动完整重复，P8/P5未完成。

最新先读[本轮报告](../docs/validation/p8-intent-v18-0913.md)。当前Agent v18/direct-v1，源码9be243feb6d6927cdedb680bd121022cea64d559fcbc0848f640126d1ceaf2ac。v16-r2修订评分已在新目录生成；v17/v18诊断均完成且禁止重跑。A015-v18-02工具正确返回160g/2蛋，回答仍写80g/1蛋，先离线核对当前轮结果引用路径再修复/独立复验。新统一180位置和留出均未登记；下文第63节及更早为历史。

2026-09-12第62节：拒绝解释/净含量澄清修复，v14/v15各5/6且新推测失败保留；v16六独立真实复验全部通过。91回归通过/1 MySQL跳过，最终16通过/1跳过、ruff通过。新增27请求/139902token，累计974；v13同输入超时离线分析完成、根因未知。下一步新登记v16完整180位置统一重复，再20留出；P8/P5未完成。

最新先读[修复与复验报告](../docs/validation/p8-clarification-v16-0912.md)。当前源码21b2ba809c8b08cdcc71ff9d9a4f8beccf293cc8b55296c0ac2e2acb56e2091f，Agent v16/direct-v1/json-v2/thinking=false/3000/30秒。下一步新登记完整180位置，approve仅A010～12可执行模式，其余none；目前尚未登记或执行。旧v13完整manifest及v14～v16诊断均禁止重跑，失败不回填。以下第61节及更早为历史。

2026-09-12第61节：v13完整180位置及恢复离线审计/评审/聚合完成；Agent55/60、固定60/60、直接20/42适用另18不适用。三首请求超时、A004拒绝解释及A008净含量澄清失败保留；A014三次通过。188请求/758184已观察token，累计947，恢复新增0。禁止重跑manifest；下一步通用修复/独立复验，再统一重复与20留出。P8/P5未完成。

最新先读[完整报告](../docs/validation/p8-cohort-v13-0912.md)。私有D:/SoloMeal-Acceptance/p8-cohort-v13-0912-01，manifest b4a32fe91c9ae8c4b23afe0625a535de4e61bd68e05bc8a88d95f66983cc6640，已完成，禁止重跑；源码仍8db7525ce63f06359d2f691bc6fe80ee6adc3c607a5e566279cb9833e7012790。下文“即将执行/未登记”均为历史。

2026-09-12第60节：v13后续操作能力边界修复及A014三独立真实复验通过；118回归通过/1 MySQL跳过、ruff通过。现有A013同输入延迟1.86/超时31.04/27.86秒，根因未知且旧失败保留。新增6请求/31208token，累计759。下一步新登记v13完整180位置统一重复，再20留出；P8/P5未完成。见STATUS第60节和docs/validation/p8-capability-v13-0912.md。

最新先读[修复报告](../docs/validation/p8-capability-v13-0912.md)。v13源码8db7525ce63f06359d2f691bc6fe80ee6adc3c607a5e566279cb9833e7012790；新统一批次尚未登记/执行，旧v12 manifest禁止重跑。以下第59节及更早为历史。

2026-09-12第59节：v12完整180位置执行、离线审计/评审/聚合完成；Agent58/60、固定60/60、直接23/42适用另18不适用。A013-02超时及A014-02不支持的忽略忌口确认路径保留，硬约束59通过/1缺失。189请求，累计753；额度中止恢复新增0，禁止重跑该manifest。下一步修复不支持的后续路径并独立复验、分析超时，再统一重复/20留出；P8/P5未完成。见NEXT_SESSION与STATUS第59节。 [批次报告](../docs/validation/p8-cohort-v12-0912.md)。下文为历史。

2026-09-12第58节：[v12修复与独立复验](../docs/validation/p8-constraints-v12-0912.md)九试次全部通过；v11两个A007失败保留。166回归及最终59复验通过（各1 MySQL跳过，包含重复），ruff通过。新增34请求，累计564。下一步新统一180位置三模式重复及20留出，P8/P5未完成，下文为历史。

2026-09-12第57节：[v4完整180位置](../docs/validation/p8-cohort-v4-0912.md)已完成执行、审计、评审及聚合。Agent56/60、固定60/60、直接26/42适用另18不适用；四个Agent语义失败保留，硬约束59/60未过100%。192请求/731007token，累计530，额度中止恢复新增0。该manifest不得重跑。下一步修复约束漂移/比较与忌口解释，独立复验后新统一重复及留出；P8/P5未完成，下文为历史。

2026-09-11第56节：[直接模型独立提示与v4登记](../docs/validation/p8-direct-v1-0911.md)完成，180专项/ruff通过；真实诊断1通过/2失败/1不适用，累计338请求。新完整180位置已登记未执行，下一步见NEXT_SESSION；P8/P5未完成。

2026-09-11第55节：[v10查询与预览修复](../docs/validation/p8-routing-v10-0911.md) A002/A016各三个真实试次通过，173回归通过/1 MySQL跳过、ruff通过；累计333已知聊天请求。下一步直接模型独立提示、新完整cohort及留出，P8/P5未完成。下文为历史。

2026-09-11第53～54节：[真实统一180位置](../docs/validation/p8-real-cohort-0911.md)完成，Agent52/60、固定60/60，失败/缺失保留；[v9包装量修复](../docs/validation/p8-package-v9-0911.md)三个新A006完整通过，新增私有输入留证，154回归/ruff通过。A002/A016等、新统一重复/留出仍待做，P8/P5未完成。

2026-09-11第52节：新增独立SOLOMEAL_MODEL_ENABLE_THINKING（默认省略，显式true/false），与视觉独立；CLI --no-enable-thinking。原3000/30秒/v8/json-v2下完整A014一次通过，2请求/8.48秒/8991token，Codex语义通过、人工清晰度未知。154回归及追加18专项/ruff通过；见[报告](../docs/validation/p8-a014-thinking-0911.md)。下一步真实统一配置/完整重复，P8/P5未完成。

2026-09-11第51节：A014离线重建及schema空白单变量诊断完成，一次仍31.08秒超时，18专项/ruff通过，聊天新增1；未应用生产，P8/P5未完成。详见[诊断报告](../docs/validation/p8-a014-compact-0911.md)。

2026-09-11第50节：cohort-v3固定流程独立CLI闭环完成，第二批60/60通过；修正计数/确认计时，旧批次保留。98专项及最终14复验/ruff通过，模型0。范围与后续见[CLI报告](../docs/validation/p8-fixed-cli-0911.md)。

2026-09-10第49节：参数/写入专门测量接入聚合，cohort-v3支持指定场景批准策略。114专项及最终27复验/ruff通过，模型0；口径、局限与后续CLI闭环见[测量报告](../docs/validation/p8-measurements-0910.md)。

2026-09-10第48节：cohort summarize三模式指标聚合已实现，58专项/ruff通过，模型0。参数/写入专门测量仍缺，正式门槛未完成；见[聚合报告](../docs/validation/p8-cohort-metrics-0910.md)。

2026-09-10第47节：cohort-v2已接执行前校验与评审绑定；92专项通过、最终23项复验及ruff通过。旧v1保留，新版需重新登记，正式配置未冻结、模型新增0；门槛聚合/留出仍待实现。见[联动报告](../docs/validation/p8-cohort-link-0910.md)。

2026-09-10第46节：[cohort预登记与审计](../docs/validation/p8-cohort-0910.md)已实现，180调试位置含未启动，配置/请求证据校验及34专项/ruff通过。离线工具不发模型请求，不代表已冻结正式配置或完整P8完成。

2026-09-10第45节：持续模型调用授权已明确；完整A014首请求超时、业务不变，失败评审及额度恢复记录见[报告](../docs/validation/p8-a014-chat-budget-0910.md)。不盲目重跑，P8/P5未完成。以下为历史。

2026-09-10第44节：单次A014预算探针26.39秒有效final，完整闭环仍待批准。新增SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS（默认1500、1～3000整数），仅聊天输出预算，生产请求仍30秒，不改.env或视觉参数；执行器可用--max-completion-tokens。唯一129专项通过、ruff通过，详见[报告](../docs/validation/p8-a014-final-budget-0910.md)。

2026-09-10第43节：[A014单次预算探针](../docs/validation/p8-a014-final-budget-0910.md)已实现，72专项/ruff通过。外发两次被自动审批在启动前拒绝，新增真实请求0；待具体DashScope外发批准，生产参数未改。以下为历史记录。

2026-09-10第42节：[A014有界诊断](../docs/validation/p8-a014-timeout-0910.md)完成两请求；延长等待后观察到输出预算耗尽、正文为空，未修复。66专项通过，生产1500/30秒和.env未改；下一单次预算探针尚未执行。

2026-09-10评审入口更新：[离线三模式评审与A014诊断方案](../docs/validation/p8-review-0910.md)。scripts/review_agent.py支持当前20调试场景，69专项通过；已绑定10旧报告并保留失败/未评分，只有v8 A018/A020填写Codex语义，人工清晰度仍null。A014有界探针未执行，统一冻结/完整对照/留出仍待做；下文为历史快照。

2026-09-10最新：[回答忠实性调试](../docs/validation/p8-faithfulness-0910.md)。当前提示v8/JSON协议v2，A018/A020本次通过，A014正确推荐后最终请求超时，回答验收仍缺。最终93通过/1 MySQL跳过、ruff通过。三模式评分、统一冻结/完整重复和留出待做；下文为历史快照。

2026-09-10时序扩展：执行器支持12调试场景；A015工具保留20分钟并改为2份，但最终回答引用单份数量，语义仍待修复。A016库存改0后两次批准均409且无做饭写入。真实6请求；专项分组67通过/1跳过、ruff通过。详见[时序调试报告](../docs/validation/p8-temporal-debug-0910.md)。

2026-09-10预算扩展：调试执行器新增A006/A007，支持10场景；A007在首次运行前修正夹具并冻结v1.2勘误。报价纳入业务快照和直接模型输入，预算检查覆盖整包装与未知费用；本次未修改业务服务。测试74通过、ruff通过，实测与关机中断记录见[预算报告](../docs/validation/p8-budget-debug-0910.md)。

2026-09-09确认扩展：执行器支持8个调试场景，真实入库/做饭/撤销批准、取消和同键重放已有证据；首次响应失败保留，json-tools-v2统一历史格式后复验通过。最终79测试通过，详见[确认调试报告](../docs/validation/p8-confirmation-debug-0909.md)。

2026-09-09协议更新：可选SOLOMEAL_MODEL_TOOL_PROTOCOL=json已通过A003同配置三次调试，A001通过；A002一次响应失败及新目录复验通过均保留。默认native，未改.env。最终65测试通过，详见[JSON协议实测](../docs/validation/p8-json-protocol-0909.md)。

2026-09-09 P8真实调试更新：[前三场景与失败报告](../docs/validation/p8-agent-debug-0909.md)。26次聊天请求，A001/A002工具路径通过，A003字符串整数兼容仍失败；complete_with_metadata及scripts/evaluate_agent.py已实现，最终46测试通过。完整P8未完成，下文旧快照保留。

2026-09-09 P8入口：[场景与预注册规则](../evaluation/README.md)。100场景已冻结，工程运行器scripts/evaluate.py首轮53/60场景通过、7个MySQL专属跳过；40个新合成Agent场景未跑，真实三模式仍待实现。本机模型名/密钥已配置但聊天开关关闭，未改.env。

最新（2026-09-09）：P7指定配置验收通过。receipt-v5、qwen3.8-flash、SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING=false、30秒时限下，三张真实字段与页面闭环通过，新隔离库23批次。该可选参数默认省略；未修改本机.env，可在启动环境显式设置以复现。详见[最终验收与局限](../docs/validation/receipt-v5-acceptance-0909.md)。P8完整评测与生产部署仍待完成，下文旧证据保留原日期。

> 2026-09-09授权更新：用户已持续授权本项目后续视觉模型调用，无需逐批确认。下文限次/需新授权表述为此前历史；调用仍须记录实际结果，避免无意义重试。

独立 FastAPI + SQLAlchemy + Alembic 后端，正式数据库为 MySQL，React/Vite 提供页面。原 Hermes 插件仍在根目录 src，规则与依赖独立。

## 当前能力（2026-09-08）

身份/偏好、定量批次、归档恢复、菜谱、FEFO 做饭扣减/撤销、版本化方案、包装报价、采购草稿与整单确认入库均已实现。小票私有上传和手工可编辑草稿已加入，支持逐行核对后整单确认入库与取消。单 Agent 使用应用内状态机、8 个工具和显式确认；SSE 提供运行状态恢复。最新迁移为 1b34d782ef90，21 张业务表。

视觉适配和完整图片解码已实现，真实模型、中文小票效果、正式评测、生产部署和远程 CI 尚未验收。浏览器测试使用隔离 SQLite 与脚本模型；其结果不替代 MySQL 并发或真实 AI 验证。最新证据见[状态第26节](../SOLOMEAL_STATUS.md)、[小票视觉边界验证](../docs/validation/receipt-vision-0908.md)；此前CI审阅见[审阅记录](../docs/validation/review-ci-0908.md)。历史验证数字保存在 STATUS，不代表当前全量结果。

2026-09-08补充：已执行3张真实授权票据、共6次真实模型调用；三票修正入库及同键重试闭环通过，隔离SQLite中23批次。识别含失败/超时/401及约重差异，P7尚未整体验收；详见[真实验收报告](../docs/validation/receipt-vision-real-0908.md)。常规E2E仍使用脚本模型，本次真实试验单独记录。

## 本地启动

本机已有 backend/.venv、frontend/node_modules 和私有 backend/.env，不要覆盖后者。新环境在 backend 执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
# 自行从 .env.example 创建 .env，并填写本项目的数据库配置
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Linux 虚拟环境命令使用 .venv/bin/python。本机专用 MySQL 容器为 solomeal-dev-mysql，127.0.0.1:13316；开发库 solomeal，测试库 solomeal_test。不要使用机器原有 MySQL80，也不要将测试指向开发库。独立Docker Compose部署、限流/分页及备份恢复见[部署指南](../deploy/README.md)，实际容器状态使用前检查。

frontend 目录执行 npm ci、npm run dev，访问 http://127.0.0.1:5173。API 文档为 http://127.0.0.1:8000/docs。启动不自动建表；readiness 比较数据库版本与迁移 head。修改代码后重启对应服务。

## 接口与业务约定

统一前缀 /api/v1：

- auth/register、login、logout；me、me/preferences。
- ingredients、别名与名称解析；inventory、批次修正/归档和事件。
- recipes、编辑/删除与原创 examples；cooking 和 undo。
- recommendations、plans 与版本/确认/取消；quotes；shopping 与 edit/confirm/cancel。
- agent/sessions、agent/runs 及 advance/approve/cancel/retry/events。
- receipts：图片上传、鉴权原图、草稿读取/编辑、确认/取消和受控解析接口，见[小票约定](../docs/receipts.md)。

认证使用 Bearer；身份由服务端会话绑定，数据库仅保存令牌摘要。要求幂等的写端点使用 Idempotency-Key（8～80 位字母数字、下划线或连字符）；同一逻辑重试复用 key，同 key 不同参数返回 409。版本化端点还校验 expected_version。

采购草稿保存原方案预算快照，后续方案修订/取消不改变它；实际采购金额不自动覆盖报价。采购确认只入库，做饭前需按当前库存更新原方案。细节见[规划与采购](../docs/planning.md)、[Agent 协议](../docs/agent.md)和[数据模型](../docs/data-model.md)。

## 验证

backend 目录：

```powershell
.venv/Scripts/python.exe -m pytest --basetemp=.tmp-pytest-run
.venv/Scripts/python.exe scripts/test_mysql.py
.venv/Scripts/python.exe -m alembic check
```

basetemp 必须是测试专用目录，pytest 会清理它。MySQL 测试只允许 solomeal_test，每例降级/升级迁移并清空该 schema；不可并行执行共享数据库测试。SQLite 会跳过 MySQL 专属竞争用例。

frontend 目录：

```powershell
npm test
npm run e2e
```

首次执行浏览器套件前安装浏览器：npx --no-install playwright install chromium；Linux 使用 install --with-deps chromium。npm run e2e 自动构建并串行运行浏览器及夹具生命周期测试。默认使用本项目对应平台的虚拟环境；不存在时使用 PATH 的 python，可用 SOLOMEAL_PYTHON 显式指定已安装后端依赖的解释器。

E2E 自动启动和清理临时数据库/服务，截图位于 frontend/.tmp-e2e。手动检查时可在 backend 运行 scripts/browser_fixture.py --port 8010 --model-delay 3；它只使用脚本模型和临时 SQLite，无需密钥。

CI 分别运行原插件、后端 MySQL/SQLite、前端测试/构建、Chromium E2E；全部汇入 ci-complete。当前只是配置完成与本地验证通过，远程执行仍待授权提交/推送后核验。

## 后续边界

2026-09-09已补小票脱敏失败诊断及receipt-v2数量提示，专项37通过/2 MySQL专属跳过；新提示尚未真实复验，额外调用须新授权。规则、初次失败和验证范围见[离线收尾](../docs/validation/receipt-diagnostics-0909.md)。

真实模型由用户在backend/.env或部署私有env自行配置，不在聊天索取密钥。指定视觉配置、小规模真实诊断、本地联合恢复、入口限流及列表分页已有证据，完整验收仍以STATUS为准。私有文件默认backend/private_uploads，不能作为静态目录公开，部署时与数据库联合备份。模型关闭时普通库存与菜单功能仍可使用。第三方测试适配的弃用警告另行跟进，不据此更换锁定依赖。
