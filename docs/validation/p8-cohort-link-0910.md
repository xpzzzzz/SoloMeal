# P8 cohort 执行前校验与评审绑定（2026-09-10）

本段完成 NEXT_SESSION 指定的下一步联动，不启动正式评测。cohort 版本为 solomeal-cohort-v2；旧 v1 文件保留，不将旧登记静默升级或用于新执行。应在源码稳定后重新登记配置及保存 manifest 哈希。

## 实现

- evaluate_agent.py 新增 --cohort 和 --cohort-sha256，必须成对传入。创建输出目录、隔离数据库和模型请求之前核对场景/模式/位置、源码/commit/提示/schema、协议/预算/时限、数据/勘误和模型采样配置；已存在位置拒绝重启。未传 cohort 的既有单次诊断仍保留，不能作为 v2 cohort 证据。
- attempt 保存 cohort 哈希及重复序号；v2 audit 强制检查该绑定。固定模式读取同批模型配置用于一致性审计，但执行仍不调用模型；直接模型继续使用原生文本协议。
- cohort_agent.py review 复用 review_agent.py 的原始 manifest、证据哈希和评分校验，重新计算评分，不信任可编辑 scores 文件。拒绝跨批次和错误配置证据；完整保留180位置及未启动/失败/未评分状态。评审可分批，尚未评阅的位置不会消失。
- success_rate 仍 null，P8 gate=incomplete；不是三模式门槛聚合，也不是独立人工清晰度验收。

## 使用

沿用 cohort v2 register 的显式配置结构，保存登记时输出的哈希。执行示例中的目录必须与 manifest 对应位置完全一致：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --cohort D:/SoloMeal-Acceptance/COHORT.json --cohort-sha256 SAVED_SHA256 --output D:/SoloMeal-Acceptance/ROOT/A001-agent_tools-01 --scenario A001 --mode agent_tools --send-model --tool-protocol json --max-completion-tokens 3000
backend/.venv/Scripts/python.exe backend/scripts/cohort_agent.py review --manifest D:/SoloMeal-Acceptance/COHORT.json --manifest-sha256 SAVED_SHA256 --review D:/SoloMeal-Acceptance/REVIEW.json --output D:/SoloMeal-Acceptance/BOUND-NEW.json
```

上例仅说明接口，本段没有登记正式配置或执行模型。review 文件先通过原 review_agent.py init 生成，再按实际证据填写。

## 验证与范围

92 passed / 2 既有弃用警告（60.04秒），覆盖cohort、评审、48执行器与冻结测试。最终缺失绑定测试隔离及固定模式读取共同配置修正后，23项cohort复验通过（1.96秒）；不累加成115。ruff通过。未执行完整backend/MySQL/浏览器/远程CI/真人验收。

本段聊天0、视觉0；累计123已知聊天、另1关机无返回尝试及30视觉不变。A014失败仍保留，不重跑或上调预算。无业务服务、开发库、根data、.env、前端、迁移或原插件修改，无提交推送。

下一步实现三模式门槛聚合，明确每项指标证据来源、分母、缺失/不适用规则和调试/留出范围；不能从当前调试cohort直接宣布留出门槛通过。A014回答闭环完成后再冻结统一配置、完整调试重复与留出。P8/P5仍IN_PROGRESS，PLAN正式验收范围不变。
