# A014完整试次：3000预算仍首请求超时

2026-09-10，用户明确“批准,以后不需要问我,全部批准”，继续执行第44节准备的完整A014合成试次。持续授权覆盖本项目后续开发/验收所需模型调用、项目提示/schema/合成对话与工具结果发送既有DashScope及仓库外私有证据保存，不再逐批请求同类批准；仍隔离数据、保留失败并记录用量。

backend目录执行：

```powershell
.venv/Scripts/python.exe scripts/evaluate_agent.py --scenario A014 --mode agent_tools --tool-protocol json --max-completion-tokens 3000 --send-model --output D:/SoloMeal-Acceptance/p8-A014-chat-budget-v1-0910-01
```

首次模型请求31.2641725秒timeout，HTTP状态及usage均null；整体31.3116814秒，退出1。实际请求1，工具事件0、无效调用0、业务快照不变，objective_pass=false。独立SQLite合成场景，未读取/修改开发库存。3000输出预算、30秒请求时限、solomeal-agent-v8/json-tools-v2，thinking不发送，原prompt/schema/.env保持。

这次发送完整场景首请求，上次成功探针重放已有推荐结果后的第二请求；不能拼成成功轨迹。上调预算没有让本次完整试次通过，A014仍未修复。不增加等待、不继续上调或盲目重跑。

原始目录完整保留，哈希及指标见[p8-a014-chat-budget-0910.json](p8-a014-chat-budget-0910.json)。review/manifest/scores已绑定证据，原report不改；客观失败使评审task_success=false，语义和human_clarity保持null。评审为1失败、无合并成功率、P8 gate=incomplete。

本段真实聊天1、视觉0、非空usage0，token/费用未知，不记零成本。累计123已知聊天请求，另预算关机1个无返回尝试、30视觉保留。额度中断发生在写报告阶段：原始响应与三个评审JSON已落盘，报告/摘要/STATUS未落盘，恢复后按已有证据补记，未重发请求。

本段无业务源码修改，不重复运行上一段129项测试；恢复时实际核验原始证据哈希、失败评审及无工具/业务变化。P8/P5仍IN_PROGRESS，完整20调试三模式重复、20合成留出、人工清晰度、MySQL及P4～P9既有验收保留。

下一步可独立推进完整cohort预登记、统一配置一致性校验和离线统计；不能因此启动正式评测或宣称A014通过。新模型诊断须先定义单变量方案，优先离线检查输入上下文是否可精简，保持完整工具语义、忌口和确认约束；不得通过改门槛掩盖失败。该方向尚未实现或验证。

未改.env/开发库/根data/前端/迁移/原插件，无提交推送，未运行完整backend/MySQL/浏览器/远程CI/真人验收。
