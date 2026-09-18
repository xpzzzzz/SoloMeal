# P8诊断执行器：A001～A040（debug 与 holdout 两个 split）

2026-09-14第70节：v19合成留出180位置执行、审计、评审与聚合完成；Agent48/60（80%，未达85%）、固定60/60、直接26/42适用另18不适用。12个Agent失败全部保留，171退出码0/9退出码1。185请求/795947token，累计1598；恢复新增0，输入三哈希全匹配，源码7f8ab812…未变。holdout_gate=failed，真人清晰度null，P8/P5未完成。

下一步先离线修复通用查询/ID获取与错误恢复、澄清完整性、基于实际结果的后续建议；不能向旧manifest追加或重跑。源码变更后另登记有界诊断，原留出失败保留，修复后复验属于已暴露场景回归，不冒充新的盲测。

2026-09-14第69节：昨天v19统一debug 180位置已完成，恢复后离线审计评审聚合完成，新增外发0。Agent58/60、固定60/60、直接17/42适用另18不适用；A008-01漏问净含量、A014-01错误后续建议保留。190请求/833620token，累计1413；输入三哈希全匹配，180退出码均0，源码7f8ab812…不变。P8/P5未完成。

下文带日期旧段为历史，当前以第69～70节为准。

2026-09-13第68节：第67节三项离线问题已修复：恢复expiry/stale_quotes/注入文本冻结契约，metrics-v4将固定流程语义硬约束标不适用（客观判据保留），清晰度恢复mean≥4。222个不同回归用例通过、ruff通过，85%边界/完整成功/失败/缺失均有测试。源码7f8ab81290559aba68d70a2b8e672bcad78af6b6b2c413d4086292996915d79a；模型外发0/新登记0。下一步按新哈希登记调试统一重复，再合成留出；P8/P5未完成。

最新先读[修复报告](../docs/validation/p8-holdout-fix-0913.md)。当前Agent v19/direct-v1/json-tools-v2未变，聚合器v4；完整调试与留出均未登记/执行。先新源码debug 180位置、approve仅A010～12，独立审计评审聚合后再holdout 180位置、approve仅A030/31/33，执行前冻结参考价格与配置。不得重跑或追加旧manifest。语义不适用不等于客观约束免检，固定流程任务及写入等门槛仍保留。下文第67节问题为修复前历史，详情和局限见本轮报告。

2026-09-13第67节：独立审阅第66节，源码2cdd1681…核对一致，评测子集205项复跑通过；发现留出expiry/stale_quotes夹具偏离冻结契约、固定流程空硬约束评分使holdout_gate不能通过、清晰度min与冻结mean不符。仅审阅未修代码，模型外发0/新登记0。下一步先修三项离线问题并回归，再按新哈希登记批次；P8/P5未完成。

先读[独立审阅](../docs/validation/p8-holdout-review-0913.md)。本轮未执行新批次或删除旧临时脚本；下文第66节“可执行/下一步登记”为修正前历史结论，优先修复审阅问题。

2026-09-13第66节：留出A021～A040的登记/执行/审计/评审/聚合支持已按冻结标签与门槛离线补齐（`cohort_agent register --split`必填、每split仍180位置、确认扩展分置debug A010～A012与holdout A030/A031/A033、聚合升cohort-metrics-v3并按全分母判定留出85%）；同时修复`food.batch_view`返回date对象导致`get_inventory`在工具边界`json.dumps`失败、被吞成MODEL_PROTOCOL_ERROR的真实缺陷——A021此前不可能达成，REST层因jsonable_encoder被掩盖。完整套件401通过/16 MySQL跳过（Docker未运行）、评测子集205通过、改动文件ruff通过。本轮模型外发0、新登记批次0，留出与调试统一重复均未启动，P8/P5未完成。

最新先读[本轮报告](../docs/validation/p8-holdout-offline-0913.md)。当前Agent v19/direct-v1（SYSTEM正文、工具schema、json-tools-v2、业务权限未变），HEAD仍a923d77c，源码由ec7c2770…改为2cdd1681d65bc714695268fe2af49006059358fe3056148ddc9c7ae1c3867ce1。留出限制与结论同读：合成集已被实现方为编写oracle读过提示与fixture、A015/A035逐字两轮提示由harness从冻结一行描述拟定、清晰度以min≥4聚合（冻结README为mean≥4，更严不假通过）、真人清晰度仍全null、85%门槛仍未测量。下一步先给成本估算再由用户选择，随后登记两批180位置；不向v16/v13/v12私有目录追加或重跑。下文第65节及更早为历史快照。

