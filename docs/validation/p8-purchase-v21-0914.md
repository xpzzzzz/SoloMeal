# v21报价事实来源、缺口估算与必要查询（2026-09-14，纯离线）

承接STATUS第71节。按第71节结论做三项离线工作：把报价价格事实收回到服务端、给"只说缺多少"的采购计算开一个不猜份数的只读工具边界、把"必须查询"从答案正确性里分离成可观测量，并用既有证据分析A035超时。本轮0次模型调用、0次重跑、无提交推送。v19合成留出Agent 48/60（80%，未达85%）、`holdout_gate=failed`、v20九场景6通过3失败与真人清晰度全null全部原样保留，P8/P5未完成。

## 报价事实来源（A026失效根因）

- v20的A026真实失败是模型先编造无来源ID，恢复后又填写`2023-10-27`报价日期覆盖保存报价。根因不只是提示没写够：Agent可见的`recommend_meal`/`propose_plan`输入含`quotes`，其字段由模型书写，`freeze_quotes`又允许请求报价覆盖保存报价，工具结果再把`source`/`observed_on`原样回显。写进去的日期经一次工具往返就变成"已保存事实"，任何后置提示都无法与真实记录区分。
- 现把价格事实移出模型可控状态：新增`AgentPlanningInput`/`AgentPlanInput`（无`quotes`），`run.constraints`、父轮条件继承与模型可见上下文消息都按该schema读写；REST的`/recommendations`、`/plans`仍接受本次请求报价（页面与固定流程用例不变）。工具仍返回报价来源与日期，但唯一来源是服务端`SavedQuote`。
- 提交`quotes`不再是"被忽略"，而是`INVALID_TOOL_ARGUMENTS`＋`extra_forbidden`/`unknown_field`，不返回被拒值也不给ID恢复建议——恢复建议会邀请它换个ID再来一次。既有8步上限、权限、确认、业务事务与工具输入之外的流程未改。
- 历史run的`constraints`落库时都带`quotes: []`，读取时统一丢弃该键，老行不会因schema收紧而报错或把空报价当成事实。
- 提示同步重写而非追加：包装预算/旧报价问题先`recommend_meal`，来源与日期只来自服务端记录，不能填写或编造报价日期，工具结果与用户口述价格不一致时说明差异，不能把自行算式说成工具结果。

## estimate_purchase：只说缺口时的只读估算

- 新增第9个工具`estimate_purchase(ingredient_id, quantity, unit, budget?)`：按用户说出的缺料数量与单位，取该用户该食材的保存报价，返回整包数、实际购买总量、费用、`source`/`observed_on`/`price_status`、预算判断，并带`advisory_only: true`与`scope: user_stated_shortage; no recipe, servings or inventory reservation`。不接收份数、不关联菜谱、不预留库存、不写任何业务表。
- 整包与>30天过期算法与`recommend`的缺料行共用同一个`purchase_fields`，避免同一套价格规则出现两份实现。无报价→`price_status=unknown`且金额为null；过期报价仍回来源与日期但不给估算；单位不可换算→`UNIT_AMBIGUOUS`；未知/他人ID→`NOT_FOUND`并指向`get_inventory`。
- 这补的是能力形状缺口，不是A026的分数。A026冻结题干"大米一袋100克3元，缺190克，6元够吗？"的oracle要求`recommend_meal`且`servings == 3`，而自然语言从未说3份：固定流程由harness自己POST `servings:3`，真实模型只能猜份数去凑判据。旧判据、旧失败与48/60一律不改；新工具不在冻结40场景的覆盖范围内，其真实表现需另登记协议与诊断。

## 必要查询完成状态（观测，不入门槛）

