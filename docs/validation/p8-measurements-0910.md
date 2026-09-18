# P8 参数与写入专门测量（2026-09-10）

新增evaluation_measurements.py，只由诊断执行器启用，不改变应用业务服务。聚合版本cohort-metrics-v2，登记版本cohort-v3；旧v1/v2登记与历史结果保留，不能静默升级或补填旧measurements。

## 实现与口径

- 参数合法率：以持久化工具边界事件为分母，INVALID_TOOL_ARGUMENTS/UNKNOWN_TOOL为不合法，其余业务失败与合成TOOL_TIMEOUT不当参数错误。包含多轮事件；传输信封被拒绝而未到工具边界的不进入该分母，任务失败仍单列。零工具事件不是100%合法；没有measurement的旧报告仍缺失。直接模型无工具，参数指标不适用。
- 写入正确性：只接受A010/A011/A012实际approve扩展的数量、历史、事件及同键重放oracle。只预览/取消/旧方案拒绝不冒充成功写入；每可执行模式9个批准位置未执行就缺失。此范围不替代采购/小票/MySQL事务完整验收。
- 未授权写入：SQLAlchemy监听成功执行的业务DML，在commit边界计语句数；回滚清除待提交数。夹具初始化、明确驱动approve和A016外部库存PATCH不计未授权；Agent会话/工具事件/auth session/operations幂等簿记排除，其他表默认计入。计数不保存SQL参数或数据。即使写入后恢复原值，提交的两条DML仍被识别，不能靠最终快照相同掩盖。
- 观测局限：commit事件发生在DBAPI实际提交前，若提交自身失败可能保守多计，不能当已证实提交次数。无法分类的原始SQL/未结束事务使complete=false；这是顺序隔离SQLite诊断，不替代真实MySQL事务/并发证据。指标单位明确为business_DML_statements_at_commit_boundary，不冒称业务操作数。
- 聚合按完整分母计算参数比例；缺失时正式value=null。写入/未授权任一已观察失败可标failed，缺失不变passed。直接模型写入不适用。P8 gate仍incomplete，留出未运行。

## 登记与执行

cohort-v3显式config.attempt.confirmation_extension可设none或approve。approve策略只对A010/A011/A012的agent_tools/fixed_workflow位置生效，直接模型和其他场景仍none。执行这些位置时传--confirmation approve，运行前校验不匹配即拒绝。其他位置使用默认none；A019取消/A016故障驱动不变。旧v2入口不接受新语义，须保留旧文件并另登记v3，源码/提示配置稳定后再启动统一评测。

示例命令（本段没有真实执行）：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/evaluate_agent.py --cohort D:/SoloMeal-Acceptance/COHORT-V3.json --cohort-sha256 SAVED_SHA256 --scenario A010 --mode fixed_workflow --confirmation approve --output D:/SoloMeal-Acceptance/ROOT/A010-fixed_workflow-01 --tool-protocol json --max-completion-tokens 3000
```

## 验证

114项受影响专项通过（67.49秒），覆盖执行器48、测量8、聚合14、cohort23、评审15、冻结6；之后追加5个回归并修正空写入分母，最终测量/聚合27项通过（4.82秒），不把重复测试相加。ruff通过，2既有弃用警告。

首轮61通过/1旧断言失败：直接模型写入改为明确not_applicable，旧测试期待incomplete，更新测试后上述通过。独立数据库测试覆盖初始化不计、授权排除、回滚、提交、监听移除、原始SQL未知、写后恢复仍计数；API隔离测试验证三种批准数量/重放。没有付费模型调用，HTTP替身不算模型效果。

本段聊天0/视觉0；累计123已知聊天、另1关机无返回尝试、30视觉不变。无开发库/根data/.env/业务服务/前端/迁移/原插件修改，无提交推送。未跑完整backend/MySQL/浏览器/远程CI/真人验收。

下一步做v3固定流程的独立CLI登记→执行→评审→聚合闭环，核验配置与测量产物；仍是调试工程证据。A014回答闭环尚未修复，先离线定义单变量方案，不盲目重跑或继续上调预算/时限；补齐后才冻结统一真实配置与完整三模式重复/留出。P8/P5仍IN_PROGRESS，PLAN正式范围不变。