2026-09-13第65节：v19将短/长续聊历史统一归入文本摘录，仅本轮工具结果作为活动消息；三轮回归及A015三次独立真实复验通过，旧v18失败保留。相关98项最终通过/1 MySQL跳过（分组复验有重叠），ruff通过。新增12请求/70071token，累计1223。下一步先离线补留出登记/执行/评审/聚合全链路，再新源码统一调试与留出；本轮未启动完整重复，P8/P5未完成。

最新先读[本轮报告](../docs/validation/p8-context-v19-0913.md)。当前Agent v19/direct-v1，源码ec7c27702426f689096b69d52b795ee734e59662f6b0f11068953532f10fbcaa。私有p8-A015-context-v19-0913-01～03已执行、审计、评审，禁止重跑；12份输入三哈希匹配，语义3/3仅为本次诊断，真人清晰度null。先实现cohort slots/register/load_plan、evaluate范围与split、review rubric及聚合的留出支持并补离线回归，保持冻结标签/门槛；随后按新源码哈希登记20调试三模式统一重复，再20合成留出。当前均未登记/执行，不向旧批次追加。下文第64节及更早为历史快照。

2026-09-13第64节：v16独立r2评审更正为Agent56/60、固定60/60、直接27/42适用另18不适用；退出码178个0/2个1。v17三类通用修复6/9、v18进一步修复8/9，A015-v18-02旧轮用量复用失败保留。106回归通过/1 MySQL跳过，最终22通过/1跳过、ruff通过。新增46请求/277153token，累计1211。下一步先离线处理多轮最新结果引用，再有界复验及留出全链路支持；不启动完整重复，P8/P5未完成。

最新先读[本轮报告](../docs/validation/p8-intent-v18-0913.md)。当前Agent v18/direct-v1，源码9be243feb6d6927cdedb680bd121022cea64d559fcbc0848f640126d1ceaf2ac。v16-r2修订评分已在新目录生成；v17/v18诊断均完成且禁止重跑。A015-v18-02工具正确返回160g/2蛋，回答仍写80g/1蛋，先离线核对当前轮结果引用路径再修复/独立复验。新统一180位置和留出均未登记；下文第63节及更早为历史。

2026-09-12第63节：v16完整180位置统一批次执行、离线审计/评审/聚合完成；Agent57/60、固定60/60、直接27/42适用另18不适用，合计144通过/18失败/18不适用。Agent三失败保留（A001-02数组信封、A009-01猜单位并留下待确认写入、A015-02份数表述），第62节修复的两类未复现，本批无30秒超时。191请求/818246已观察token，累计1165，墙钟22分41秒。禁止重跑manifest、失败不回填；下一步离线复核失败通用缺口后按新源码哈希登记，20留出需先扩展登记的split支持（`cohort_agent.slots()`与`evaluate_agent.py`目前只走debug）。P8/P5未完成。

最新先读[完整批次报告](../docs/validation/p8-cohort-v16-0912.md)。私有D:/SoloMeal-Acceptance/p8-cohort-v16-0912-01，manifest 69da5efe7e3fd35d78699e01cb132ba38ba197add6f9559e989d33c4f0ef640d，已完成不得重跑；逐项评审理由见[review-notes](../docs/validation/p8-cohort-v16-review-notes-0912.json)，源码仍21b2ba809c8b08cdcc71ff9d9a4f8beccf293cc8b55296c0ac2e2acb56e2091f，本段未改生产代码。以下第62节及更早为历史。

2026-09-12第62节：拒绝解释/净含量澄清修复，v14/v15各5/6且新推测失败保留；v16六独立真实复验全部通过。91回归通过/1 MySQL跳过，最终16通过/1跳过、ruff通过。新增27请求/139902token，累计974；v13同输入超时离线分析完成、根因未知。下一步新登记v16完整180位置统一重复，再20留出；P8/P5未完成。

