# P8预算调试与关机中断（2026-09-10）

执行器现支持A001～A007、A010～A012共10场景。本段只扩展评测脚本/测试，未改应用业务、迁移、前端或原插件。真实请求使用qwen3.8-flash、solomeal-agent-v2、json-tools-v2、30秒/1500token，未发送enable_thinking；应用默认native及.env保持不变。完整指标见[p8-budget-debug-0910.json](p8-budget-debug-0910.json)。

## 夹具与判定

- A006沿用quoted契约：无库存批次即可用量0，大米100g/包3元、鸡蛋1个/包2元，运行日报价。预算5元时，白米饭/慢煮饭各采购一包米3元；蛋炒饭加一个鸡蛋总计5元。判定检查整包装购买量、费用、缺料和预算边界。该场景没有超预算候选，不能当作真实超预算拒绝证据。
- A007原standard库存足量，不会出现缺报价导致的未知采购费用。首次执行前新增amendments-v1.2.json及freeze-v1.2.json，改用已定义low_stock（大米50g、鸡蛋0个、无报价），结果标A007-v1.2。原清单/freeze-v1/v1.1均保留；未把新结果计作旧标签成绩。
- 快照新增报价，直接模型输入使用实际报价；三个模式同夹具。预算检查覆盖实际参数、候选集合、份数、缺料数量、包装数量/费用、完整报价标志和预算状态。语义与人工清晰度继续为null，不以工具正确直接推定最终任务成功。

## 真实结果与中断

| 试次 | 结果 | 已知请求 | 无返回尝试 | 无效工具调用 | 总耗时 | 已观察token |
|---|---|---:|---:|---:|---:|---:|
| A006-01 | 客观检查通过、业务不变 | 4 | 0 | 0 | 30.676s | 17970 |
| A007-01 | 关机中断、无report，最终状态未知 | 2 | 1 | 未完成 | 未知 | 7762 |
| A007-02 | 客观检查通过、业务不变 | 2 | 0 | 0 | 22.215s | 9041 |

原始目录分别为D:/SoloMeal-Acceptance/p8-budget-A006-json-v2-0910-01、p8-budget-A007-json-v2-0910-01、p8-budget-A007-json-v2-0910-02。三者source_sha256相同：87f5706ad1f907d127bcf7e16fd0aaf70e7559383d8b6f3ff75990aeed53623b。

用户报告意外关机后，核对A006完整报告，A007首轮仅两个result和第三个attempt，旧进程已不存在。保留首轮所有文件，在新目录新账号重跑A007；没有覆盖原证据或补造第三次响应。总计8个确认发送并有usage的请求，另1个已预留尝试是否发送/计费未知；已观察34773 total_tokens，无费用估算。中断不是通过，也不能从分母抹除。历史聊天62次/视觉30次另计，本轮视觉0次。

A006最终文字正确列出3/5元费用及先入库，但没有明确提醒报价属于估算，留待语义评阅；A007-02明确表示缺价格/包装信息，不能确认8元预算。以上是开发检查笔记，不是独立人评或正式成功率。

## 工程验证

命令在backend执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_agent_evaluation.py tests/test_tool_protocol.py tests/test_evaluation.py tests/test_model_transport.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-budget-final-0910 -q
.venv/Scripts/python.exe -m ruff check scripts/evaluate_agent.py tests/test_agent_evaluation.py
```

最终74 passed，23.32s；ruff通过，两个既有第三方弃用警告保留。初轮26通过/2失败：新增MockTransport测试错误地按原生role=tool判断JSON历史，修正为tool_result封装后通过；不是生产协议更改。未重跑全后端/MySQL/浏览器/远程CI。关机恢复后确认文件与证据存在，并再次ruff通过；74为关机前完成的实际结果，未虚称恢复后重跑。

剩余10个调试场景A008/A009、A013～A020，优先A015多轮反馈/A016旧快照；之后才统一冻结配置并运行完整调试/留出/三模式重复。P8/P5保持IN_PROGRESS。未提交推送，未改开发库、根data或.env。
