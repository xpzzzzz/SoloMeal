# Mem0 接入的隔离 MySQL 并发验收

2026-10-28（Asia/Shanghai）。使用本轮新建的独立 MySQL 实例，**关键行锁组 5 项通过，记忆状态与事务回归组 13 项通过**；另有 SQLite 对照 47 项通过、5 项按条件跳过。没有调用真实 Mem0 或模型，没有部署应用、提交或推送。

## 环境和隔离证据

- 检查了 `backend/tests/conftest.py` 和迁移配置：测试 fixture 只接受名为 `solomeal_test` 的 MySQL schema，并在每个测试前后执行 Alembic 降级/升级；这些操作会清除测试 schema，不能对已有应用库使用。应用 MySQL 连接显式采用 `READ COMMITTED`。
- 只读检查 Docker 列表及端口后，使用本机已有 `mysql:8.0` 镜像（镜像 ID `sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b`），没有拉取镜像或复用已有数据库。主要测试实例版本为 **MySQL 8.0.46**，专用容器 `solomeal-mem0-mysql-516bd3c9a211`、专用命名卷 `solomeal-mem0-data-516bd3c9a211`，动态端口仅绑定 `127.0.0.1:56252`；测试用户与 root 密码均为本轮随机生成的不同临时凭据，没有写入仓库或输出其值。
- 新实例的容器/卷所有权标签、容器 ID、唯一挂载和本机端口均经核对；测试连接成功后，以只读查询确认 `solomeal_test` 初始表数 **0**。服务器默认隔离级别是 `REPEATABLE-READ`，通过实际应用 `build_engine()` 创建的连接查询得到 **`READ-COMMITTED`**；本轮业务测试采用后者。测试结束后 fixture 降级，schema 内剩余一张迁移版本表。
- 进程级关闭 Mem0，清空该进程的 Mem0 和模型密钥；测试使用 Fake、MockTransport 和 Scripted 模型。测试连接通过单个 shell 进程中的临时变量提供，没有改写 `.env` 或生产连接。所有 MySQL 测试串行使用同一隔离 schema；SQLite 对照使用另一独立临时数据库。

## MySQL 实际结果

### 关键行锁组：5 通过，0 失败，0 跳过

| 测试 | 结果与覆盖 |
| --- | --- |
| `test_plans.py::test_concurrent_confirmation` | 通过：两个并发确认返回 200/409，仅产生一条做饭记录。 |
| `test_plan_lifecycle.py::test_mysql_cancel_confirm_race` | 通过：取消与确认竞争返回 200/409，最终做饭记录与方案终态一致。 |
| `test_agent_sessions.py::test_mysql_concurrent_session_continuation` | 通过：并发续接返回 201/409，会话版本和运行数量一致。 |
| `test_memory_mysql_concurrency.py::test_mysql_agent_releases_user_lock_during_memory_and_rechecks[candidate]` | 通过：Agent 的 Fake 记忆读取被事件阻塞时，独立 MySQL 连接在 `innodb_lock_wait_timeout=3` 下取得同一用户行锁并修改候选；释放 Fake 后，Agent 重新计算并按时间约束拒绝两道菜。 |
| 同一测试 `[lease]` | 通过：独立连接在 Fake 等待读取期间取得用户和 AgentRun 行锁并替换租约；Agent 恢复后发现租约不符，没有写入工具事件。 |

新跨连接测试位于 [test_memory_mysql_concurrency.py](../backend/tests/test_memory_mysql_concurrency.py)。它确认的是本次真实 MySQL 连接和受控 Fake 等待下的锁行为，不代表真实 Mem0 的网络或高并发性能。

复核时又为两个新测试增加了断言：第二连接取得用户行锁时，Fake 的读取函数**仍在等待，尚未返回或超时**。在新建的第三个独立容器 `solomeal-mem0-mysql-87922a5fde51`、独立卷 `solomeal-mem0-data-87922a5fde51`、本机动态端口 `56913` 上，核对标签、挂载并确认初始表数为 0 后，单独重跑加强版两项，**2 passed、0 failed、0 skipped，32.95 秒**。这两项已包含在上述五个不同用例中，不重复计数。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_mysql_concurrency.py --basetemp $testRoot -o addopts='' -v -ra --tb=short -p no:cacheprovider
```

关键组命令，工作目录为 `backend`，连接变量指向上述隔离实例，`$testRoot` 为本轮唯一临时目录：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_plans.py::test_concurrent_confirmation tests/test_plan_lifecycle.py::test_mysql_cancel_confirm_race tests/test_agent_sessions.py::test_mysql_concurrent_session_continuation tests/test_memory_mysql_concurrency.py --basetemp $testRoot -o addopts='' -v -ra --tb=short -p no:cacheprovider
```

实际输出 **5 passed，2 条依赖弃用警告，82.76 秒**。