历史入口：[修复与复验报告](../docs/validation/p8-clarification-v16-0912.md)。当时源码21b2ba809c8b08cdcc71ff9d9a4f8beccf293cc8b55296c0ac2e2acb56e2091f，Agent v16/direct-v1/json-v2/thinking=false/3000/30秒，计划新登记完整180位置、approve仅A010～12可执行模式、其余none；该项已在第63节完成。旧v13完整manifest及v14～v16诊断均禁止重跑，失败不回填。以下第61节及更早为历史。

2026-09-12第61节：v13完整180位置及恢复离线审计/评审/聚合完成；Agent55/60、固定60/60、直接20/42适用另18不适用。三首请求超时、A004拒绝解释及A008净含量澄清失败保留；A014三次通过。188请求/758184已观察token，累计947，恢复新增0。禁止重跑manifest；下一步通用修复/独立复验，再统一重复与20留出。P8/P5未完成。

最新先读[完整报告](../docs/validation/p8-cohort-v13-0912.md)。私有D:/SoloMeal-Acceptance/p8-cohort-v13-0912-01，manifest b4a32fe91c9ae8c4b23afe0625a535de4e61bd68e05bc8a88d95f66983cc6640，已完成，禁止重跑；源码仍8db7525ce63f06359d2f691bc6fe80ee6adc3c607a5e566279cb9833e7012790。下文“即将执行/未登记”均为历史。

2026-09-12第60节：v13后续操作能力边界修复及A014三独立真实复验通过；118回归通过/1 MySQL跳过、ruff通过。现有A013同输入延迟1.86/超时31.04/27.86秒，根因未知且旧失败保留。新增6请求/31208token，累计759。下一步新登记v13完整180位置统一重复，再20留出；P8/P5未完成。见STATUS第60节和docs/validation/p8-capability-v13-0912.md。

最新先读[修复报告](../docs/validation/p8-capability-v13-0912.md)。v13源码8db7525ce63f06359d2f691bc6fe80ee6adc3c607a5e566279cb9833e7012790；新统一批次尚未登记/执行，旧v12 manifest禁止重跑。以下第59节及更早为历史。

2026-09-12第59节：v12完整180位置执行、离线审计/评审/聚合完成；Agent58/60、固定60/60、直接23/42适用另18不适用。A013-02超时及A014-02不支持的忽略忌口确认路径保留，硬约束59通过/1缺失。189请求，累计753；额度中止恢复新增0，禁止重跑该manifest。下一步修复不支持的后续路径并独立复验、分析超时，再统一重复/20留出；P8/P5未完成。见NEXT_SESSION与STATUS第59节。 [批次报告](../docs/validation/p8-cohort-v12-0912.md)。下文为历史。

2026-09-12第58节：[v12修复与独立复验](../docs/validation/p8-constraints-v12-0912.md)九试次全部通过；v11两个A007失败保留。166回归及最终59复验通过（各1 MySQL跳过，包含重复），ruff通过。新增34请求，累计564。下一步新统一180位置三模式重复及20留出，P8/P5未完成，下文为历史。

2026-09-12第57节：[v4完整180位置](../docs/validation/p8-cohort-v4-0912.md)已完成执行、审计、评审及聚合。Agent56/60、固定60/60、直接26/42适用另18不适用；四个Agent语义失败保留，硬约束59/60未过100%。192请求/731007token，累计530，额度中止恢复新增0。该manifest不得重跑。下一步修复约束漂移/比较与忌口解释，独立复验后新统一重复及留出；P8/P5未完成，下文为历史。

2026-09-11第56节：[direct-v1与cohort-v4](../docs/validation/p8-direct-v1-0911.md)已实现，180专项/ruff通过，真实诊断保留两失败。v4新增direct_prompt_version/direct_system_sha256配置字段，所有直接路径无工具、实际提示与输入哈希受审计；v3历史可读。新完整180位置已登记未执行，manifest及执行约定见报告/NEXT_SESSION。累计338请求，P8/P5未完成。

