# A014 单次输出预算探针（2026-09-10，单次成功，完整闭环待批准）

## 用户批准后实际执行

用户明确“批准,请继续工作”后执行一次，三输入哈希与上轮基线payload匹配。26.394733秒HTTP200、stop、有效final；4863输入、915输出、5778总token，其中735 reasoning。输出上限3000，等待60秒，thinking不发送；本次实际低于生产30秒时限。原始四文件保存在D:/SoloMeal-Acceptance/p8-A014-final-budget-v1-0910-01，哈希及指标见[p8-a014-final-budget-0910.json](p8-a014-final-budget-0910.json)。此前审批拒绝不是模型失败，没有回填响应。

Codex核对：保留鸡蛋忌口，候选为慢煮饭30分钟与白米饭20分钟，均1份/80g大米/电饭锅/无需补购，未虚构重查或写入；符合这条已有推荐结果。回答提及内部空排除项和结构化条件，人工清晰度仍null。本次未执行工具，仅重放最终请求，task_success仍null；单次成功且实际输出少于1500，不能证明3000预算带来稳定收益或解决历史超时。

增加独立聊天配置SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS，默认1500、范围1～3000，仅整数量；支持环境变量十进制整数字符串，拒绝布尔/小数/越界。传输payload和metadata共用配置，30秒时限不改，不套用视觉thinking。执行器增加--max-completion-tokens并将预算/时限写attempt；.env未改，默认生产行为保留。

最终按唯一用例129通过：初轮128通过/1失败（严格整数拒绝环境字符串），修正后29项模型传输全通过；不把两轮结果相加。ruff通过，两个既有弃用警告。覆盖模型/JSON协议/48执行器/评审/冻结/两种探针；不是全后端/MySQL验收。

随后尝试一个完整A014试次，被自动审批在启动前拒绝，理由是最多8模型请求超出刚批准的单次探针数量/内容流转/成本范围。未绕过、未启动，D:/SoloMeal-Acceptance/p8-A014-chat-budget-v1-0910-01不存在。下一步需明确批准这一个完整合成A014试次（最多8请求、每请求3000输出上限、30秒等待、无自动重跑、同DashScope服务及私有新目录）。命令：

```powershell
.venv/Scripts/python.exe scripts/evaluate_agent.py --scenario A014 --mode agent_tools --tool-protocol json --max-completion-tokens 3000 --send-model --output D:/SoloMeal-Acceptance/p8-A014-chat-budget-v1-0910-01
```

本段真实聊天1、视觉0、5778已观察token、费用null；累计122已知聊天请求，另1预算关机无返回尝试，30视觉保留。完整A014仍未验收，P8/P5保持IN_PROGRESS。以下是批准前记录，保留历史，不代表当前阻塞仍在单次探针。

## 批准前记录

`backend/scripts/probe_a014_final_budget.py` 实现 `a014-final-budget-v1`：复用上轮 reconstructed 校验 v8 第二请求 messages/tools/wire 三哈希，再核对1500/60秒基线完整payload哈希。新请求只改输出上限为3000，等待60秒，不发送thinking参数，无重试或健康探针，不执行业务工具。生产1500/30秒、SYSTEM和.env未改。

共两次自动审批拒绝，均发生在进程启动前，不计真实请求。首次理由为潜在敏感提示/工具上下文及未明确目标。随后只读核实目的地主机为dashscope.aliyuncs.com，重建输入仅含项目提示、8工具schema、合成不吃鸡蛋要求、recommend_meal调用和有合成来源标记的白米饭/慢煮饭结果（各80g），三哈希匹配；按交接既有授权申请复核。第二次仍认为可信用户内容没有明确授权将这份具体prompt/tool上下文发送至DashScope。没有换入口或绕过限制。新输出目录不存在；本轮真实聊天0、视觉0、无新增usage或响应。

后续需用户明确批准：将上述A014合成请求及项目提示/工具定义发送到既有阿里云DashScope qwen3.8-flash，一次3000输出token/60秒请求，在D:/SoloMeal-Acceptance/p8-A014-final-budget-v1-0910-01保存私有响应。密钥仅作既有服务认证，不输出；不触碰真实数据库。请求内容虽为合成数据，项目提示和工具定义仍会传给外部服务。

获得批准后在backend目录运行：

```powershell
.venv/Scripts/python.exe scripts/probe_a014_final_budget.py --source D:/SoloMeal-Acceptance/p8-faithful-A014-agent-v8-0910-01 --baseline D:/SoloMeal-Acceptance/p8-A014-timeout-probe-v1-0910-01 --output D:/SoloMeal-Acceptance/p8-A014-final-budget-v1-0910-01 --send-model
```

若仍length/空正文/timeout，停止，不继续上调。若有效final，核对忌口、候选、数量和操作事实，以及是否30秒内，再决定独立聊天配置与完整真实A014闭环。不得将单请求重放计成任务验收。

验证：最终72项通过（新增6、旧超时探针5、模型传输/工具协议/评审/冻结61），ruff通过，两个既有第三方弃用警告。初轮11为子集不累加。测试覆盖成功/工具返回/空正文/超时/HTTP错误均只请求一次、文件不可覆盖、预算/timeout及payload精确匹配、基线任一参数不符拒绝；旧三哈希和两请求边界仍通过。

P8/P5仍IN_PROGRESS，A014未修复，统一冻结/完整cohort/三模式重复/留出待做。未运行完整backend/MySQL/浏览器/远程CI/真人测试，未改开发库/根data/.env/前端/迁移/原插件，无提交推送。PLAN正式范围和门槛不变。