### 记忆状态和事务回归：13 通过，0 失败，0 跳过

- [test_memory_operations.py](../backend/tests/test_memory_operations.py) 五项：同一及等价确认幂等、Fake 远端等待时并发确认只写一次、Fake 结果未知时禁止重复发送并抑制记忆、纠正/删除重复偏好及旧结果抑制、旧快照不可错误宣称成功。
- [test_memory_no_candidates.py](../backend/tests/test_memory_no_candidates.py)：未知状态抑制、关闭记忆或个性化的单次规划，以及四种 Mock 读取失败（超时、连接错误、429、500）的降级行为，共六项。
- [test_plans.py](../backend/tests/test_plans.py) 的库存变化和旧版本保护、[test_plan_lifecycle.py](../backend/tests/test_plan_lifecycle.py) 的取消/历史/重放与终态，共两项。

实际命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_operations.py tests/test_memory_no_candidates.py::test_unknown_suppression_remains_applied_to_viable_results tests/test_memory_no_candidates.py::test_disabled_memory_or_personalization_keeps_one_planner_pass tests/test_memory_no_candidates.py::test_failure_degrades_only_when_candidates_exist tests/test_plans.py::test_stale_stock_revision_and_old_version tests/test_plan_lifecycle.py::test_cancel_history_owner_replay_and_terminal --basetemp $testRoot -o addopts='' -v -ra --tb=short -p no:cacheprovider
```

实际输出 **13 passed，2 条依赖弃用警告，222.72 秒**。其中“结果未知”和网络异常均由本地 Fake/Mock 模拟，没有测试真实 Mem0 写入超时或真实响应丢失。

### 中断及环境错误记录

首次尝试了收集 **106 项**的较宽 MySQL 回归；考虑每个用例重建整个 schema 带来的磁盘写入，我中断该轮，pytest 报告 **10 passed、KeyboardInterrupt，未完成其余用例**。中断后同一测试 schema 出现迁移版本与表结构不一致；随后的关键组 **5 项在 fixture 初始化报错**，均为降级时尝试删除不存在的 `receipt_parse_tasks.mode`，未进入并发断言。现象与 MySQL 非事务 DDL 迁移被中断后部分提交一致，但没有保存足以确定中断发生在具体哪条 DDL 的证据。

这是本轮隔离测试环境的状态问题，不能算业务测试通过，也未据此改写或降低测试。随后核对本轮容器和卷标签后，仅移除该测试容器 `solomeal-mem0-mysql-cb0021bd4377` 和卷 `solomeal-mem0-data-cb0021bd4377`，重新创建上述空实例；关键组及状态组在新实例完整通过。没有对任何既有数据库执行 `DROP DATABASE` 或清空操作。首次等待 MySQL 的一个本地 Python 检查命令因 shell 引号产生语法错误，改正后确认新库初始为空；它没有执行数据库更改。

## SQLite 与静态检查

SQLite 对照命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_memory_mysql_concurrency.py tests/test_memory_operations.py tests/test_memory_no_candidates.py tests/test_plans.py tests/test_plan_lifecycle.py tests/test_agent_sessions.py --basetemp $testRoot -o addopts='' -q -ra --tb=short -p no:cacheprovider
```

结果 **47 passed、5 skipped、0 failed，98.67 秒**。跳过两项新增 MySQL 行锁测试，以及方案并发确认、取消/确认竞争、Agent 会话并发续接；这些 SQLite 跳过没有计入 MySQL 通过数。SQLite 运行在上述额外等待断言加入之前，但两项相关测试在 SQLite 下本来即跳过。最终在仓库根目录执行 `backend\.venv\Scripts\ruff.exe check backend/app backend/tests --select F,E9`，**通过**。未改应用代码或前端，未运行前端测试或全量后端套件。

## 清理和剩余风险

三次测试专用容器及其各自命名卷均已删除。每次删除前核对了本轮随机标签、容器 ID 和唯一卷挂载；最终按标签复查无残留。原有 SoloMeal 的 web/API/db 与其他项目运行容器在清理后仍处于运行状态，没有停止、重启或修改它们。临时测试凭据已从测试 shell 环境移除；没有删除、清空或重置既有数据库。本轮 pytest 的独立临时目录仍留在系统临时目录中，包含测试产物；未清理其他工作区或既有临时目录。

这轮没有发现需要修改应用代码的并发缺陷；上述通过结论限于单次、两请求/两连接的受控场景，不能外推为压力测试结果。没有运行最初收集的全部 106 项 MySQL 测试，也没有测试真实 Mem0 故障、真实响应丢失、搜索索引延迟或跨进程长期故障。真实未知写入仍缺少完整安全核销入口，旧索引与在途请求的风险仍在；不能因本轮 Fake 测试宣称这些问题已解决。P8 冻结协议、±6 评分和跨请求缓存策略均未改。
