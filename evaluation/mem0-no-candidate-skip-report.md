# 无可行候选时跳过 Mem0 搜索

2026-10-28。本轮只在本地使用 SQLite、MockTransport 和 Scripted/Fake 模型验证；没有调用真实 Mem0、真实模型或重新运行真实 A/B。没有更改 P8 冻结协议或历史实验结果，也没有部署、提交或推送。

## 实现和调用链

- [planning.py](../backend/app/services/planning.py)：给现有 `recommend()` 增加内部可行性探测模式，复用完全相同的报价校验、个人用时、忌口、厨具、时间和已知预算规则。探测遇到第一个可行候选即停止，不进行历史权重和候选评分；若全部不合条件，则补齐原有响应所需的历史统计并返回完整空候选结果。新增 `recommend_with_memory()`：空候选直接返回；有候选则通过原有 `read_memories()` 读取并应用 `operations` 抑制，然后刷新 session 对象并用原规划器重新生成最终结果。Provider 或个人化关闭时沿用单次原规划流程，不增加探测扫描。
- [规划 API](../backend/app/api/planning.py) 和 [首页服务](../backend/app/services/home.py)：使用 `recommend_with_memory()`。认证、输入模型和首页区块处理不变；无候选时不调用 Provider，有候选时无论记忆是否相关仍调用原读取路径。
- [Agent 服务](../backend/app/services/agent.py)：模型工具参数和租约仍按现有流程检查。在用户/运行锁内以同一规划器探测；无候选时正常记录该工具结果，不请求记忆。有候选时先回滚只读探测事务、释放锁，再读取记忆；重新获取锁并验证原租约后重新执行完整推荐。如果租约已失效，沿用原有退出逻辑。远端调用不发生在锁内，方案预览的原行为未改变。工具执行计时继续排除远端读取时间。
- [新增测试](../backend/tests/test_memory_no_candidates.py)覆盖前后调用顺序、硬约束、HTTP 次数、空/相关/无关/冲突/重复记忆、错误、未知状态、首页、Agent 和读取期间变化；[诊断测试](../backend/tests/test_memory_diagnostics.py)给故障降级与日志失败案例补充可行候选，使其仍实际执行读取，未降低断言。

本轮未改 [memory.py](../backend/app/services/memory.py)、[personalization.py](../backend/app/services/personalization.py) 或记忆状态机。没有引入跨请求缓存，±6、搜索参数和归属验证不变。无候选时不读取、也不使用记忆；后续存在候选的请求仍查询并执行未知、待处理、已退役状态抑制。

## 效果与边界

没有菜谱、或所有菜谱因忌口、时间、厨具、已知预算超限而被拒绝时，可跳过远端搜索。预算未知仍是现有规则下的候选，即使 `budget_feasible` 为 false 也不能因此跳过；有候选但记忆为空、无关或冲突时，仍正常调用 Provider。

四个独立固定测试分别用旧调用顺序（先 `read_memories()` 后规划）和新 API 对同一数据对照：每个旧顺序发生 **1 次 MockTransport HTTP**，新 API **0 次**，合计在这四对比较中减少 **4 次 Mock HTTP 调用**。两组完整响应逐项相等，包含候选、分数、排序、理由、约束与拒绝原因。首页和 Agent 的空候选专项各观察到 0 次 Mock HTTP，有候选时各观察到 1 次；有候选结果分别与旧顺序的固定夹具对照。测试没有发送真实网络请求，不能将此数量当作线上调用或成本统计。

固定可行场景中，空记忆、无关记忆、可匹配记忆、相同偏好重复及正负冲突时，新旧完整结果相等；未知操作状态仍抑制对应记忆。非法输入及他人报价仍分别返回原有 422/404，未授权请求仍为 401；已有测试继续检查失效记忆、关闭、超时、限流和异常降级。已知预算、忌口、时间、厨具均有零候选对照，预算未知另有正例。

探测结果是一次时点判断，不是锁定库存或菜谱的承诺：探测有候选后，等待远端期间若条件改变，最终结果可能无候选，已经发出的读取不会被撤销。测试模拟了读取期间菜谱变为超时，普通 API 和 Agent 均重新过滤；Agent 也测试了读取期间租约失效。无候选直接返回时，结果反映当次探测时的数据；并发更新发生在该时点之后不能反映在该次响应。真实 MySQL 隔离和行锁行为尚未验证。

启用记忆且有候选时会多执行一遍本地可行性扫描，但探测阶段不会重复计算历史权重或评分；已有性能回归及新的 API/Agent 用例检查一次历史权重计算。Provider 或个人化关闭时普通推荐和首页使用单次规划。额外数据库读取和响应时间尚未在真实环境测量。Provider 和个性化均启用且无候选时没有 `read_memories` span；当前诊断中间件只在发生记忆读取或未知操作时输出，因此不能靠缺少日志单独证明发生了多少次跳过。

