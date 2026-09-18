# 第91节：服务端错误原文本地化与真实 Nginx 堆栈浏览器 429 页面场景（2026-09-17）

日期：2026-09-17。范围：按 [最终验收清单](final-acceptance-checklist-0917.md) 第 E 节第 2 步的两项零模型成本任务——（1）409 `RUN_NOT_READY` 等服务端错误原文本地化（第89节 2b 唯一已知 UI 缺陷）；（2）在真实 Nginx 限流堆栈下补一条浏览器 429 页面场景（第84节仅拦截夹具、第85节列为未覆盖）。模型请求新增 0，累计聊天 1685、视觉 30 不变。无提交推送。

## 1. 前端实现（唯一应用代码改动）

- 新增 `frontend/src/errorText.ts`：把原先内联在 `main.tsx` 的错误码表抽为独立模块并补全。本轮新覆盖的码：`RUN_NOT_READY`、`RUN_NOT_PENDING`、`RUN_FINISHED`、`RUN_NOT_RETRYABLE`、`CONTEXT_LIMIT`、`STEP_LIMIT`、`MODEL_UNAVAILABLE`、`MODEL_PROTOCOL_ERROR`、`QUANTITY_TOO_LARGE`、`DUPLICATE_INGREDIENT`、`MIGRATIONS_PENDING`、`DATABASE_NOT_READY`、`IDEMPOTENCY_CONFLICT`、`EXAMPLE_UNIT_CONFLICT`、`RECEIPT_PARSER_UNAVAILABLE`、`RECEIPT_PARSER_FAILED`，以及通用 `CONFLICT`。
- 兜底规则：凡带 `error.code` 且未入码表的响应，一律显示中性中文「操作未完成，请重试或刷新页面」，**不再回显服务端英文原文**；无码的响应（非本后端契约）保持原样透传，该分支本堆栈未触发。
- 带行号的动态消息（`RECEIPT_REVIEW_REQUIRED`/`RECEIPT_DATE_REQUIRED`，服务端原文含行号且码表在消息之前生效）按「每个码只对应一种服务端消息形状」的模式匹配保留行号并本地化。此依赖为**推断**，非服务端强制契约。
- `main.tsx` 请求边界改走 `errorText(data?.error)`；`AgentPanel.tsx` 的 run 级失败展示由「仅特判 MODEL_NOT_CONFIGURED、其余显示原始码」改为统一 `errorText(run.result.error)`（服务端该信封只含 `code` 无 `message`，按码渲染）。
- 后端**零改动**：服务端英文契约文案原样保留（供日志与第88/89节断线语义），见第 3 节镜像比对。
- `frontend/package.json` 的 `test` 脚本编译列表加入 `src/errorText.ts`。新增 `frontend/tests/errorText.test.mjs` 6 项离线断言（409 中文、无 message 的 run 级码、行号模式、未映射码不回显原文、已知码命中、无码兜底）。

## 2. 离线验证

- `npm test`：35 通过 / 0 失败（原 29 + 新增 6）。
- `npm run build`（`tsc --noEmit` + vite）通过；产物 `dist/assets/index-Cg0QL_Q5.js`（254.97 kB），与部署 bundle 文件名一致。
- 完整 fixture 浏览器套件 `npm run e2e`：见第 5 节结果（后台执行，不改动任何冻结判据，脚本模型/临时 SQLite，无真实模型）。

## 3. 真实堆栈部署与比对

- 新镜像 `solomeal-web:errtext-0917`（镜像 ID `b5395f6b16f6`），在镜像内独立 `npm ci && npm run build`；API 沿用已验收的 `solomeal-api:p9-boundaries-0917`（ID `908cf165568b`），compose 叠加文件为私有目录 `combined-429.override.yaml`（仅覆盖 web 镜像）。
- 后端未变实证：磁盘 `backend/app`+`backend/scripts` 共 67 个 `.py` 与已验收 API 镜像内同名文件 **sha256 逐一比对，67/67 一致、0 不一致**。历史聚合指纹 `c3161b9b…` 的生成配方未随证据留存、本轮无法复现，故不引用其数值作比对，改用上述逐文件口径。
- 项目：复用第85节 `solomeal-combined-0917`（127.0.0.1:18082，卷保留直接 `up -d --wait`），四容器 healthy。源 18080 全程未触碰、复查健康。**源 18080 尚未部署本轮前端**（是否重部署待用户决定）。

## 4. 真实 Nginx 堆栈浏览器 429 页面场景（`frontend/e2e/deployed-429.mjs`）

