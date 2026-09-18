# P9 浏览器UI层真实Agent断线恢复实测（2026-09-17，第89节）

## 范围与方法

补第88节明确保留的缺口：第88节为 API/SSE 客户端语义验证，本轮在同一套真实模型
环境上，把断线演练的驱动方换成**真实浏览器页面**（`frontend/src/AgentPanel.tsx` +
`frontend/src/sse.ts`），验证 UI 层在 Agent 断线后的自我恢复。

- 环境：独立Compose项目 `solomeal-agent-weaknet-0917`（127.0.0.1:18085，镜像
  `p9-boundaries-0917`，`SOLOMEAL_AGENT_ENABLED=true`，DashScope qwen3.8-flash、
  json协议、thinking=false、3000输出预算）前挂 `deploy/weaknet_proxy.py`
  （监听18086，控制18087）。独立合成演练账号（演练大米300g + 一份可用菜谱）。
- 驱动：IDE浏览器实例，页面 `http://127.0.0.1:18086/`（全部流量经代理）。
  视口被宿主隐藏（0×0、`visibilityState=hidden`），原生指针点击不可用，因此
  输入/提交以页面自身的事件路径触发（React原生value setter + `input` 事件后
  `button.click()`），证据取结构快照、`MutationObserver` 状态串、`fetch` 包装日志、
  DevTools网络列表与代理逐请求日志——与第85/86节同一做法，属结构留证非截图留证。
- 事前估算（用户批准）：6～12次模型请求 / 约3.5万～7.5万token（**估计**）/
  10～20分钟墙钟，硬上限16次。实际见「用量与预算」。

## 场景与结果

### 1. 基线（无故障）

run `88178d99…` completed，`steps=2`，1次 `recommend_meal`，页面显示
「已完成 · 已执行 2 轮」并给出推荐正文（80克，库存足够），无错误告警。

### 2a. advance 断连 ×1（服务端处理完成后杀连接，kill_after_ms=4000）

代理日志两条 advance：`killed`（4.007秒）+ 成功（3.921秒）。DevTools 只有**一条**
advance fetch（200）。

**发现（实测）**：断连被 Chrome 的**连接层透明重试**掩盖——应用代码没有看到任何
失败，UI 无错误提示，run 仍以恰好 2 步完成、无重复步骤、无额外落库。即该故障
形状在浏览器下不必然到达应用层。

### 2b. advance 断连 ×2（同一 run 连续两次布防）

代理日志：killed（4.014秒）、killed（6.364秒）、成功转发（2.144秒）。两次布防的
advance 都被杀，随后应用自身收到 **409 `RUN_NOT_READY`**（该 409 由服务端原样
转发，未被布防）。服务端事实仍是该 run 恰好 2 步、1次工具调用，即被杀的那次
请求没有被重复计成额外步骤。

推断的成因（非直接观测）：advance 为同步处理器，被杀请求在服务端仍在执行并
持有 120 秒租约，故后续 advance 得到 `RUN_NOT_READY` 而非新的一次模型调用。

**发现（UX，如实记录）**：页面告警区显示的是服务端原文
「Run is not ready to advance」（英文、未本地化），而不是第87节网络层那种
「无法连接服务器，请检查网络后重试」的本地文案。同时该 run 的 SSE 进度流未受
影响，面板自动刷新为「已完成 · 已执行 2 轮」并展示推荐正文，**无需用户点击
「继续执行/恢复执行」**。服务端该 run 仍恰好 2 步、1次工具调用、零业务写入。

### 3a. SSE 流中途断连（第一次尝试，kill_after_ms=1200）——未达成，保留

UI 正确显示「连接中断，正在自动重连…」，run 以 2 步完成、零业务写入；但代理
只记录到一次 `events` 请求：重连 fetch 在 run 到达终态、React effect cleanup 取消
 watcher 之前尚未发出。**因此该次未验证到 UI 层的缺失帧补收**，作为方法学局限
保留，不回填为通过。

### 3b. SSE 流中途断连（更早的断点，kill_after_ms=300）——通过

run `3905f1e6…`。`fetch` 包装日志捕获两次 `events` 请求：原始请求
（`Last-Event-ID` 为空，转发 seq 1～2 后被杀）与自动重连
（`Last-Event-ID: 3905f1e6-61bd-40db-9229-28ec9d74151f:2`）。
页面状态串（`MutationObserver`）单调推进，无回退、无重复计数：

进度已连接 → 运行中·已执行1轮 → 连接中断，正在自动重连… → 进度已连接 →
运行中·已执行2轮 → 已完成·已执行2轮

服务端事实：run completed、`steps=2`、`event_seq=5`、1次 `recommend_meal`。
**浏览器UI层的 Agent SSE 断线恢复实测通过**：游标续收由 `sse.ts` 自动完成，
不需要用户干预。

