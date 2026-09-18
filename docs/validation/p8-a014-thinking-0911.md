# A014独立聊天thinking单变量完整试次

2026-09-11，执行前登记a014-chat-thinking-off-v1；承接STATUS第51节。持续模型调用/合成内容外发/私有证据授权有效。

## 离线证据与决策

新增离线脚本analyze_chat_history.py，按顶层p8目录的call-*-result.json逐文件计数，不重复读取report里的副本，不包含不同文件名探针或无返回中断。118条可识别结果：首请求55（52有usage、3超时、2非法响应），后续请求63（61有usage、2超时、1非法响应）；其余有效响应不等于任务成功。首请求已观察输入373～3860token，后续3428～6423；后续可能仍是工具调用，不能统称最终请求。明细/源哈希见[p8-chat-history-0911.json](p8-chat-history-0911.json)，这不是累计用量账本，也不是同配置cohort。

A014 v8成功首请求3860输入/875输出，其中853 reasoning，24.22秒；历史最终请求重放4863输入/1500输出全部reasoning、40.88秒且空正文；3000预算final探针4863输入/915输出，其中735 reasoning，26.39秒。旧超时usage未知，不能补零或推断所有超时均因思考。较大输入也存在较快成功；第51节减少706字符仍超时，不继续微调空白。

2026-09-11核对[阿里云官方思考文档](https://www.alibabacloud.com/help/en/model-studio/deep-thinking)：qwen3.8-flash为默认开启的混合思考模型，支持enable_thinking=false。[兼容Chat API](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions)说明原始HTTP参数放JSON顶层。故单独验证关闭聊天思考；此选择有聊天文档和usage证据，不沿用视觉设置。

## 事前方案

相对第45节完整失败试次，仅发送enable_thinking=false；仍为qwen3.8-flash、SYSTEM v8、完整json-tools-v2（不压缩schema）、3000输出预算、30秒请求超时、提供方默认采样、原A014合成夹具/门槛。工具、忌口、确认规则不变。

新增独立SOLOMEAL_MODEL_ENABLE_THINKING，默认None省略；仅显式true/false有效，与视觉开关独立，.env不变。CLI --no-enable-thinking指定false；metadata/attempt用字符串false/true/not_sent，兼容cohort既有字符串配置并实际参与校验。

执行一个完整A014，最多8模型请求（既有运行器上限），不自动重跑/健康探针；隔离SQLite，只读推荐，原始证据新目录D:/SoloMeal-Acceptance/p8-A014-thinking-off-v1-0911-01。先核对首请求三哈希与第45节一致，再核对工具结果、最终回答、业务不变、忌口/数量/操作事实及耗时。失败停止；通过只算这次调试，后续统一配置重复/留出另冻结，不借此修改门槛。

```powershell
.venv/Scripts/python.exe scripts/evaluate_agent.py --scenario A014 --mode agent_tools --tool-protocol json --max-completion-tokens 3000 --no-enable-thinking --send-model --output D:/SoloMeal-Acceptance/p8-A014-thinking-off-v1-0911-01
```

## 实际结果与评审

完整试次退出0、objective_pass=true；两请求均HTTP200，3.1350025秒与5.2377789秒，整体8.4777353秒。首请求messages/tools/wire三哈希与第45节旧失败完全一致。一次recommend_meal、参数合法1/1、无效调用0、未授权DML0、业务快照不变；写正确率不适用，未批准任何写入。

Codex逐项核对最终回答和工具结果：鸡蛋忌口保留，蛋炒饭被排除，慢煮饭/白米饭各需80g大米、30/20分钟、电饭锅；无虚构重试或完成写入。离线评审intent/constraints/faithfulness=true，task_success=true，人工清晰度null。原始六文件和review/manifest/scores共九文件哈希及脱敏指标见[p8-a014-thinking-0911.json](p8-a014-thinking-0911.json)。

表达局限：回答暴露后端规则和EXCLUDED_INGREDIENT内部错误码，并以“保障饮食安全”解释偏好保护；这不是已验证的食品安全结论，本段仅认可结果和操作事实。后续统一重复需继续观察语义及表达质量，不以Codex评分冒充真人清晰度。

usage：首请求3824输入/76输出/3900总token；最终请求4902输入/189输出/5091总token，合计8991。reasoning_tokens未返回，保持null，不能声称观测为零。费用未知。新增聊天2/视觉0；累计126已知聊天请求、另1预算关机无返回尝试、30视觉。

154项回归通过（模型传输/JSON协议/执行器/cohort/旧探针/新历史分析）；补充CLI开关接线后18项CLI与评审专项通过（含重复，不累加），ruff通过，2既有弃用警告。未跑完整backend/MySQL/前端/浏览器/远程CI/真人。独立聊天配置默认仍省略、.env未改，原生产提示/协议/业务语义不变，未提交推送。

A014本次回答闭环通过；仅一个试次，不能断言全部历史超时根因或稳定提升。下一步按PLAN冻结新的真实统一配置（含thinking=false）和源码，登记20调试×3模式×3次完整cohort；该诊断不回填正式位置。固定流程旧批次与所有历史失败保留，20合成留出/真人清晰度/独立小票/试用/MySQL/P9仍待执行，P8/P5整体未完成。
