# P8工具协议兼容：A003三次通过

2026-09-09。增加可选JSON工具协议后，A003在同一源码/模型/提示配置下连续3次通过，均2次请求、0次参数错误，实际工具条件20分钟/1份，业务快照不变。原生协议保持默认，旧失败未抹除；未修改.env。P8仍IN_PROGRESS，不是完整留出或生产稳定性结论。

## 排查与实现

新增可重放scripts/probe_tool_schema.py，保持相同SYSTEM、用户消息和8工具，仅分别去掉default、展开本地$ref。2次原生探针仍输出字符串整数，保留invalid_arguments。未把这些schema转换写入业务，也不能从单次探针认定服务商根因。该脚本最终显式固定native协议，避免后续环境配置影响诊断。

新增SOLOMEAL_MODEL_TOOL_PROTOCOL=native|json，默认native；应用内Settings和评测CLI均可选择。json模式保留完整Pydantic工具schema，以系统消息传输，发送response_format=json_object，不发送原生tools/parallel_tool_calls。历史工具调用和结果转成标明类型的数据消息；存储的run消息格式不变。响应只能是严格tool或final对象，转回既有runtime接口，继续执行工具白名单、Pydantic严格类型、用户权限与确认流程。不修复Markdown/重复键/NaN/多余字段，不转换字符串整数，不删除null或用户条件。

[阿里云官方结构化输出说明](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-structured-output)规定JSON Object模式要求提示中包含JSON，且只保证JSON格式、不保证结构。因此本应用仍自行严格解析并执行schema验证；不能把json_object当作服务端完整业务校验。此实现只对本次配置有真实证据，其他兼容端点是否支持仍须单独验证。

协议版本json-tools-v1，原应用提示solomeal-agent-v2不改。metadata增加实际协议/协议版本/response_format/线上消息哈希；30秒、1500输出token、默认采样及未发送enable_thinking均保留。JSON仅用于有工具的Agent调用；直接模型无工具时仍按原文本模式运行。

响应解析失败的provider_message只保存在ModelCallError私有属性，公开API和metadata不返回它；显式RecordedModel才将其写进仓库外私有目录。没有新增业务自动日志，也不记录HTTP错误原文。这是A002失败后补的诊断入口，不回填旧失败正文。

## 实际调用

本轮聊天15请求，全部15份usage可用，观察total_tokens合计63337，费用未估算。历史聊天26次、视觉30次另存；没有真实视觉调用。原始响应保存在D:/SoloMeal-Acceptance/p8-schema-*与p8-a00*-json-0909-*；仓库仅保存[指标](p8-json-protocol-0909.json)。

| 场景/尝试 | 请求 | 秒 | 结果 |
|---|---:|---:|---|
| 去default原生探针 | 1 | 见JSON | 字符串整数，失败 |
| 展开$ref原生探针 | 1 | 见JSON | 字符串整数，失败 |
| A003 JSON 01 | 2 | 23.108 | 通过，0无效调用 |
| A003 JSON 02 | 2 | 16.189 | 通过，0无效调用 |
| A003 JSON 03 | 2 | 26.049 | 通过，0无效调用 |
| A001 JSON 01 | 2 | 8.112 | 通过，0无效调用 |
| A002 JSON 01 | 1 | 10.063 | invalid_response，失败 |
| A002 JSON 02 | 4 | 43.391 | 独立复验通过，0无效调用 |

A003三次的source_sha256相同，dataset/protocol/SYSTEM/tools也固定；不是用三种提示拼3重复。A002第一次失败时未记录原始正文，无法细分具体响应结构原因；不能推测已被修复。增加私有失败采集后新目录复验通过，但旧失败仍计入本轮诊断。全部业务快照不变。task_success和人工清晰度仍为null，未运行留出，不产出正式成功率提升。

## 验证与复现

backend目录最终：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_tool_protocol.py tests/test_model_transport.py tests/test_agent.py tests/test_agent_evaluation.py tests/test_evaluation.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-p8-json-audit-0909 -q
.venv/Scripts/python.exe -m ruff check app/core/config.py app/services/tool_protocol.py app/services/agent_model.py scripts/probe_tool_schema.py scripts/evaluate_agent.py tests/test_tool_protocol.py --select F,B,I
```

最终65 passed（17.90秒），ruff通过；两条既有第三方弃用警告。初轮47与第二轮65是中间结果，不相加。新增测试覆盖类型/null保留、字符串仍被业务拒绝、非法封装/重复键/非有限数/未知工具、历史消息不变、真实runtime查询与做饭确认：批准前不扣减、取消不变、同键批准一次只扣80g并留一个做饭事件。这些写入测试使用MockTransport+隔离SQLite，不冒称真实模型写入或MySQL并发验收。

仓库根目录复现A003，输出目录须不存在：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --scenario A003 --mode agent_tools --tool-protocol json --send-model --output D:/SoloMeal-Acceptance/p8-json-NEW
```

需要在应用启动中使用时，在该进程设置SOLOMEAL_MODEL_TOOL_PROTOCOL=json；本机.env仍未改，默认native不能称已修复。不是发生失败后自动切换协议，不隐式增加模型请求。

下一步以显式json协议继续A004～A020的确认/撤销/反馈/异常夹具与执行器，保留A002失败继续观察，补人工评价后再冻结完整配置运行留出。P4/P5/P6/MySQL/浏览器/远程CI/真实试用/P9原缺口仍在。本轮未改数据库迁移、前端、原插件，未修改开发库、根data、未提交推送。
