# P0 上游审查与复用矩阵

日期：2026-09-05。上游：https://github.com/sergiparpal/meal-manager 。
本地基线 a923d77c7c281f2fcd165a71ad062f1ec0d851bc；origin 仍指向上游，未提交或推送。
保留 GPL-3.0 与原归属。改造初期原 src 不更改业务实现。

## 基线与验证

Windows，Python 3.13.13，Node 24.16.0，npm 11.13.0。
Docker CLI 可用但 daemon 不可连接；MySQL80 Windows 服务运行，但本项目未配置连接。
开始时已有 AGENTS.md/CLAUDE.md 修改及 PLAN/STATUS 未跟踪文档（上一轮产物）。
测试前后根目录 data/ 均不存在，测试使用临时目录，禁用 pyc 写入。

| 检查 | 首次 | 修正后 |
|---|---|---|
| test_unit.py | 361 通过，3 失败，退出 1 | 365 通过，0 失败，退出 0 |
| test_integration.py | 298 通过，0 失败，退出 0 | 298 通过，0 失败，退出 0 |

计数为脚本 check 断言数，不是 pytest 测试函数数。后端 pytest 另有 7 个测试通过。
日志在 docs/validation/，保留初次失败记录；Windows 上 fcntl 专属测试明确跳过。
Linux/Python3.12/3.14、mypy 与 coverage 本轮未执行，不宣称跨平台全绿。

## 源码核对结论

| 模块 | 实际能力 | SoloMeal 处理 |
|---|---|---|
| __init__.py / handlers/__init__.py | 自动发现 26 个工具并注册 Hermes | 新应用独立工具运行时；schema 思路可用 |
| src/dish.py | 名称归一、必需/可选布尔、按名称判断可做 | 保留语义，重建数量/单位/份数模型 |
| src/suggestion.py | 可选食材数量与最近用餐加权、2 天冷却 | P4 参考；加入真实硬约束，不直接当定量规划 |
| src/shopping.py | 按最少缺失种类数排序 | 不是货币价格最便宜；价格/包装费用新增 |
| src/handlers/_common.py | 未知参数拒绝、名称别名、错误脱敏 | 参考边界设计，Web 使用 Pydantic/错误码 |
| src/repositories/base.py / __init__.py | Protocol + 可重定向全局 JSON 单例 | 不作多用户后端，改为请求作用域 DB session |
| src/filelock.py / src/__init__.py | 进程/文件锁、原子替换、best effort fsync | 原插件保留，新应用使用数据库事务 |
| register_cooked_meal.py | 写历史、扣每项一菜份、异常补偿、权重更新 | 重建事务、幂等和批次消耗；原版不保证精确可用量 |
| delete_history_entry.py | 撤销最近历史影响，未恢复食材 | 新 undo 必须按消费明细恢复 |
| src/dii/session.py / finalizer.py | 交互状态、提交与补偿 | 参考确认流程，不直接移植共享 session store |
| .github/workflows/tests.yml | 原测试矩阵、mypy、coverage、聚合 gate | P1-04 加后端 job，隔离扫描范围，保留原门槛 |

未逐行审阅每个 handler；已覆盖复用和迁移关键路径，其余通过 26 工具集成套件验证。

## Windows 失败修正

仅修改 test_unit.py：
1. 权限保留检查比较操作前后实际权限，POSIX 新文件仍严格要求 0644。
2. Windows 新文件检查内容可读和再次替换可写，不冒充 POSIX 权限验证。
3. fcntl 存在要求锁文件，不存在验证不创建文件锁；可重入深度检查保留。

新一轮 CI 会增加断言计数，但没有降低业务门槛。原业务源文件未修改。
