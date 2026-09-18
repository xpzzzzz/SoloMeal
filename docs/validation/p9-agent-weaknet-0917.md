# P9 真实Agent断线演练（2026-09-17，第88节）

## 范围与方法

在独立Compose项目 `solomeal-agent-weaknet-0917`（127.0.0.1:18085，镜像
`p9-boundaries-0917`，`SOLOMEAL_AGENT_ENABLED=true` + DashScope
qwen3.8-flash、json协议、thinking=false、3000输出预算）前挂自研故障注入代理
`deploy/weaknet_proxy.py`（监听18086，控制18087），对**真实模型开启**的Agent执行
有界断线演练。用户事前批准的估算：6～12次请求/约3.6万～7.5万token，硬上限
16次请求；实际结果见下，全部实测。

本轮为代理新增加法的 `kill_mode="stream"`（响应帧照常转发，计时器到点后在流
中途断连），默认行为不变，第87节证据不受影响。演练驱动为新增
`deploy/agent_weaknet.py`，ruff通过。

演练账号为独立合成账号（演练大米300g + 一份可用菜谱），不触碰用户既有账号。

## 三场景结果（最终批 drill-final，全新幂等键，一次通过）

1. **基线（无故障）**：真实模型经代理两步完成推荐（步骤1调用
   `recommend_meal`，步骤2产出最终回答），run状态completed，无业务写入。
2. **advance 断连（服务端处理完成后杀连接）**：对 `/agent/runs/{id}/advance`
   布防杀死（kill_after_ms=4000）。客户端收到 `RemoteProtocolError`。刷新后按
   前端同样的恢复路径重读run：状态回到 `ready`（服务端已完整落地步骤1的模型
   回复与工具结果，lease已清）；客户端继续advance，run完成。**断连的那次
   advance的模型调用被服务端执行且恰好落库一次，恢复后没有重复执行步骤1，
   也没有额外模型请求；每个run仍是2步**。无业务写入。
3. **SSE流中途断连**：对 `/agent/runs/{id}/events` 布防stream杀死
   （kill_after_ms=1200）。客户端收到1帧（seq=1）后流被掐断。断开后run通过
   无故障路径推进完成，随后客户端携游标重连（与前端 `sse.ts` 的
   Last-Event-ID语义一致）：收到seq 2～5全部缺失帧，**无任何重复帧**
   （断连前后帧序号交集为空，全部大于游标）。无业务写入。

## 用量与预算（实测）

| 项 | 数值 |
|---|---|
| 最终批模型请求（服务端模型尝试steps） | **6次**（3 run × 2步） |
| 最终批客户端发出的潜在模型请求 | 7次 |
| 工具执行 | 3次（每run 1次 `recommend_meal`） |
| 硬上限 | 16次（含驱动调试期间4次，全账号累计12次模型尝试） |
| 最终批墙钟 | 19.611秒 |

token用量：服务端run视图不含usage（`agent_model.py` 元数据仅用于显式评测器，
不入库），本批未逐请求留token数；按第77/79节同配置每请求约5,900～6,150 token
估计约3.5万～4.4万（**估计**），在批准范围内。累计模型请求按**服务端模型尝试**
口径更新为聊天1675/视觉30（1663+12）；若按最终干净批次口径为1669/30。

业务不变性：演练账号库存始终300g（种子1条库存事件）、0条用餐记录、无业务DML；
Agent写入仅限run/tool_events/operations。

## 观察到的行为边界（如实记录）

- advance是同步处理器：客户端断连不取消服务端模型调用，步骤照常落库；
  lease（120秒）在完成后清除，因此重读恢复不需要retry。若断连发生在
  lease期内重读仍为 `running`，驱动实现为有界轮询等待（最终批实测0秒等待）。
- 同键advance幂等：重放返回首次结果；驱动曾复用旧键把历史run当作新场景读取
  （drill-1～4为驱动调试过程，失败与键复用留证），最终批以全新键一次通过。
- 前端「恢复执行」按钮走 `/retry`，仅 `failed`/lease过期 `running` 可重试；
  本批断连未产生failed，未触发retry路径（该路径已有既有离线测试覆盖）。

## 证据

私有目录 `D:/SoloMeal-Acceptance/p9-agent-weaknet-0917-01/`（含env与
credentials，禁止提交）：

- `drill-final/agent-weaknet-results.json` — 最终批三场景结果、客户端日志、代理事件
- `drill-1..4/` — 驱动调试过程留证（键复用与断言失败保留）
- `drill-account.json`、`agent.env` — 凭据与部署env，不提交

代理逐请求事件：最终批两次kill（advance 4.396秒、SSE stream 1.918秒）均在
`proxy_events` 中带 `killed` 标记。

## 边界与保留

- 故障目标为独立合成项目18085/18086；源18080与演示项目18082全程健康未触碰。
- 演练项目已 `stop`、卷保留；不删除卷。
- 模型单次调用30秒超时/每run 8步/上下文60000字符为服务端既有约束，未改动。
- 本演练覆盖「客户端不知道服务端是否已应用」的关键窗口下的Agent恢复；
  不模拟DNS失败/TLS中断/丢包。真实浏览器页面上的Agent断线恢复（UI层）依赖
  既有AgentPanel/sse.ts回归与第87节浏览器场景，本轮为API/SSE客户端语义验证。
- 未演练：主机断电、MySQL数据盘写满、新物理主机验收，按交接另列。
- 无提交推送；源码变更仅 `deploy/weaknet_proxy.py`（加法stream模式）与新增
  `deploy/agent_weaknet.py`。
