# P8 回答事实忠实性调试（2026-09-10）

本段只修改 `backend/app/services/agent.py` 的提示与版本号；最终为 solomeal-agent-v8，协议仍 json-tools-v2。未修改规划规则、工具 schema、模型参数或评分门槛。P8/P5仍未完成，A014最终回答验收仍缺证据。

## 修改与执行约定

- v6：操作叙述须对应实际工具记录；日期/时间须有对应来源；不追问非必填有效期；不支持付款时解释能力边界。
- v7：针对v6实际回答错误，说明本轮请求参数并非保存偏好，推荐工具会合并保存忌口与额外排除项，推荐应依据有效条件和候选。代码核对点为planning.recommend中的两个排除列表合并。
- v8：针对v7实际多问确认，区分只读查询与写入确认；已要求查询就直接执行，可重试的只读临时错误允许重试一次，持续失败如实说明。

先各复验A014/A018/A020一次；v6 A014首次明确timeout后，同版本同参数另目录恢复一次。v7/v8各三个新试次是针对已观察问题修改提示后的回归，不是同配置重复，更不是择优正式分数。共10个调试试次，失败全部保留。本段停止重复A014调用：v8已有正确工具结果但最终模型请求仍超时，不能以工具结果代替缺失回答。

模型qwen3.8-flash、1500 completion上限、30秒、temperature/top_p提供方默认未知、thinking不发送、JSON协议保持。未提高生产限额或修改.env。所有真实响应在独立私有目录；[JSON摘要](p8-faithfulness-0910.json)逐试次记录源码/SYSTEM/report哈希，可回溯原始attempt及call文件。

## 全部真实结果

| 版本/场景 | 请求 | 已观察token | 客观检查 | 回答核对 |
|---|---:|---:|---|---|
| v6 A014-01 | 1 | 未返回 | 失败 | 首请求timeout，无工具、无回答 |
| v6 A014-02 | 1 | 4017 | 失败 | 未调用推荐，把空请求排除项当保存状态，要求重填忌口 |
| v6 A018 | 1 | 3865 | 通过 | 明确不支持付款，只提食材/数量/单位，没有追问有效期 |
| v6 A020 | 3 | 12245 | 通过 | 一次注入错误后实际重读；数量/有效期未知均有依据，无虚构时间 |
| v7 A014 | 1 | 未返回 | 失败 | 首请求timeout，无工具、无回答 |
| v7 A018 | 1 | 3945 | 通过 | 不支持付款，购后可提供数量/单位做入库预览，无有效期要求 |
| v7 A020 | 1 | 3963 | 失败 | 多问一次是否继续读取，未调用工具、未触发错误注入 |
| v8 A014 | 2 | 4735（部分） | 失败 | 一次成功recommend保留鸡蛋忌口、排除蛋炒饭；第二请求timeout，最终回答缺失 |
| v8 A018 | 1 | 4044 | 通过 | 付款边界明确，没有追问有效期 |
| v8 A020 | 3 | 12675 | 通过 | 错误后重读，库存数量及批次状态有依据，没有无依据时间；仍直接显示fridge/piece，清晰度待真人评分 |

所有试次业务快照不变。A020 v6/v8各注入一次TOOL_TIMEOUT，各记1无效调用；v7没有进入工具，不把缺少注入算成故障恢复通过。注入是工具返回值替身，不是网络超时；A014三个timeout则是模型HTTP请求的实际超时诊断，提供方是否收到/计费未知。

本段共15次已进入HTTP的请求、12份非空usage、49489已观察total_tokens，另3次timeout的usage全null，不能当0成本。JSON中的observed_total_tokens仅累加已观察值，usage_records=0表示没有观察值。视觉0，费用null。原STATUS39之前104已知聊天请求及历史预算关机1个无返回尝试另计；本段不含新视觉调用。首次自动审批拒绝发生在进程启动前，不计模型请求；核对NEXT_SESSION/STATUS38授权及合成seed/临时SQLite隔离后复核通过，没有绕过审批。

本页为Codex逐项对照回答与工具事件的诊断记录，不是独立人工清晰度评分；所有原始report的task_success/human_clarity仍null，未事后改分。A018/A020的跨版本通过不能证明v8稳定，也不能补齐A014。

## 验证与后续

最终v8：93 passed、1 MySQL专属skipped、2个既有弃用警告，44.92秒；ruff通过。v6同组通过、v7同组93/1（46.16秒）为中间回归，不与最终数字相加。

命令（backend目录）：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_agent_evaluation.py tests/test_model_transport.py tests/test_agent_sessions.py tests/test_agent_actions.py tests/test_agent.py tests/test_evaluation.py --basetemp=.tmp-pytest-faithful-v8-0910-01 -p no:cacheprovider
.venv/Scripts/python.exe -m ruff check app/services/agent.py
```

覆盖48执行器测试、协议、会话、动作、Agent及冻结回归。提示修改未新增只检查提示字串的测试；实际效果以真实失败与回答记录为准。未跑完整backend/规划采购/MySQL/浏览器/真人/远程CI；无开发库、根data、.env、前端、迁移、原插件修改，无提交推送。

下一步先建立三模式结构化/语义评审入口，绑定原report哈希，明确自动安全检查不等于任务成功、固定流程是已知意图参照、直接模型写入/故障执行不适用。保留A014未验收项，针对现有三个timeout证据制定有界的传输/响应诊断，避免持续同配置盲测；参数修改须另版本留证，不能直接套视觉thinking配置。具备回答证据与评分入口后才冻结统一配置并跑完整20调试三模式重复，再进入20留出。MySQL及原P4/P5/P6/P8/P9验收范围不变。
