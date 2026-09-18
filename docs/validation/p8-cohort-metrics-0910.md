# P8 三模式指标聚合（2026-09-10）

cohort_agent.py新增summarize命令，cohort_metrics.py从manifest重新审计并可选绑定review，不接受编辑后的scores作为成绩。当前仅debug；180位置、每模式60位置保留，P8 gate=incomplete、holdout_gate=not_run。

## 指标规则

- 任务结果保留通过/失败/缺失。直接模型6个执行不适用场景共18位置单列，42适用位置；其决策指标仍保留全部60位置。不适用与传输失败不同，不删除失败。未评分时rate=null，confirmed_success_fraction仅已证实成功数/预登记适用位置数，不称正式成功率。不合并不同配置或选最佳重复。
- 客观/传输失败无须语义评审便计失败；无报告的有效已启动试次计失败。配置异常保持invalid_evidence，不能计通过。
- 硬约束来自实际review constraints项，明确语义来源；固定结构化objective不能代替约束测量。任何已评失败为failed，缺失为incomplete。
- 延迟同时报告均值和最近秩P95（排序后ceil(0.95*n)位置），120秒门槛只用于完整P95。部分观测另报observed_value，value=null，不判整批通过。无效调用均值使用现有report计数；缺失不能当0，工具错误次数不能当参数不合法次数。
- 清晰度仅使用原评审校验允许的人类1～5分，按最小分与4分比较；固定流程不适用，Codex语义不能代替人工。该保守展示约定不改变冻结协议。
- 参数合法率、写入正确率、未授权写入次数缺少专门测量，明确incomplete；不从快照不变推断全链路写入正确。下一步补测量字段与证据后接门槛。
- usage报告已观察请求/总token、未知usage和缺失report；只有所有report完整且usage无缺失才计算总量。没有费率/账单则cost=null。异常证据不用于数值汇总，原审计状态仍保留。

## 使用

```powershell
backend/.venv/Scripts/python.exe backend/scripts/cohort_agent.py summarize --manifest D:/SoloMeal-Acceptance/COHORT.json --manifest-sha256 SAVED_SHA256 --review D:/SoloMeal-Acceptance/REVIEW.json --output D:/SoloMeal-Acceptance/SUMMARY-NEW.json
```

review可省略；未启动仍180位置。输出必须不存在。源码变化后须按此前约定重新登记新配置，不修改旧manifest。

## 验证

最终58 passed、2既有弃用警告（3.85秒），ruff通过。覆盖聚合14、cohort23、评审15、冻结6；未跑执行器48或完整后端。新增真实聊天/视觉0，未登记正式配置或执行评测。

初轮56通过；新增CLI测试后57通过/1失败，原因为子进程不继承测试monkeypatch且试次根在仓库内。改为系统临时目录下唯一、未创建的路径后58通过，未放宽生产私有目录限制。一次代码编辑审批审查超时未执行，重试成功，无残余审批阻塞。

A014仍失败，P8/P5仍IN_PROGRESS。下一步补参数合法/确认写入/未授权写入专门测量，再完成门槛接线；回答闭环修复、统一配置调试重复与留出及PLAN其余验收均保留。无模型/开发库/根data/.env/业务服务/前端/迁移/原插件修改，无提交推送。