## 自动化验证

所有测试命令在 `backend` 下运行，进程级关闭 Mem0、清空该进程的 Mem0/模型密钥、使用唯一临时 SQLite，并禁用 pytest 缓存。启用的 Provider 都使用 MockTransport，Agent 使用 Scripted/Fake。以下各测试组有重叠，不应相加。

测试进程使用以下隔离设置，`$testRoot` 是每次新生成的临时目录；两个现有依赖发出弃用警告，不影响本次测试断言。

```powershell
$env:SOLOMEAL_MEM0_ENABLED='false'
$env:SOLOMEAL_MEM0_API_KEY=''
$env:SOLOMEAL_MODEL_API_KEY=''
Remove-Item Env:SOLOMEAL_TEST_DATABASE_URL -ErrorAction SilentlyContinue
$testRoot=Join-Path $env:TEMP ('solomeal-offline-' + [guid]::NewGuid().ToString('N'))
```

| 实际运行 | 结果 | 范围与时间点 |
| --- | --- | --- |
| 早期沙箱内相关回归 | **19 通过、40 初始化错误** | 沙箱临时目录无法创建 pytest 编号目录，40 项未进入测试主体；这次运行失败，不计为通过。 |
| 中途综合后端回归 | **212 通过、3 跳过** | 覆盖记忆、推荐、首页、方案和 Agent；在改成不重复计算历史权重的可行性探测之前执行，仅作中途回归证据。 |
| 分组记忆相关回归 | **93 通过、0 跳过** | 可行性探测版，涵盖 Provider、操作、确认 API、推荐与诊断；在最终关闭快路径和 Agent 计时细节调整之前启动。 |
| 分组推荐与 Agent 回归 | **123 通过、3 跳过** | 可行性探测版，涵盖个性化、用时、规划性能、方案、首页与 Agent；在同样的最后局部调整之前启动。 |
| 最终相关回归 | **83 通过、1 跳过、0 失败** | 最终关闭快路径及 Agent 计时代码；涵盖新增案例、记忆推荐、诊断、首页、Agent 会话和恢复、规划性能。 |

最终相关回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_no_candidates.py tests/test_memory_recommendations.py tests/test_memory_diagnostics.py tests/test_home.py tests/test_agent_sessions.py tests/test_agent_recovery.py tests/test_planning_performance.py --basetemp $testRoot -o addopts='' -q -ra --tb=short -p no:cacheprovider
```

前两组覆盖的 Provider 和方案等测试命令分别为：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_no_candidates.py tests/test_memory_provider.py tests/test_memory_operations.py tests/test_memory_agent_api.py tests/test_memory_recommendations.py tests/test_memory_diagnostics.py --basetemp $testRoot -o addopts='' -q -ra --tb=short -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/test_personalization.py tests/test_personal_time.py tests/test_recommendation_scenarios.py tests/test_recommendation_diagnostic.py tests/test_recommendation_response.py tests/test_planning.py tests/test_planning_performance.py tests/test_plans.py tests/test_plan_lifecycle.py tests/test_home.py tests/test_agent.py tests/test_agent_actions.py tests/test_agent_sessions.py tests/test_agent_recovery.py tests/test_agent_review.py --basetemp $testRoot -o addopts='' -q -ra --tb=short -p no:cacheprovider
```

分组综合回归的三个跳过项分别是 `test_plans.py::test_concurrent_confirmation`、`test_plan_lifecycle.py::test_mysql_cancel_confirm_race`、`test_agent_sessions.py::test_mysql_concurrent_session_continuation`，均需要真实 MySQL 行锁；最终相关回归只包含其中最后一项。**SQLite 下均不计为通过**。本轮未验证真实 MySQL。新增测试曾因片段放错函数被 Ruff 报出两个 `F821`，已修正；一轮未完成测试主动中断并在修正后重新运行，不记为通过。最终在仓库根目录运行 `backend\.venv\Scripts\ruff.exe check backend/app backend/tests --select F,E9`，**通过**。前端未修改，未运行前端测试。

## 剩余风险

本轮未测真实 Mem0 延迟、真实节省的服务成本或生产数据；此前真实连接复用实验只观察了有搜索的情况，不能代表本次优化后的端到端性能。额外可行性探测产生本地查询开销，候选较多时的性能边界待测。远端结果旧索引、未知写入人工核销及在途旧快照风险保持既有边界；MySQL 行锁专用测试如未在隔离 MySQL 执行应继续标记跳过。没有修改任何真实用户数据或系统开关。