- 评测器新增`REQUIRED_QUERY = {A026: recommend_meal, A027: recommend_meal}`，只在`agent_tools`试次的report里声明"该场景需要先读保存事实"。
- `evaluation-measurements-v2`按已成功结束的只读工具事件记`observed/satisfied/answered_without_query`，把A027这类"一个字都没查就作答"与"查了但答错"分成两类缺口；`TOOL_TIMEOUT`等失败调用算未查询。未声明要求的场景与旧v1报告一律计为"未测量"。
- `solomeal-cohort-metrics-v5`读取v1和v2，新增`required_query`汇总字段但`value/threshold`固定为null、不加入`GATED`，因此各分档通过率、`holdout_gate`与全部旧分数不变；旧批次不用新数字重聚合。

## A035：只读既有证据

- 汇总v19调试/留出与v20有界诊断的私有元数据（新请求0），逐批逐模式给出时延分布、超时、同输入重放与既有v12/v13结论，数字见[JSON](p8-a035-latency-0914.json)。
- 观察：agent_tools内部`prompt_tokens`与耗时相关性弱（r=0.237，混入direct后为负），5325输入/37输出token却耗时29.64秒与7986 token更快完成同时存在；同输入重放39组内没有出现分叉结局。超时那次没有HTTP状态也没有usage，排队、传输停顿与生成缓慢无法从这批证据区分。
- 结论：v20的A035是同一时间窗内的慢尾（17请求2.5分钟里有29.64秒成功和31.00秒超时），根因仍未知；生产30秒时限与3000输出预算不动，不延长、不重跑旧目录，A035第二轮未执行与语义null保持原样，不假定已修复。

## 离线验证

- 全量后端套件exit 0：430通过／16跳过（合计446），跳过全部是MySQL门控用例（Docker守护进程未运行，本轮未启动），SQLite结果不当MySQL并发证据；13文件相关子集306通过／5跳过。改动文件ruff `--select F,B,I`全部通过（全树117项属他人未提交区域，未动）。
- 新增/改写测试覆盖：模型提交`quotes`在`recommend_meal`与`propose_plan`两条路径上被拒且不回显；190克按保存报价算出2包/200.000克/6.00元（`piece`等按单位、`kg`按小数各自通过）；过期与无报价只回状态不回金额；他人ID与单位歧义错误；`UNIT_AMBIGUOUS`与`NOT_FOUND`恢复；估算后库存、事件、方案、报价四类业务快照不变；评测层三条查询观测断言与聚合层非门槛断言。
- 工具白名单由8项增至9项，`recommend_meal`与`estimate_purchase`的description改变，故`tools_sha256`改变；源码指纹`1674f8313e0cad9bd81598a2acdd1182c6b56b58b90c23be54eca9e25126473e`，`system_sha256 a9d52adb…`，`tools_sha256 79ff5a75…`（v20为`33816f7d…`）。七份冻结evaluation JSON逐文件哈希与v20登记一致。
- 验证过程本身的一次方法学错误记录在此：首次全量跑出现8条`test_timeout_probe`/`test_tool_protocol`的teardown ERROR，根因是同一`--basetemp`被两个并发pytest会话共用、后启动者清空了目录，与被测代码无关；改为每次一个会话、换新`--basetemp`后稳定exit 0。单跑这两个文件26项全通过。

## 限制

- 本轮没有任何真实模型证据，`estimate_purchase`与"报价字段被拒后的行为"目前只有脚本/离线用例背书；模型是否会在无`quotes`字段时改用手算并谎称工具结果，仍是开放问题。
- A026的价格事实现已由服务端供给，但其冻结判据仍要求猜测的份数，故该场景在真实链路上仍可能失败；这是判据与能力的一致性问题，不是提示问题。
- `required_query`只测"有没有查"，不测"查得对不对"，也不覆盖未声明要求的场景。

## 下一步

先按v21源码在新私有目录登记小规模真实诊断（建议A026/A027/A035三个已暴露场景各一次，另加一条`estimate_purchase`新形状），执行前给出请求/token/墙钟估算并由用户确认；不做旧目录重跑或追加，回归不冒充新盲测。遗留：真人清晰度全null、MySQL/P4～P6完整验收、浏览器与真机、P9部署与备份恢复。脱敏数字与哈希见[JSON](p8-purchase-v21-0914.json)。
