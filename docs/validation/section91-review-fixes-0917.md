# 第92节：第91节独立复核三处修正（2026-09-17，仅离线）

范围：按 `docs/validation/review-section91-0917.md` 的三项 P2 发现修正文案与验证驱动；未启动真实堆栈、未运行浏览器 e2e、未调用模型、未部署、未提交推送。历史报告与原证据不改写。

## 修正内容

1. **STEP_LIMIT / RUN_NOT_READY 文案**（`frontend/src/errorText.ts`）
   - `STEP_LIMIT` 原建议「点击继续执行或恢复执行」不可执行：服务端 retry 分支只置回 ready、不重置 `steps`（`backend/app/services/agent.py:575-577`），恢复后 advance 在 `steps>=8` 立即再次 STEP_LIMIT（392 行）。现改为「助手已达到单轮步数上限，继续或恢复都会立即再次超限；请开始新对话」。服务端预算未放宽、后端零改动。
   - `RUN_NOT_READY` 对所有非 ready 状态（含 completed/cancelled/failed，391 行）统一返回，原文案断言「上一步仍在处理中」不成立。改为中性提示「当前运行状态无法继续…请查看运行状态，或开始新对话」。
   - `frontend/tests/errorText.test.mjs`：RUN_NOT_READY 断言同步；新增 STEP_LIMIT 反例测试（必须含「开始新对话」、不得出现「继续执行/恢复执行」）。
2. **429 恢复判定与计时**（`frontend/e2e/deployed-429.mjs`）
   - 恢复循环不再以「表格行存在 + 页面含演示大米」判定（刷新失败时旧 batches 滞留页面即可假通过）；改为每次点击「刷新库存」后等待本轮 `/api/v1/inventory` 返回 200 的网络响应（`page.waitForResponse`，先建等待再点击，避免拿到陈旧响应），命中后再断言限流提示已清除、页面含演示大米与库存统计。checks.json 新增 `recovery_clicks`。
   - `recovery_seconds` 由 `Math.round(ms/1000)/10`（缩小十倍）改为 `Math.round(ms/100)/10`。第91节报告的 0.2 秒不作为恢复耗时证据；429 触发与中文提示两项证据不受本缺陷影响，维持原样。
   - **第93节跟进**：用户复核指出该修复仍不彻底——一次刷新并行发 5 个 GET，且 `perform` 在请求发出前即清空错误，仅凭 `/inventory` 200+固定 500ms 静默可能出现「库存200＋暂无错误＋旧表格」的假通过。已再修正：每次点击「刷新库存」收集本轮全部 5 类 api GET 响应，要求每类接口均出现且全部 200（分页允许多次），并以按钮进入再离开禁用（busy）窗口作为本轮刷新结束的信号，之后才断言无「请求较频繁」与数据回显；checks.json 新增 `final_refresh_responses` 逐条留证。`node --check`、`npm test` 36 通过、`npm run build` 通过且 bundle 仍为 `index-BTAvzu0t.js`（仅驱动改动）。真实堆栈补验已于第94节在 18082 执行并通过（新镜像 `review-fixes-0917`，恢复 3.6 秒/2 次点击、本轮 5 接口全 200 留证），见[第94节报告](p9-review-live-verify-0917.md)；补验中另修复了本目录脚本一处列表投影取数缺陷与一处 Playwright `waitFor` 版本漂移，均在第94节报告中记录。
3. **本地化验证脚本零模型保护顺序**（`frontend/e2e/deployed-error-localization.mjs`）
   - advance 探测改为两步：先只读列出 run，POST 前断言全部处于已知终态（failed/completed/cancelled/approved）——存在 ready/running run 即直接失败、不发任何 advance；随后仅对终态 run 探测，并断言响应全部为 409（原「先对全部 run 发 advance、事后才检查无 200」的顺序废除）。
   - failed 页面检查从通用前缀升级为按错误码断言 `errorText.ts` 的完整中文正文（脚本内镜像表注明须与源表同步）；bundle 断言短语同步新文案。历史第91节批仅有 failed run、全 409，不据此推断该批有额外模型调用。

## 验证

- `node --check` 两个 e2e 脚本通过。
- `npm test` 36 通过 / 0 失败（35 + STEP_LIMIT 反例 1）；`npm run build` 通过，产物 `index-BTAvzu0t.js`（文案变更故哈希不同于第91节 `index-Cg0QL_Q5.js`）。
- 未复跑：`npm run e2e` fixture 套件、18082 真实堆栈两脚本。第91节「429 恢复已收口」结论在本驱动下**待重演补验**；重演需以 `solomeal-web` 新构建镜像（含本轮文案）重启 18082 叠加项目，属部署动作，待用户决定。源 18080 仍未部署第91/92节前端。

模型新增 0、累计聊天 1685/视觉 30。P5/P8/P9 整体及旧 48/60、holdout_gate=failed、人工清晰度 null 保持，无提交推送。
