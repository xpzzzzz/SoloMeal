# P8聊天观测与前三个真实调试场景

2026-09-09。新增聊天请求26次（视觉本轮0次，历史视觉30次另计）。P8仍IN_PROGRESS：A001/A002真实工具路径通过；A003限时推荐失败未解决。原始响应在D:/SoloMeal-Acceptance/p8-*专用目录；仓库[指标JSON](p8-agent-debug-0909.json)只含脱敏元数据、状态与来源哈希。

## 实现

- ChatModel增加complete_with_metadata，每次独立返回message和metadata；complete兼容原调用。记录模型、httpx版本、输入/工具哈希、30秒/1500输出token、未指定采样参数、实际usage及固定错误分类。ModelCallError保留AppError公开code/message。不持久化业务遥测表，不输出密钥/上游原文，不自动重试。未知token为null。
- scripts/evaluate_agent.py实现standard临时SQLite/合成账号和A001～A003三模式入口；固定流程无模型，直接模型使用数据快照无工具，Agent原工具循环最多8轮。首次写attempt，禁止覆盖；真实原始结果必须放仓库外。进程内临时开启聊天，不改.env。所有模式都比较库存/事件/菜谱/用餐/方案前后快照。
- 新增受控参数错误反馈：已知字段location/type、未知字段替换、最多10项；不含input/ctx/用户原始值。新增solomeal-agent-v2系统提示说明JSON整数/布尔类型和保留用户条件。严格schema未放宽；这两项改进尚未解决指定模型的A003问题。

执行方式见[evaluation/DRIVER.md](../../evaluation/DRIVER.md)。100场景/门槛/freeze文件未修改，清单中的not_run是冻结时状态，实际运行状态以本报告为准。

## 真实结果

配置qwen3.8-flash，未发送聊天enable_thinking扩展，采样参数使用提供方默认且实际值未知。每个初始场景每模式仅1次；后续A003重跑使用不同代码/提示哈希，不能拼成同配置3重复。无网页/真机操作，均通过真实后端TestClient与HTTP模型适配器运行。

| 场景/模式 | 请求 | 秒 | 结果 |
|---|---:|---:|---|
| A001固定流程 | 0 | 0.005 | 库存查询通过 |
| A001直接模型 | 1 | 9.710 | 返回文字，语义待评 |
| A001 Agent | 2 | 6.144 | 查询工具及终态通过，0无效调用 |
| A002固定流程 | 0 | 0.008 | 菜谱查询通过 |
| A002直接模型 | 1 | 28.524 | 返回文字，语义待评 |
| A002 Agent | 3 | 16.536 | 工具及终态通过，0无效调用 |
| A003固定流程 | 0 | 0.018 | 20分钟/1份候选通过 |
| A003直接模型 | 1 | 14.076 | 返回文字，语义待评 |
| A003 Agent首轮 | 5 | 28.831 | 失败，3无效调用后丢失20分钟条件 |
| A003安全错误反馈复验 | 3 | 38.427 | 失败，2无效调用后单请求30秒超时 |
| A003 v2提示复验 | 8 | 57.697 | 失败，5无效调用后使用空条件查询 |

全部业务快照不变。首轮A003的最终文字看似过滤了30分钟菜，但实际工具用默认30分钟，不能当作硬约束执行成功。两次复验失败仍保留，不替换或平均成通过。objective_pass只是工具/状态检查，task_success与人工清晰度始终null；不能称已有人评或正式效果提升。

额外2次schema探针，不接业务工具：第一份仅两个required整数参数、无SYSTEM，返回真正JSON整数；第二份使用完整8工具/当前SYSTEM，仅将可空整数anyOf改为type数组，仍返回字符串。完整请求schema和返回参数在各probe私有目录。第一份用户提示“请调用recommend_meal，推荐20分钟内的一人晚餐。”；第二份为冻结A003提示加当前SYSTEM。两探针不构成仅改变一个变量的因果实验，只支持继续检查schema兼容，不能认定服务商实现缺陷；没有把type数组方案写入业务代码。

所有26请求中25份有total_tokens，已观察合计91326 token；另一份超时用量未知。没有提供方计费率/账单，成本为null，不能把91326当完整消费量。不跑留出、不提供成功率/P95提升数字。

## 工程验证

backend目录最终执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_model_transport.py tests/test_agent.py tests/test_agent_evaluation.py tests/test_evaluation.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-p8-chat-final-0909 -q
.venv/Scripts/python.exe -m ruff check app/services/agent.py app/services/agent_model.py scripts/evaluate_agent.py tests/test_agent.py tests/test_model_transport.py tests/test_agent_evaluation.py --select F,B,I
```

最终46 passed（27.43秒），ruff通过，2条既有第三方弃用警告。中间39通过/1失败是新测试把中文JSON转义中的“20”误认作输入泄漏；改为ensure_ascii=false后针对Agent10通过，最终合并46通过。初期28项/执行器10项是中间结果，不相加。

未改事务/schema迁移/前端/原插件，未跑MySQL、完整后端、浏览器或远程CI；开发数据库和根data不触碰。无提交/推送。

下一步：先离线检查完整工具schema中可空整数/$defs/默认值等兼容因素，制作单变量诊断，找到不丢失API语义的表示再复验A003；不能偷偷将字符串当合法整数。之后扩展A004～A020的夹具/确认/反馈驱动、人工评阅、冻结统一配置后跑留出与3重复。当前实现不覆盖完整40个Agent场景或真实写入闭环。