2026-09-11第55节：[v10查询与预览修复](../docs/validation/p8-routing-v10-0911.md) A002/A016各三个真实试次通过，173回归通过/1 MySQL跳过、ruff通过；累计333已知聊天请求。下一步直接模型独立提示版本化、新完整cohort及留出，P8/P5未完成。旧批次和下文历史结果不回填。

2026-09-11第53～54节：[真实统一180位置](../docs/validation/p8-real-cohort-0911.md)已完成，Agent52/60、固定60/60，直接缺失/不适用单列。当前提示v9与该v8批次源码不同，不能向旧目录追加；[v9 A006](../docs/validation/p8-package-v9-0911.md)三个独立试次通过。RecordedModel新增私有call-XX-input.json，保存messages/tools用于动态字段核验，证据写失败不外发；新文件自动纳入评审哈希，旧缺口不补造。A002/A016等及新完整cohort/留出仍待做。

2026-09-11第52节：CLI新增--enable-thinking/--no-enable-thinking，默认沿用独立聊天配置（None省略），实际值进入attempt、model metadata与cohort校验。关闭thinking的完整A014一次通过：2请求/8.48秒/8991token，Codex语义通过，人工清晰度未知；见[报告](../docs/validation/p8-a014-thinking-0911.md)。下一步新真实统一配置/180位置登记，旧cohort不回填，P8/P5未完成。

2026-09-11第51节：A014离线重建及schema空白单变量诊断完成，一次仍31.08秒超时，18专项/ruff通过，聊天新增1；未应用生产，P8/P5未完成。详见[诊断报告](../docs/validation/p8-a014-compact-0911.md)。

2026-09-11第50节：cohort-v3固定流程独立CLI闭环完成，第二批60/60通过；修正计数/确认计时，旧批次保留。98专项及最终14复验/ruff通过，模型0。范围与后续见[CLI报告](../docs/validation/p8-fixed-cli-0911.md)。

2026-09-10第49节：参数/写入专门测量接入聚合，cohort-v3支持指定场景批准策略。114专项及最终27复验/ruff通过，模型0；口径、局限与后续CLI闭环见[测量报告](../docs/validation/p8-measurements-0910.md)。

2026-09-10第48节：cohort summarize三模式指标聚合已实现，58专项/ruff通过，模型0。参数/写入专门测量仍缺，正式门槛未完成；见[聚合报告](../docs/validation/p8-cohort-metrics-0910.md)。

2026-09-10第47节：cohort-v2已接执行前校验与评审绑定；92专项通过、最终23项复验及ruff通过。旧v1保留，新版需重新登记，正式配置未冻结、模型新增0；门槛聚合/留出仍待实现。见[联动报告](../docs/validation/p8-cohort-link-0910.md)。

2026-09-10第46节：新增cohort_agent.py离线register/audit，固定180调试位置、保留未启动、核验配置/请求证据；34专项/ruff通过。使用及范围见[cohort报告](../docs/validation/p8-cohort-0910.md)。尚未冻结正式配置，执行器运行前校验/评审聚合/留出仍待接入。

2026-09-10第45节：完整A014在3000/30秒下首请求timeout，已绑定离线评审1失败，原始证据保留。持续模型授权已明确；cohort预登记/配置校验仍待实施，见[报告](../docs/validation/p8-a014-chat-budget-0910.md)。以下为历史。

2026-09-10第44节：单次3000/60秒探针26.39秒成功，完整A014试次被审批拦截未启动。执行器新增--max-completion-tokens（1～3000），预算和30秒时限写入attempt，默认仍1500；新配置结果须独立登记，不能合并旧版本。唯一129专项通过/ruff通过，批准范围与命令见[报告](../docs/validation/p8-a014-final-budget-0910.md)。

2026-09-10第43节：`backend/scripts/probe_a014_final_budget.py`已实现单次3000/60秒探针，72专项/ruff通过；外发审批阻塞，真实新增0。具体命令、批准范围和停止条件见[报告](../docs/validation/p8-a014-final-budget-0910.md)。以下为历史记录，完整评测仍未启动。

2026-09-10第42节：A014有界超时诊断已执行两请求后停止，精确重放返回length/空正文/1500输出全reasoning；短健康探针通过。[报告与下一版本边界](../docs/validation/p8-a014-timeout-0910.md)。66专项通过，生产参数未改，A014仍缺最终回答。以下为历史记录。

