# Mem0 未知写入状态安全核销

## 范围和结论

本轮实现了关联证据、受控运维检查、保守的状态转换与审计；没有对真实 Mem0、模型或真实用户执行操作。**当前真实 Mem0 Provider 不提供可证明完整一致性的快照，因此自动核销成功和确认未写入仅在具有更强证据契约的 Fake Provider 中验证，不能宣称真实未知写入已可自动恢复。** 搜索或列表为空、只发现一条记录，均不能据此解除抑制。

## 官方契约与证据边界

- [Add Memories](https://docs.mem0.ai/api-reference/memory/add-memories)：`POST /v3/memories/add/` 接收自定义 `metadata` 和 `user_id`，`infer=false` 原样保存。文档一般描述异步事件，同时响应字段说明 `infer=false` 为同步处理且可带 `results`；历史隔离冒烟实际观察过 `SUCCEEDED` 和 `ADD`。两种描述需按具体响应处理；非明确完成或异常结构一律未知。
- [Get Memories](https://docs.mem0.ai/api-reference/memory/get-memories)：`POST /v3/memories/` 在 `filters` 中指定用户，提供 `count`、`next`、`results`，记录可含 metadata。文档未承诺遍历期间的一致快照或写后可见时限；过期记录默认隐藏，因此分页数量一致也不能证明不存在或全局唯一。
- [Get Memory](https://docs.mem0.ai/api-reference/memory/get-memory)：`GET /v1/memories/{id}/` 返回 ID、用户、正文及 metadata 等字段。可以核对单条归属和内容，但不能证明没有其他记录。
- [Update](https://docs.mem0.ai/api-reference/memory/update-memory) 与 [Delete](https://docs.mem0.ai/api-reference/memory/delete-memory) 使用 `/v1/memories/{id}/`；核销过程不调用这两种写操作。原管理流程、状态保护仍在。
- 本轮只依据公开文档和 MockTransport 检查 metadata 请求和响应，没有实测 Mem0 是否保留新增 UUID；过去的真实实验也不能替代本次新增字段的验证。返回的 event UUID 或未验证的记忆 ID 若可获得，会在本地回执区分保存，未作为成功证据；本轮不轮询事件。

## 状态与实现

沿用 `operations` 表，不新增表或迁移。确认前的短事务校验用户与 Agent 建议，保存一个随机 UUID、确认来源和语义槽关联，提交后才发一次远端 add。UUID 仅进 metadata，不进入偏好文本。正常结果要求单个 `ADD`、合法 ID，且再次读取该 ID 并验证用户、结构化内容和 UUID，才记 `saved`/`active` 和确认 ID。读取失败、异步或模糊结果保留 `unknown`；明显在调用前未发送（禁用或输入无效）记录 `not_sent`/`retired`。进程中断可能留下 `pending`，不自动核销。

| 原状态与证据 | 结果 | 推荐行为 |
|---|---|---|
| unknown，唯一匹配、归属和 UUID 一致、内容一致，且可信证据证明结果完整无冲突 | 回执 `saved`，槽 `active`，记录 ID | 允许使用已验证偏好 |
| unknown，权威证据证明没有发送，且没有候选 | 回执 `not_sent`，槽 `retired` | 继续屏蔽；原确认不可重用，不自动重发 |
| 空列表、非权威列表、超时、列表不完整 | 保持 unknown，记原因 | 继续屏蔽 |
| 多条候选、归属/UUID/内容不符 | 保持 unknown，记冲突原因 | 继续屏蔽，不删除任何远端记忆 |
| 历史记录缺少关联、槽已变化、pending、更新或删除产生的未知状态 | 保持当前状态并交人工调查 | 不自动解除屏蔽 |

Fake 的 `authoritative` 和 `not_sent` 模拟严格证据契约，并非客户端输入；真实 Provider 从不将分页读取标为权威，也不会将空列表标为未发送。历史记录不能仅以相同文本认领操作；如果历史上另有独立、可验证的原始写入凭据，仍须人工核对，当前命令不据此自动更改状态。

读取前及读取后分别持有用户行锁，远端 I/O 期间提交事务；返回后清除 ORM 缓存、重新加锁并比较确认回执及语义槽快照。每次成功、拒绝、失败或并发变化的有效操作会在回执中保留操作者、UTC 时间、前后状态及不含正文的分类依据。未找到的操作没有可写的审计记录。已知事件 ID 和待核实 ID 是关联线索，不表示完成。

## 权限和使用

当前 User 模型没有管理员角色；没有新增 HTTP 核销路由。`backend` 目录内执行 `python -m app.commands.reconcile_memory --receipt-id <本地确认操作UUID>` 只输出 dry-run，既不访问数据库也不访问远端；只有主机受控运维人员使用 `--apply` 才查询本地回执并按其所属用户读取远端。命令不接受目标用户 ID，执行者从操作系统账户获取；主机登录权限、配置和数据库凭据的访问控制是实际授权边界，应用本身不提供细粒度运维 RBAC。命令只输出分类，不回显正文或异常详情。不要对真实操作使用它，除非完成运维授权和人工核对。

## 测试与隔离

MySQL 使用本地已有的 `mysql:8.0` 镜像、新建随机命名容器、独立随机凭据、独立 `solomeal_test` schema、主机回环随机端口和容器专属匿名卷。没有连接、停止或修改其他容器或应用数据库；测试结束按容器唯一标签核验所有权后删除容器及其匿名卷。首次 MySQL 运行 **1 通过、2 失败**：会话配置 `expire_on_commit=False` 导致重新锁定时 ORM 身份映射仍返回旧值，两个并发操作可能都解除抑制，或覆盖读取期间的退役。加入 `expire_all()` 及锁后刷新后，最终同组 **3 通过、0 失败、0 跳过**：

```text
python -m pytest --basetemp=<本轮专用目录> --tb=short \
  tests/test_memory_reconciliation.py::test_mysql_simultaneous_reconciliation_commits_only_once \
  tests/test_memory_reconciliation.py::test_changed_slot_during_remote_check_is_not_restored \
  tests/test_memory_operations.py::test_concurrent_confirmation_calls_remote_only_once
```

SQLite 最终定向回归 **125 通过、0 失败、4 跳过**（2 条框架弃用警告），测试命令如下；MySQL 专属跳过不等同于 MySQL 通过。4 项分别是新核销并发 1 项、原记忆 MySQL 并发 2 项和 Agent 会话 MySQL 行锁 1 项；其中新核销并发另在本轮 MySQL 通过，后两类不计作本轮 MySQL 通过。测试进程显式关闭真实 Mem0 和模型并清除 MySQL 测试连接变量。

```text
python -m pytest --basetemp=.tmp-mem0-reconcile-sqlite-final-1228d --tb=short -ra \
  tests/test_memory_reconciliation.py tests/test_memory_operations.py tests/test_memory_agent_api.py \
  tests/test_memory_provider.py tests/test_memory_recommendations.py tests/test_personalization.py \
  tests/test_recommendation_scenarios.py tests/test_memory_diagnostics.py \
  tests/test_memory_mysql_concurrency.py tests/test_home.py tests/test_agent_sessions.py
```

SQLite 初次运行因默认临时目录权限导致 fixture 创建错误；指定隔离工作区目录并在适当权限下重跑。另一轮测试的异常分页 Mock 错误地先模拟 metadata 冲突，产生 1 个测试失败；修正该夹具后通过，未放宽产品断言。测试仅使用 Fake Provider / MockTransport，真实 Mem0 和 Agent 模型开关在测试进程关闭。

Ruff：`python -m ruff check app/services/memory.py app/services/memory_operations.py app/commands tests/test_memory_reconciliation.py tests/test_memory_operations.py tests/test_memory_agent_api.py` 及 `python -m ruff check --select F,E9 app tests` 均通过。运维命令 dry-run 实测不访问数据库或网络。SQLite 测试临时目录含合成数据，保留在工作区忽略的测试临时目录；没有碰触既有数据。

## 已知限制与风险

1. 当前真实 Provider 没有强一致快照证明，实际未知记录无法通过此入口自动变成成功或未发送；未知状态可能长期屏蔽该偏好。需取得服务商明确一致性/事件证据后再设计真实可执行的安全核销，不通过猜测放宽。
2. 历史 `unknown` 没有 UUID，旧 `pending` 无法证明外部请求是否仍在执行，修改/删除操作的未知状态不在本轮确认写入核销范围。
3. 新增单条归属核验多一次 HTTP 请求，可能增加耗时或因索引可见性延迟导致确认进入未知；阶段超时不是端到端上限。本轮没有真实性能数据。
4. 远端控制台的并发修改、删除及已拿到旧记忆的在途推荐仍存在一致性窗口；本地锁不能约束外部控制台。
5. 当前文档允许 `infer=false` 同步结果，但也描述异步事件；纯 `PENDING` 只保留 event ID 和未知状态，尚未提供事件核对或轮询。真实 metadata 持久化以及核验延迟需要在用户未来单独授权的隔离冒烟中验证。
