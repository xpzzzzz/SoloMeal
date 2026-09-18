# 单 Agent 工具运行（P5 当前实现）

2026-09-14第71节：v20补通用ID查询/结构化只读恢复反馈及澄清、报价查询规则；194回归通过/1 MySQL跳过、ruff通过。9个已暴露场景诊断6通过3失败（A026编造报价日期、A027不查询、A035首轮回答超时），原失败保留。新增17请求/已观察94749token/1缺usage，累计1615；17输入三哈希匹配，源码33816f7d…；P8/P5未完成。 [本轮报告](validation/p8-recovery-v20-0914.md)。下一步先离线处理报价事实来源/任意缺口计算工具边界与必要查询完成状态，分析A035既有超时证据；不要仅继续堆提示。v20九目录及v19旧manifest禁止重跑/追加；回归不冒充新盲测，原留出48/60不变。

2026-09-13 v19更新：每次续聊均把旧用户/助手文字归入带来源的历史摘录，旧工具调用与结果不作为活动消息重放；本轮工具消息完整保留。短文本不截断，摘录超过24000字符时取末8条、每条前1000字符；继承时展平，原run记录不修改。历史只辅助理解指代，库存和可行性需重新查询。A015三次有界真实复验通过，不代表完整多轮验收；见[报告](validation/p8-context-v19-0913.md)。下文按日期保留历史实现与验证。