2026-09-10评审入口更新：`backend/scripts/review_agent.py`支持20调试场景的三模式离线评审，见[使用及本次证据](../docs/validation/p8-review-0910.md)。先登记本批全部已启动试次，再填写副本中的criteria/reviewer，不能删失败项；原始report不改。示例（输出文件必须不存在，父目录先创建）：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/review_agent.py init --trial D:/SoloMeal-Acceptance/TRIAL-1 --trial D:/SoloMeal-Acceptance/TRIAL-2 --output D:/SoloMeal-Acceptance/review-NEW.json
backend/.venv/Scripts/python.exe backend/scripts/review_agent.py score --review D:/SoloMeal-Acceptance/review-NEW.json --output D:/SoloMeal-Acceptance/scores-NEW.json
```

init同时生成 `.manifest.json`；评阅只填写review中的reviewer、criteria和人工clarity字段，保留manifest。criteria证据格式为`{"file":"report.json","pointer":"/output/result/message","reason":"实际核对理由"}`，多轮输出按数组索引引用。评分输出保留未评分、不适用及未知usage；不合并跨版本成功率，P8 gate仍incomplete。当前10旧试次离线评审2通过/5失败/3未评，只有v8 A018/A020填写Codex语义，人工清晰度全null；69项专项通过。A014有界诊断设计见报告，尚未执行新探针。以下带日期段落均为历史记录。

2026-09-10最新：20调试场景驱动仍齐备，当前solomeal-agent-v8/json-tools-v2。本轮A018/A020通过，A014成功推荐保留忌口后最终模型请求超时，回答验收仍缺；全部v6～v8失败和请求见[忠实性报告](../docs/validation/p8-faithfulness-0910.md)。下一步三模式结构化/语义评审入口及A014有界诊断，补齐回答证据后统一冻结/完整重复/留出。下文带日期段落为历史记录。

上一段[总量与澄清报告](../docs/validation/p8-totals-clarify-0910.md)记录required_ingredients本次总量修复、A009猜单位失败和v5复验。A014/A020最新回答仍有虚构重查/时间，task_success与human_clarity保持null。不同prompt/源码版本不可混为同配置重复，20留出及完整三模式未执行。下文带日期段落为历史记录。

2026-09-10时序扩展：支持12个调试场景。A015同session两次消息校验20分钟/1→2份；A016正确预览后外部改米为0，批准及同键重试均须409、无新增做饭写入。A016内置故障驱动，不使用--confirmation；直接模型不执行写入或自动判成功。约定和证据见[时序调试](../docs/validation/p8-temporal-debug-0910.md)。

以下入口段落从冻结README迁回此动态文档，保留历史内容；README恢复原freeze-v1字节哈希，未修改冻结值、场景或门槛：

2026-09-10当前入口：[DRIVER.md](DRIVER.md)；执行器已支持10个调试场景。A005勘误见amendments-v1.1.json；A007在首次执行前按amendments-v1.2.json改用low_stock以实际产生未知采购费用。原清单/冻结文件保留。下文“未实现/未执行”是初始冻结时状态，最新运行和中断以STATUS第36节为准。

2026-09-10：现支持10个调试场景，新增A006整包装预算和A007缺报价。A006使用quoted：零库存，大米100g/包3元、鸡蛋1个/包2元；预算5元，白米饭/慢煮饭3元、蛋炒饭恰好5元。此夹具没有超预算候选，不能声称真实验证了拒绝超预算分支。A007原standard库存足够，与未知采购费用oracle矛盾；首次执行前冻结amendments-v1.2.json和freeze-v1.2.json，改用既有low_stock（50g大米、0鸡蛋、无报价），结果标A007-v1.2。原清单及旧freeze不改。

预算判定核对候选集合、实际预算参数、份数、缺料数量、包装数/购买量/费用、price_complete与budget_feasible；回答语义与人工清晰度仍不自动计分。业务快照新增quotes，直接模型获得实际报价，避免带报价夹具却传空报价的不公平输入。固定流程仍为已知结构化意图；--confirmation仅A010～A012支持。预算实测及断电中断记录见[预算报告](../docs/validation/p8-budget-debug-0910.md)。以下带日期段落为历史进展，当前支持范围以上述说明为准。

最新：已支持8个调试场景及`--confirmation none|approve|cancel`（仅A010～A012的可执行模式，默认none）。先评分预览/确认前不变，再独立记录批准或取消扩展；不混入原场景分数。A005在首次运行前用amendments-v1.1.json修正矛盾oracle，原v1清单未改。当前JSON协议为json-tools-v2，历史调用使用合法tool对象，非法历史参数保留为数据；详见[本轮结果和局限](../docs/validation/p8-confirmation-debug-0909.md)。以下前三场景入口描述为此前记录，新增用法以上述报告为准。

2026-09-09后续：新增`--tool-protocol native|json`，不传时使用Settings配置，应用默认native。指定json使用完整schema的严格JSON工具封装，绕过本次原生可空整数兼容问题，仍不强转参数。A003同配置三次通过，A001通过，A002有一次响应失败、另一次独立复验通过；见[协议实测](../docs/validation/p8-json-protocol-0909.md)。留出及A004以后仍未运行。失败响应正文仅显式私有评测记录，不回显API。

2026-09-09。`backend/scripts/evaluate_agent.py`实现standard合成夹具及前三个调试场景的三种模式。不是20调试/20留出完整执行器；不改变v1场景、门槛或freeze文件。默认固定流程，不会调用模型。真实模式需显式`--send-model`，这属于脚本操作开关，不改变用户已经给出的授权。

在仓库根目录运行，输出目录必须不存在：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --scenario A003 --mode fixed_workflow --output D:/SoloMeal-Acceptance/p8-fixed-NEW
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --scenario A003 --mode direct_model --send-model --output D:/SoloMeal-Acceptance/p8-direct-NEW
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --scenario A003 --mode agent_tools --send-model --output D:/SoloMeal-Acceptance/p8-agent-NEW
```

