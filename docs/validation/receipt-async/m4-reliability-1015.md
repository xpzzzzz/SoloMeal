# M4：RabbitMQ / Celery 可靠性验证（2026-10-15）

本阶段完成：原计划10类场景均取得实际证据，并补双Worker重复消费与发送后确认/状态丢失。没有任务静默消失、重复保存解析版本或未确认入库；发生故障后仍可查看失败/丢弃状态。真实模型调用0。按连续授权进入M4.5。

## 范围与方法

复用隔离 `solomeal-backend-m3-1015-01`，实际MySQL8.0、RabbitMQ4.2.7、Celery5.6.3及真实消息运输，不使用eager模式。Parser是脚本Stub，图片是自造1像素PNG加测试标识，不能用于准确率评价。Worker容器被真实SIGKILL、Broker被真实stop/start，重复消息通过实际AMQP发送。

故障专用overlay将硬上限设15秒、执行租约25秒、总期限180秒、重试/派发间隔0.5秒；生产默认仍为90/120/900秒及10/5秒。缩短边界用于可重复故障演练，观测恢复时间不是生产保证。单Worker并发1，另独立测试两个Worker容器。

受理/outbox/租约实现沿用 [M3报告](m3-normal-workflow-1015.md)。运行配置核对delivery_mode2、confirm_publish=true、late_ack=true、reject_on_worker_lost=true、prefetch1、结果后端None。业务队列为durable quorum；只有一个节点，不能声称集群HA。

## 结果

[原始12项记录](results-m4-1015-01/faults.jsonl)包含10个不同任务，末两项复用已解析任务验证隔离与未确认零入库；不能把12项说成12个独立识别样本。各参与用户库存/事件/采购始终0。本项目此前M3人工确认的数据保留，不把整个项目称为零库存。

| 场景 | 注入方法 | 实际最终状态 / 执行次数 | 关键证据 |
| --- | --- | --- | --- |
| 重复点击 | 相同key两次，另key再点 | succeeded / 1 | 同TaskID，另key409，版本仅2 |
| 重复消息 | 在原消息外真发3条 | succeeded / 1 | Mock一次、版本2 |
| Worker退出 | running后容器SIGKILL并启动 | succeeded / 2 | 租约恢复后约25.6秒到parsed，仍只有一次最终版本更新 |
| Broker不可用 | 先stop Broker，再API受理，后start | succeeded / 1 | 不可用时queued、attempts0、Mock0；恢复观察约18.1秒 |
| 模型超时 | Stub抛TimeoutError | failed / 3 | 有限重试结束，约3.1秒，无业务写入 |
| 非法模型数据 | extra用户字段及NaN | failed / 1 | 原Schema拒绝，手动草稿仍可编辑 |
| 模型连接错误 | Stub抛ConnectError | failed / 3 | 达到次数上限，约2.9秒 |
| 执行中编辑 | running后保存人工草稿 | discarded / 1 | 旧任务完成尝试后草稿/版本2保持人工值 |
| 执行中取消 | running后取消 | discarded / 1 | 旧结果不覆盖取消终态 |
| API响应丢失 | 驱动丢弃受理响应并原key重试 | succeeded / 1 | 同TaskID；另有下述真实浏览器断响应 |
| 跨用户 | 另一用户读取详情/文件及发起parse | 原任务不变 | 三请求均404，无私人数据返回 |
| 未确认成功草稿 | 多个成功场景结束后检查 | draft / parsed | 库存、事件、采购均0 |

[双Worker专项](results-m4-1015-01/parallel.jsonl)：两个实际Worker同时可消费，额外发送5条相同任务消息，仍仅1次执行、1次Mock、最终版本2，无库存。结束后缩回一个Worker。

[确认/状态丢失专项](results-m4-1015-01/ack-loss.jsonl)：暂停常规outbox，显式派发真实消息，实际publish完成后抛异常模拟确认/状态记录丢失；Worker仍从MySQL取得执行权并完成，1次Mock、版本2、无库存，随后恢复outbox。结合重复投递验证，发送端不能单靠“发送失败”判断消息未到达。

[真实浏览器断响应](results-m4-1015-01/browser-response-loss.json)：Playwright先 `route.fetch()` 获得服务器202，再 `route.abort()` 使页面收到网络失败；重试发出的Idempotency-Key完全相同、TaskID相同，重新登录仍恢复parsed，未人工核对按钮禁用、库存0。专项1/1通过。截图、账号与认证Token仅存仓库外。

## 确认、恢复与边界

Broker确认表示消息已由Broker接受，消费确认与MySQL提交是不同机制，参照 [RabbitMQ确认文档](https://www.rabbitmq.com/docs/confirms)。实际业务以MySQL状态、当前执行token、版本和用户行锁保护，重复消息会被跳过；租约过期后能再执行。Worker退出样本中Mock确实调用2次，所以不能声称外部模型“恰好一次”或成本必定一次。

重试只针对超时、传输、限流、5xx及存储类临时错误，有最大次数和总截止；非法响应及不可用进入失败。总截止也会反映在详情状态，用户可以手工编辑。原确认入库保持独立人工操作、版本校验与整单事务。

相关数据库/Schema/锁/库存回归沿用M3最终MySQL85/85、SQLite78通过/7跳过；本阶段生产任务逻辑没有再修改，不靠重复跑同一单测制造覆盖。实际故障验证及新增浏览器场景单独记数。公开结果只含状态/计数/UUID/脱敏类别，凭据扫描通过。

未覆盖：多节点Broker分区、主机断电、磁盘永久损坏/写满、长时间资源饱和、所有网络时序组合、真实付费模型。没有用放宽超时消除失败，也没有清空原数据库。原18080/18088未操作、真实模型0、未提交推送。
