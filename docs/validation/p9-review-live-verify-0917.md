# 第94节：18082 真实堆栈补验（2026-09-17，第92/93节修正驱动的收口）

范围：用户授权启动。构建含第92节文案的 `solomeal-web:review-fixes-0917`（镜像 ID f2928999404b，镜像内独立 `npm ci && npm run build`），以私有叠加文件 `combined-429-v2.override.yaml` 重启第85节 `solomeal-combined-0917`（127.0.0.1:18082，卷直接复用，`up -d --wait` 后 db/api/web 三容器 healthy；env 实测 `SOLOMEAL_AGENT_ENABLED=false`、视觉关闭）。运行第93节补严后的两个驱动脚本，随后 stop、卷保留。API 沿用已验收 `solomeal-api:p9-boundaries-0917` 未重建。模型调用 0。

## 结果

1. **线上 bundle**：容器实际服务 `index-BTAvzu0t.js`，含 `RUN_NOT_READY` 与新中性文案「当前运行状态无法继续」（独立 curl 抓取复核）。
2. **本地化验证 `deployed-error-localization.mjs` 通过**：POST 前零模型保护生效——枚举全部 run（本例仅 1 个）均为已知终态才发出探测，advance 响应全 409、服务端英文契约原文逐字节保留；failed run（`f05ca042…`，`MODEL_NOT_CONFIGURED`）页面断言从通用前缀升级为完整中文正文「本次运行失败：尚未配置模型…」，且英文原文未达页面。
3. **429 页面场景 `deployed-429.mjs` 通过（补严判定下）**：一次性空账号 150 请求经真实 Nginx→103×200/47×429、`Retry-After:60` 由 Nginx 本体返回、页面中文「请求较频繁，请稍后重试（约 60 秒）」；恢复在第93节口径下成立——第 2 次点击的窗口内本轮全部 5 类 api GET（ingredients/inventory/recipes/cooking/plans）逐条 200（checks.json 留 `final_refresh_responses`）、刷新按钮 busy 窗口闭合、限流提示清除、演示大米与库存统计回显、`page.problems` 空。**真实恢复耗时 3.6 秒（2 次点击）**，取代第91节被作废的 0.2 秒；429 触发与中文提示两项与第91节各自独立复现一致。
4. **离线回归**：`npm test` 36 通过、`npm run build` 通过、`npm run e2e` fixture 18 场景全通过。

## 补验过程中定位并修复的两个驱动缺陷（属本轮验证的一部分）

- **列表投影取数缺陷**：脚本原先从 `GET /api/v1/agent/runs` 列表读 `result?.error`，而列表投影只有 `{id,status,steps}`（`backend/app/api/agent.py:33-41`），该值恒为 undefined——第91节旧版脚本的 failed 页面检查因此从未真正断言过错误正文，本轮升级为精确断言后首次暴露。已改为选中 failed 后再取单个 run 详情视图。应用代码无恙。
- **Playwright API 版本漂移**：`locator.waitFor({state:'enabled'|'disabled'})` 在本仓库锁定的 Playwright 版本中直接抛参数错误（state 仅支持 attached/detached/visible/hidden），首轮补验中它使 busy 窗口判定恒为 false——网络侧其实第 2 轮已 5×200 全绿，脚本仍空转 25 轮。已改为页内轮询 `disabled` 属性界定窗口，并在脚本注释中记录该版本边界。此为第93节驱动的正确性修正，判据未放宽（仍要求本轮 5 接口全 200+窗口闭合+提示清除+数据回显）。

## 状态与边界

- 第91节「429 恢复已收口」的限定自此收口：恢复成功与耗时以补严驱动+新镜像在本节新证据位置成立；第91节原报告与旧证据（含 0.2 秒数值）不改写，仅以本节取代其恢复/耗时两项。
- 18082 卷内新增第 2 个一次性空洪泛账号（`ratelimit429469801`；连同第91节的共 2 个），记入证据 scope。证据文件 `review-fixes-0917-{429,localization}-*` 存于私有 `D:/SoloMeal-Acceptance/p9-combined-0917-01/demo-evidence/`，禁止提交。
- 源 18080 全程未触碰、复查三容器 healthy，仍未部署第91/92节前端（待用户决定）。18082 补验后 stop、卷保留。
- 模型新增 0，累计聊天 1685/视觉 30。P5/P8/P9 整体、旧留出 48/60、holdout_gate=failed、人工清晰度 null 保持。无提交推送。
- 下一步按用户口径进入发布收尾（提交/远程 CI/冻结哈希），须用户授权。