三个mode均使用临时SQLite和新合成账号；迁移数据库URL只在进程临时覆盖并恢复，应用不连接开发库，不开启视觉、不启动网页服务。真实模式从已有Settings读取模型配置，仅在内存中开启聊天开关，不改.env。固定流程直接给定结构化参数，无自然语言理解；直接模型得到同一用户库存/菜谱/偏好快照、无工具；Agent沿用应用SYSTEM和8工具、最多8轮，失败不自动重试。当前没有确认、取消或反馈场景驱动，不应传入其他场景假称覆盖。

真实原始响应要求写入仓库外私有目录。每次请求先独占写call-N-attempt.json，成功或失败再写独立result；中断留下未完成attempt，禁止覆盖或从同目录重跑。记录来源commit/未提交源码哈希、数据/协议/SYSTEM/工具哈希、实际参数与httpx版本。重跑创建新目录，不用新结果替换旧失败。每次命令只执行1个试次，不满足正式每场景每模式3次要求。

report.json中的objective_pass只校验目标工具执行/推荐候选及业务状态不变。A003要求实际推荐工具带整数20分钟、1份，候选是白米饭和蛋炒饭；失败后偷偷删约束使用30分钟默认值不得通过。task_success和human_clarity保持null，因为回答语义尚需单独评阅。直接模型文字输出不自动打分，即使返回错误文字也不能自动成功。task_success=null不是失败被抹除：传输失败同时显式objective_pass=false，尝试和错误分类保留。

`ChatModel.complete_with_metadata()`返回message和每次独立metadata，`complete()`保持原返回结构。无共享last-response状态，无自动日志/重试；ModelCallError继承AppError、原公开code/message不变。metadata只保留usage已知非负整数、请求参数/哈希、耗时和固定诊断，不含URL、密钥、输入文本、上游原始错误或任意usage扩展。缺usage记null，request_sent表示已进入HTTP请求（连接失败时不代表提供方已收到或计费）。不记录响应ID或账单；无计费率时cost不能由token臆造。

真实A003首轮发现字符串整数导致校验失败，现给模型返回受控字段location/type和修正提示，未知字段名替换为unknown_field，最多10项；不含input/ctx/异常原文。严格整数schema、用户约束和业务权限保持。最终效果与历史失败见docs/validation/p8-agent-debug-0909.md。