- 洪泛改由页面内注册的**一次性空账号**发起（临时用户 `ratelimit429941349` 留在该项目，数据零写入），演示账号会话不受影响。
- 150 个真实请求经页面同源 `fetch` 打到 18082：104×200、**46×429**，429 的 `Retry-After` 头由 **Nginx 本体**返回且实测恒为 `60`（非 page.route 拦截）。
- 页面点「刷新库存」→ 显示中文提示「请求较频繁，请稍后重试（约 60 秒）」并截图；随后每 2 秒手动重试，**首次尝试即恢复**（自定循环计时 0.2 秒，另有循环前 2 秒固定等待；第85节记录的桶约 6 秒恢复），库存表回显「演示大米」等全部行，前后行数不减。
- 断言含 `page.problems` 无页面异常。证据：`deployed-429-checks.json`、`deployed-429-rate-limited.png`、`deployed-429-recovered.png`（私有目录 `D:/SoloMeal-Acceptance/p9-combined-0917-01/demo-evidence/`，含凭据文件禁止提交）。

## 5. 本地化的部署层验证（`frontend/e2e/deployed-error-localization.mjs`）

- 线上 bundle 含新码表：抓取 `http://127.0.0.1:18082/assets/index-Cg0QL_Q5.js`，同时含 `RUN_NOT_READY` 与中文文案「上一步仍在处理中」。
- 服务端契约未动：对该项目全部 run（1 个，`failed`）逐一 POST advance，全部返回 409，`error.code=RUN_NOT_READY`、`error.message` 逐字节等于「Run is not ready to advance」；0 个 200（无 ready run，探测不推进任何状态机）。
- 页面渲染：展开「所有运行记录」打开该 failed run，页面显示「本次运行失败：尚未配置模型…」中文文案，全文不含「Run is not ready」。
- 局限如实保留：UI 告警区显示 409 本地化字符串的**即时**路径（连杀两条 advance 的真实断线场景）本轮未重演——那需要模型环境的 weaknet 演练；本轮证明的是同一渲染管线（`api`→`errorText`）、新代码已上线、且服务端原文与第89节观测逐字节一致。
- fixture e2e 套件 `npm run e2e`：18 场景全通过 / 0 失败（含拦截夹具那条 429 场景回归），未受本轮改动破坏。

## 6. 哈希与清单

本轮改动/新增文件（sha256）：

```
68996159549d6aab4b28a60c68081e7d3e9570d8b08d7396d77941962323c0a9  frontend/src/errorText.ts
2dddf94736482c4f02d41b02aaaf2500fa5d7adca3181905ba48102c10669649  frontend/src/main.tsx
68ddfc47b5fa87675510ad3337752225de26243387ab1fc9610270297d4d94a4  frontend/src/AgentPanel.tsx
b01548276f6c0c100d607f533f90b0f2469519e834300d3e4f8f26422fd91470  frontend/package.json
e9871e8bf8050fbb8222ae80c30199875f04e27e26ddcca318bc7f5646ce0017  frontend/tests/errorText.test.mjs
8259d1d28270d263f6a3feb45cc9ee07ce969f5f1b1e53fb2f0b2ca7c3b74bf4  frontend/e2e/deployed-429.mjs
1168d7342b53d236f53fa2992392d05949c0461de1efd0d12362f6aed42d3447  frontend/e2e/deployed-error-localization.mjs
```

前端聚合指纹（`frontend/src`、`frontend/e2e`、`index.html`、`package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig.json` 逐文件 sha256 连缀再 SHA256，本轮新口径）：`ffaf63b72e5c354306a1d005871d367f1955eb704fc972658ad718fb7c2395cd`。

## 7. 环境与收尾状态

- `solomeal-combined-0917`（18082）本轮为运行态（web 为新镜像），会话结束按惯例 stop、卷保留；其 web 容器现指向 `errtext-0917`，下次 `up` 若不带叠加文件会回到 `p9-boundaries-0917`，需要时以叠加文件启动。
- 18082 项目现多出 1 个空的演示外账号（429 洪泛用），已记入证据 JSON 的 scope。
- 未动：源 18080、开发库、MySQL80、任何旧私有批次目录。旧批次禁止重跑/追加规则继续有效；`verify_deployment.py` 的 auth-flood 模式仍须最后跑（本项目今日又消耗了登录配额，近期跑 auth-flood 需等配额回滚）。
- 第89节 2b 由「已知未修缺陷」转为「已修复并按上述三层验证」；清单 D 节该项移除，B 节「真实 Nginx 限流下的浏览器 429 提示」收口。