## 测试工具缺陷与修复（不是应用行为）

场景2首次提交 `POST /api/v1/agent/runs` 在浏览器永久挂起：代理无事件、API 容器
日志无请求、run 未创建。以 DevTools 待处理请求 + `netstat`（4条客户端
ESTABLISHED 对 4条上游 CLOSE_WAIT）+ 原始 socket 受控复现（先发一个请求、空闲
80秒、同连接再发第二个 → 15秒内无响应）定位为 `deploy/weaknet_proxy.py` 缺陷：
每条客户端连接只在开头建立一次上游连接且不检查 `StreamReader.at_eof()`，
nginx 默认 75 秒空闲关闭上游后，下一个请求被转发进已死的上游而静默丢失
（`deploy/nginx.conf` 只设了 `proxy_read_timeout 180s`，未改空闲关闭）。

修复：`handle()` 内逐请求检查上游存活并在需要时透明重连（真实反向代理的行为），
默认故障注入语义不变——第87/88节证据不受影响（其场景无 >75 秒空闲间隔）。
`ruff check deploy/weaknet_proxy.py deploy/agent_weaknet.py` 全部通过。复现验证：
同一 80 秒空闲序列修复后第二个请求返回 `HTTP/1.1 200 OK`，经代理取
`/healthz` 亦 200。

## 用量与预算（实测）

| 项 | 数值 |
|---|---|
| 新建 run | 5个（基线、2a、2b、3a、3b），各恰好 `steps=2` |
| 模型请求（服务端模型尝试口径） | **10次** |
| 客户端发出的潜在请求 | ≤10次 advance/retry + 5次建run |
| 批准估算 / 硬上限 | 6～12次（估计）/ 16次 |
| 墙钟 | 约38分钟（20:47 建目录 → 21:25 场景3b留证，含一次代理缺陷定位与修复） |

token：服务端 run 视图不含 usage，本批未逐请求留 token；按第77/79节同配置
每请求约5,900～6,150 token 估计约5.9万～6.2万（**估计**）。累计模型请求按
服务端尝试口径更新为聊天 1675+10 = **1685**/视觉 30。

业务不变性（每个场景后均核对）：演练账号库存始终「演练大米 300.000 g」、
库存事件始终恰 1 条（种子）、用餐记录 0 条 —— 五个 run 零业务写入、无重复应用。

## 证据

私有目录 `D:/SoloMeal-Acceptance/p9-agent-ui-weaknet-0917-01/ui/`（含凭据
`token.json`，禁止提交、禁止重跑或追加）：
`scenario1-baseline.json`、`scenario2a-advance-kill-retry.json`、
`scenario2b-advance-kill-app-visible.json`、`scenario3a-sse-kill-attempt1.json`、
`scenario3b-sse-reconnect.json`、`state-before-scenario2.json`、
`incident-stale-upstream.json`（挂起事故与受控复现）、`proxy-fix-verify.json`、
`final-verification.json`（21:34:59 收尾复核：11个run总量、本会话5个run合计10次模型
尝试、库存/事件/用餐不变量、代理布防已清除、收尾停机与ruff结果）。
代理逐请求 kill 标记（`mode:"request"` 与 `mode:"stream"`）随各场景 JSON 保存。

收尾复核时浏览器会话令牌已过期，故用第88节演练账号重新登录一次（仅认证，
不产生模型请求），再经 18085 直连 API 读回上述不变量。

## 边界与保留

- 视口隐藏，故为结构快照/事件流留证，非人眼截图验收；未做视觉清晰度评估。
- 2a 说明：单条 advance 断连在 Chrome 下可被连接层重试掩盖；UI 层真正到达
  应用的是 2b 的 409 与 3b 的流中断。两者恢复均通过，但 2b 的 409 文案未本地化，
  作为已知 UX 观察保留，未改代码。
- 未覆盖：DNS 失败 / TLS 中断 / 丢包乱序；`failed` 后点「恢复执行」（`/retry`）
  的人工路径本批未触发；多标签页并发、离线（`navigator.onLine=false`）长断线。
- 故障目标仅为独立合成项目 18085 与其代理 18086/18087；源 18080 用户试用环境
  全程未触碰且健康。演示项目 18082（录制本轮已取消）经用户决定 stop、卷保留。
- 未演练：主机断电、MySQL 数据盘写满、新物理主机验收，按交接另列，须先给有界
  估算由用户决定。
- P5/P8/P9 整体及旧留出 48/60（`holdout_gate=failed`）保持不变；无提交推送，
  源码变更仅 `deploy/weaknet_proxy.py`（上游重连修复）。