模型适配参考[OpenAI官方function calling规范](https://developers.openai.com/api/docs/guides/function-calling)。当前实现Chat Completions兼容HTTP传输，不绑定特定模型；不代表所有模型均支持该端点或参数。

## 配置

backend/.env中由开发者配置（不要覆盖已有数据库配置）：

```dotenv
SOLOMEAL_AGENT_ENABLED=true
SOLOMEAL_MODEL_BASE_URL=https://api.openai.com/v1
SOLOMEAL_MODEL_NAME=填写你账户可用且支持工具调用的模型
SOLOMEAL_MODEL_API_KEY=填写密钥
```

默认关闭，未配置返回MODEL_NOT_CONFIGURED。密钥用SecretStr读取，只用于配置服务的Authorization；不写数据库、不发给模型、不回显上游错误。当前没有真实模型调用证据，测试均注入Scripted模型；用户已有Codex额度不能直接充当本应用API凭据。
配置第三方兼容服务时，确认其支持tools、parallel_tool_calls=false、max_completion_tokens；本轮未配置或连接任何第三方模型。模型调用超时30s，单次输出最多1500 token，run至多8次模型尝试，失败也计数；60k字符上下文阈值，超限需新对话。

## 状态与工具

ready → running → ready/completed/awaiting_confirmation/failed。
awaiting_confirmation → approved/cancelled；failed或过期running可retry回ready，保留尝试次数；运行中可取消。

工具白名单：get_inventory、list_recipes、recommend_meal、estimate_purchase、propose_plan、get_cooking_history、prepare_inventory、prepare_cooking、prepare_undo。
Pydantic拒绝额外参数和身份注入。未知工具和业务错误供下一轮修正。prepare类工具只预览，必须用户确认才能写入；没有任意HTTP或shell工具。
Agent侧规划条件（recommend_meal、propose_plan、run.constraints）没有quotes字段：价格来源与日期只取用户已保存的报价记录；REST的/recommendations与/plans仍可带本次报价。
propose_plan只存待确认输入和快照。approve在同一数据库事务内校验快照并保存meal_plan，依然不扣库存；用户另行在方案页确认做饭。过期草稿需取消并重新提出。

agent_runs存消息、状态、pending、结果、步骤与租约；tool_executions存工具、校验后参数、结果、耗时。agent_sessions保存独立会话，兼容受控parent_run_id续聊，不接受跨用户引用。有界上下文采用文本摘录，非模型语义摘要。
网络请求期间释放数据库锁；120s运行租约+随机标识防止重复推进和过期worker覆盖；取消使迟到响应失效。恢复可能重新调用模型并产生服务商费用，但不会重复执行业务写入。所有写业务确认复用operations幂等事务。

## API/UI

POST /api/v1/agent/runs：message、可选parent_run_id；需Idempotency-Key。
GET /agent/runs及/{id}恢复当前用户记录（这里省略/api/v1前缀）。
POST /agent/runs/{id}/advance：执行一轮模型/工具，返回新状态。
POST /agent/runs/{id}/approve、cancel、retry：需Idempotency-Key。

网页“一人食助手”自动逐轮advance至暂停或完成；刷新后从运行记录恢复。工具结果以文本转义展示。
模型推进仍用逐步HTTP；已有SSE状态事件重放和独立session UI，没有后台worker或token流；刷新需重新登录后再恢复run。

## 待验收

真实模型端到端、上下文摘录效果评测、自动重规划质量、Agent评测集、限流与生产部署。SSE断线与多标签页已用本地Chromium离线仿真浏览器套件覆盖（见validation/p6-e2e-0908.md），现已配置独立 browser-e2e CI job 并汇入 ci-complete，远程运行仍待验收（见 validation/review-ci-0908.md）。
不能把Scripted测试或网页构建通过写成真实模型能力指标；用户文本/工具数据不可作系统指令，业务权限由代码强制。


## 持久化SSE状态事件（2026-09-05已实现）

GET /api/v1/agent/runs/{id}/events；以Authorization Bearer认证，禁止token放URL。
客户端Last-Event-ID为runUUID:sequence，也可用after查询参数。跨run游标422、超前游标409，其他用户404。每个状态变化有递增序号，与对应run修改同事务提交；幂等重放不再次发事件。
run_state payload仅含status/steps/event_seq，客户端再获取当前完整run；不是内部推理或模型token流。
断开窗口20秒，stream_end reconnect字段表明是否重连，终态关闭。活跃连接定期复查会话，失效发auth_expired后结束。
事件查询是短事务并在线程执行，不持有数据库连接等待网络。连接不推进模型，断线不会重复产生模型调用。
前端解析中文UTF-8分片/多帧/心跳，重连带游标且去重；读取当前run时按event_seq拒绝旧状态覆盖。新增3个前端测试；当时的完整浏览器断线/多标签页验证在2026-09-08由frontend/e2e补齐，见下文。
模型传输已用httpx.MockTransport测试参数、拒绝重定向、错误脱敏、超时和畸形响应，但真实服务商兼容性仍未知。

## 2026-09-06 独立会话与有界上下文

GET /agent/sessions及/{id}返回当前用户会话、版本、latest_run_id和run清单。创建run可传session_id+expected_session_version，不传时建立新会话。兼容parent_run_id，但只允许最近已结束的run，避免分叉覆盖已有会话。跨用户404，旧版本409 SESSION_CONFLICT；前次run未结束409 RUN_BUSY。

run.constraints保留规划条件，续聊与成功规划工具仅覆盖显式字段，未修改条件保持；约束再次经过Pydantic与业务规则，不能绕过忌口。页面可查看当前结构化条件。自然语言参数理解仍需真实模型验收。

旧上下文超过24000字符，继承时取近期最多8条用户/助手文本的前1000字符，附原run引用；不复制旧工具输出。context_summary标记为摘录，不声称语义总结。原run完整消息及工具记录保留，当前约束独立保存。60k运行上限保持；此策略未经过正式多轮模型评测。

迁移da41905c772e，18业务表；MySQL专项15通过。页面已验证模型未配置失败、刷新重登录恢复相同run；未冒充真实模型闭环。

## 显式确认写入（2026-09-06）

prepare_inventory接受BatchInput，prepare_cooking接受CookingInput，prepare_undo接受cooking_id。预览返回kind/request/state/preview/expires_at，15分钟有效；approve锁定用户事务后重算并对比状态，调用与普通页面相同的food服务，同一操作内提交库存事件与run状态，失败全回滚。

prepare_cooking还校验结构化条件、已保存忌口/厨具/时间/预算；库存不足不提出确认。撤销按消费明细恢复，已归档批次保持归档。批准时模型不能替换参数，取消/过期拒绝，重复批准返回原结果。propose_plan仍只保存方案，不做饭。

get_cooking_history返回最近30条用餐ID、名称和状态。有歧义应询问用户，不能假定最近一条就是撤销目标。测试使用Scripted/MockTransport；真实用户意图理解仍待模型验证。端到端与失败记录见validation/crud-agent-0906.md。


2026-09-07：recommend_meal默认使用用户保存的报价；propose_plan在预览时冻结相关报价输入，批准时不读取后来更新的报价，其他库存/日期/偏好快照检查保持。新增MySQL回归验证待批准期间修改报价，保存方案仍与预览金额一致。采购目前从页面操作，未新增Agent采购工具；白名单仍8项。


2026-09-08：前端请求按登录代次隔离，旧响应不覆盖新用户或触发新登录退出；AgentPanel卸载后不推进下一轮。注销不取消服务端当前轮，重登录可恢复ready或待确认run。续聊冲突后同步列表并提供“打开最新运行”，保留未提交输入；历史run不能继续发送。运行中注销和正常网络双标签页续聊已浏览器验证，实际离线及移动端仍待验，见validation/session-recovery-0908.md。


2026-09-08（同日第二段）：把浏览器验收固化为 frontend/e2e 可重放套件（`npm run e2e`，Playwright chromium + 隔离脚本夹具与临时SQLite）。运行中断网仅恢复后继续且工具不重复执行、离线横幅与恢复后自动同步、离线标签页取消不生效而另一页确认后落后页收敛，均已断言；同时覆盖采购丢包重试与双账号隔离。夹具新增 `--data-dir` 供运行器自清理。这些是脚本模型下的前端行为证据，不证明真实模型能力，套件也尚未接入CI。详见 validation/p6-e2e-0908.md 与 STATUS 第22节。

## 2026-09-09 P8真实调试与观测

ChatModel新增complete_with_metadata返回本次message及usage/参数/耗时/脱敏失败分类；complete保持兼容。ModelCallError沿用公开AppError错误码，不给API返回元数据；记录由独立评测包装器显式执行，业务库未加遥测表。缺失token为null；不改聊天30秒/1500输出token，不自动发送视觉思考扩展。

现有配置已通过A001库存查询、A002菜谱查询的真实工具循环；A003首轮暴露字符串整数和丢约束，新增安全字段错误反馈后单独复验，结果见[真实调试报告](validation/p8-agent-debug-0909.md)。这些是前三个合成调试场景，不代表完整P5闭环或P8留出通过。真实原始响应留私有验收目录；[执行方式和边界](../evaluation/DRIVER.md)。

## 可选JSON工具协议（2026-09-09）

SOLOMEAL_MODEL_TOOL_PROTOCOL默认native；设json时使用json-tools-v1严格JSON封装，模型仍看到完整工具schema，运行时继续校验全部类型和确认要求。不强转字符串、不修改API的null/省略语义；旧run保持同样消息结构，传输时转换历史工具消息。不自动重试或自动切换协议。A003三次同配置通过，但A002仍留一次解析失败；[配置与实测范围](validation/p8-json-protocol-0909.md)。应用要使用该协议，显式设置启动进程环境，本机.env未改。

## json-tools-v2与真实确认调试（2026-09-09）

JSON传输的合法历史assistant调用现在使用与输出一致的tool/name/arguments封装，避免模型模仿另一种历史展示格式；非法历史参数原样保留为标注数据，不强转类型。模型仍须等待明确确认才能执行入库/做饭/撤销。8个调试场景与真实模型确认/取消/同键重放已有局部证据，但不同协议版本的失败/复验分开记录，完整P5/P8仍待验，详见[确认报告](validation/p8-confirmation-debug-0909.md)。

## 报价事实来源与缺口估算（2026-09-14）

取代上文2026-09-07“白名单仍8项”的结论：Agent白名单为9项，新增只读estimate_purchase。
动机是留出诊断中出现的“自造报价”：Agent规划条件曾暴露quotes数组，模型可同时填写source与observed_on，
freeze_quotes让本次报价覆盖保存报价，工具再把这两个字段原样回显，虚构的来源和日期因此变成看起来可信的工具证据。
现在Agent可见的schema（AgentPlanningInput、AgentPlanInput、RunInput.constraints）不含quotes，
run.constraints与工具回显中的报价一律来自服务端price_quotes行；REST /recommendations与/plans的
PlanningInput保持可带本次报价，页面与既有方案快照行为不变。estimate_purchase只接受用户说出的
食材、数量和（可选）预算，按该食材保存报价向上取整为整包，返回packages/purchase_quantity/estimated_cost
及来源日期，不推断份数、不关联菜谱、不预留库存、不写入。

A026的冻结oracle（expected_action=recommend_meal、servings=3）与它保留的失败未改写，判据不改分数不回填；
但“缺190克”在自然语言里并不等于“3份”，新工具与冻结意图并不等价，因此本节的能力扩展不属于已冻结的40场景覆盖，
需要另登记prompt/tools版本与有界诊断后才能取得任何真实模型证据。详见
[报价与缺口估算报告](validation/p8-purchase-v21-0914.md)与STATUS第72节。


## 推荐回答与可执行状态（2026-09-16）

成功recommend_meal为本轮最后工具时，服务端recommendation-response-v1生成最终message及逐菜next_actions，原模型回答保留为model_message；source_step绑定工具证据。仅库存足够、无缺料且预算通过才建议请求预览；实际预览/确认仍重新校验。其他工具回答与后续失败不套用这一模板。页面展示message，后续历史也继承实际展示内容；模型原文须另行评审，不能把模板正确率当模型语义提升。范围和测试见[验证报告](validation/recommendation-response-0916.md)。
