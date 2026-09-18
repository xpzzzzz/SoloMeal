# SoloMeal 接手（2026-09-18，第97节：UI 侧偏好覆盖缺陷修复，前端冻结量更替，18080 重部署与 Dependabot 处置进行中）

第97节（用户授权处置三项低成本决定）：第1项已完成——第96节保留的 UI 侧缺陷（偏好面板挂载 GET `/me/preferences` 晚落地清掉用户已输入厨具）修复于 `frontend/src/main.tsx` 的 `Preferences`（+4/−2 行：`edited` ref，四个字段 `onChange` 统一经 `edit()` 置位，挂载响应仅在未编辑时回填）。新增 e2e 回归 `frontend/e2e/preferences-race.test.mjs`：注入 1500ms 延迟断言输入不被覆盖、PUT 存 `["煮锅"]`，并做**双向验证**（还原旧代码该用例失败、修复版通过）。本地全绿：插件 Windows 373+298、前端 36、build 产物 `index-D2Luux6J.js`、e2e **19/19**（原 18 未放宽）。**前端冻结量取代第95节值（历史不改写）**：源码聚合 `4285ae31…`→`1a99ab46a45e6431b08e20cb3743990b6445e482d7ae0740d32c6593acd7ba48`（同口径 15 文件）、产物 `BTAvzu0t`→`D2Luux6J`；后端 `c3161b9b…`/API 镜像 `908cf165568b…` 不变，web 镜像待按新产物重建（`f2928999404b…` 不再是新版本目标）。两文档性哈希不被 freeze 测试引用，CI 无预期失败项。代码提交 `4c47ee2`（pre-commit 实跑）。**本轮后续步骤（结果以 Actions 运行列表为准，不在本节预写）**：推送复验远程九作业 → 以新 `frontend/` 构建 web 镜像重部署源 18080（仅 web、卷不动）→ 处置 Dependabot PR #1。仍未做：其它面板「挂载即 GET＋受控输入」同类竞态未穷举；未做 stress 多轮 e2e。模型新增 0、累计 1685/30。详见[修复报告](docs/validation/ui-preferences-clobber-fix-0918.md)与 SOLOMEAL_STATUS 第97节。

下一步（严格顺序，均须前置就绪）：
1. CI 绿只了结「远程流水线未跑」这一条（绿点随 HEAD 推进需重验）。**P9-04 的新物理主机验收与 v1.0 发布仍是独立条件**，不得并入完成宣称；P5/P8/P9 整体、旧 48/60、`holdout_gate=failed`、真人清晰度 null 全部保持。
2. v1.0 发布（Release/Tag 与镜像 digest 绑定）须用户另行授权；冻结基线：后端/API 仍为第95节 `f3f9c7b` 值，**前端以第97节新聚合 `1a99ab46…`＋产物 `D2Luux6J` 为准**，web 镜像重建后 digest 另行登记。Dependabot PR #1 处置在本轮进行。
3. 剩余待用户决定的小改动：409 即时本地化的真实断线路径可在下次模型 weaknet 演练顺带补测；其它面板同类挂载竞态是否穷举排查。
4. 需授权/需资源，先给有界估算再由用户决定：独立人工清晰度包与新小票留出、新源码完整留出复验、新物理主机部署、主机断电与 MySQL 数据盘写满。

保留原样不改写：合成留出 Agent 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null、旧各批失败与超时样本；后续修复与小批诊断属已暴露回归，不冒充新盲测、不改旧分数。旧私有目录与各模型批次禁止重跑或追加，第82节五项真机反馈不重复索取，源 18080 用户试用环境不作故障目标。

环境与保护：18082 项目现含 2 个空的演示外洪泛账号（第91节 `ratelimit429941349`、第94节 `ratelimit429469801`），记入证据 scope；证据与凭据在私有 `D:/SoloMeal-Acceptance/p9-combined-0917-01/demo-evidence/`（含 credentials.json、deployed-429-*、deployed-errtext-* 与 review-fixes-0917-* 的 JSON/PNG），禁止打印或提交、禁止重跑。第94节以 `combined-429-v2.override.yaml`（web=solomeal-web:review-fixes-0917）启动后已 stop、卷保留；不带叠加文件启动会回到 p9-boundaries-0917。`verify_deployment.py` auth-flood 会耗尽登录配额须最后跑。演练项目卷不 down -v。根下 5 个 ACL 锁死的 `.pytest-*`/`.test-tmp-crud-0906` 目录未跟踪未 ignore 且 git 不可读，`git status --porcelain` 打权限警告但退出码 0，勿删除勿改权限。第96/97节的注入复现脚本：第96节者在仓库外跑完即删；第97节的延迟注入已固化为仓库内 e2e 用例 `preferences-race.test.mjs`。

以下为历史快照。

# SoloMeal 接手（2026-09-18，第96节：第95节文档推送暴露 browser-e2e 竞态，注入复现后在驱动侧修复，HEAD 重新全绿）

第96节（沿用第95节的提交/推送授权，本轮不再冻结新哈希）：第95节两份收口文档提交推送后 run `35320718788` 的 `browser-e2e` 失败 2/18 并连带 `ci-complete` failure（其余七作业 success）——**「CI 全绿」自此只在冻结点 `f3f9c7b` 成立，不在分支 HEAD 成立**。先排除回归（`f3f9c7b..1b6cf00` 只有 7 个 `.md`，两轮 `npm run build` 产物同为内容哈希命名的 `index-BTAvzu0t.js`，被测 JS 字节相同），再读代码定因：偏好面板每次挂载都重读 `/me/preferences` 且字段受控（`frontend/src/main.tsx:79`）、保存按钮 `disabled={busy}`（`:58`/`:80`），而 e2e 的 `useTab` 切 tab 后不等该 GET（`frontend/e2e/support.mjs:120`）即填厨具——**慢响应下「挂载响应覆盖已输入内容」必然发生在点击之前**；随后 PUT 存空厨具，后端按厨具子集硬过滤（`backend/app/services/planning.py:56-58`/`:115`）使候选清零，页面出现与 CI 逐字相同的「没有符合条件的菜谱」。离线故障注入同一 GET 延迟 1500ms 做 A/B：旧写法 PUT body `equipment: []` 且复现失败文案，新写法 `equipment: ["煮锅"]` 且页面正常。修复 `d3fcb9d` **只动四个 e2e 文件**（新增 `openPreferences` 就绪等待、改四处写入前置调用点，`mobile.test.mjs:103` 的读取回显等待未动），未放宽断言、应用代码零改动；`npm run e2e` 本地 18/18，复跑 run `35322761131` 九作业全 success、`ci-complete` 于 `2026-09-18T08:18:03Z`；本节文档提交 `348fdf6` 的 run `35324565914` 同样九作业全 success（`08:39:22Z`），即文档改动未触及任何冻结校验（为补记该事实而生的后续提交不再自我登记，以 Actions 列表为准）。**第95节冻结值不被推翻**：前端源码聚合改动后仍 `4285ae314aace08a…205001aa`（15 文件、`e2e/` 不在口径内），产物、后端 `c3161b9b…`、两镜像 digest 均未变；该口径此前只记结果未记算法，报告已补可复现定义。顺带查实并更正一处过期事实：交接写的「本地插件套件 372+298」经同 clone 两提交对拍实为 **373**+298（`test_unit.py:2271` 逐 `- uses:` 行核对钉版，修 CI 时给 backend 作业加了 `setup-node` 一行），Linux CI 为 376+300，四处交接文档已按平台分别标注。**刻意未做**：UI 侧同一覆盖缺陷（真实用户慢网络下输入仍可能被挂载响应清掉）未修——改 `main.tsx` 会使已冻结并通过 CI 的前端产物变化、须重走冻结与验收，待用户决定；「挂载即 GET ＋受控输入」在其它面板是否同样构成竞态未穷举；未做 stress 多轮重跑量化其余场景残余抖动。模型新增 0、累计 1685/30。详见[竞态报告](docs/validation/browser-e2e-preferences-race-0918.md)与 SOLOMEAL_STATUS 第96节。

下一步（严格顺序，均须前置就绪）：
1. CI 绿只了结「远程流水线未跑」这一条（且已两度证明：绿点会随 HEAD 推进而需要重验）。**P9-04 的新物理主机验收与 v1.0 发布仍是独立条件**，不得并入完成宣称；P5/P8/P9 整体、旧 48/60、`holdout_gate=failed`、真人清晰度 null 全部保持。
2. v1.0 发布（Release/Tag 与镜像 digest 绑定）须用户另行授权；已推送至私有 `origin` 的高水位现在是第96节的文档提交（其父为测试驱动修复 `d3fcb9d`），而第95节冻结点仍是 `f3f9c7b`——三者关系以 `git log --oneline` 为准。Dependabot PR #1（`setup-node` 升版）仍 open、head 早于本轮提交，处置（rebase/关闭）待用户决定。
3. 待用户决定的小改动：源 18080 是否重部署新前端（现线上验证版本 `review-fixes-0917`/`index-BTAvzu0t.js`）；UI 侧偏好覆盖缺陷是否修（修即触发前端重新冻结＋CI 复验）；409 即时本地化的真实断线路径可在下次模型 weaknet 演练顺带补测。
4. 需授权/需资源，先给有界估算再由用户决定：独立人工清晰度包与新小票留出、新源码完整留出复验、新物理主机部署、主机断电与 MySQL 数据盘写满。

保留原样不改写：合成留出 Agent 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null、旧各批失败与超时样本；后续修复与小批诊断属已暴露回归，不冒充新盲测、不改旧分数。旧私有目录与各模型批次禁止重跑或追加，第82节五项真机反馈不重复索取，源 18080 用户试用环境不作故障目标。

环境与保护：18082 项目现含 2 个空的演示外洪泛账号（第91节 `ratelimit429941349`、第94节 `ratelimit429469801`），记入证据 scope；证据与凭据在私有 `D:/SoloMeal-Acceptance/p9-combined-0917-01/demo-evidence/`（含 credentials.json、deployed-429-*、deployed-errtext-* 与 review-fixes-0917-* 的 JSON/PNG），禁止打印或提交、禁止重跑。第94节以 `combined-429-v2.override.yaml`（web=solomeal-web:review-fixes-0917）启动后已 stop、卷保留；不带叠加文件启动会回到 p9-boundaries-0917。`verify_deployment.py` auth-flood 会耗尽登录配额须最后跑。演练项目卷不 down -v。根下 5 个 ACL 锁死的 `.pytest-*`/`.test-tmp-crud-0906` 目录未跟踪未 ignore 且 git 不可读，`git status --porcelain` 打权限警告但退出码 0，勿删除勿改权限。第96节的注入复现脚本在仓库外、跑完即删，未提交。

以下为历史快照。

# SoloMeal 接手（2026-09-18，第95节发布准备收口：推送至自有私有仓库、远程 ci-complete 全绿、哈希冻结）

第95节（用户授权完整执行）：420 文件安全盘点无真实凭据；本地离线套件全绿（插件本地 Windows 373+298（2 项平台 SKIP；Linux CI 376+300）、前端 36/build `index-BTAvzu0t.js`/e2e 18、后端 530 通过/16 MySQL 跳过）；分组提交 `9a060b0`/`f9fbcf8`/`5eb512f`/`0935c99`/`39ab68f`，修 CI 的 `1882669`/`f3f9c7b`，pre-commit 钩子逐次实跑、无 `--no-verify`；索引以单次 `-c core.autocrlf=input` 保持 LF、仅 31 个摘要钉住路径按原字节入库（未改 git 全局配置）。**初稿的推送 403 结论前提有误已更正**：`sergiparpal/meal-manager` 只是 `docs/upstream.md:4` 记录的只读上游、用户与其无关联，不存在待恢复的写权限；推送目标改为用户自有私有仓库 `https://github.com/xpzzzzz/SoloMeal`（`origin`），`upstream` push URL 置 `DISABLED`。**远程 CI 首次全绿**：run `35319166877`（push @ `f3f9c7b`）九作业含 `ci-complete` 全 success（`07:34:33Z`）；backend 内 MySQL 轮 546 通过、SQLite 回退轮 530 通过/16 跳过。三类失败根因均在本地以 Linux 等价检出复现后修复：冻结摘要按原始 CRLF 字节记录而被 LF 规范化打破（`.gitattributes -text` + 逐字节回钉 31 路径，零内容改动）、`mypy -p meal_manager` 误纳 `deploy/`+`docs/`（exclude 收口）、backend 作业 15 分钟上限与缺 `frontend/dist`（加 `npm ci && npm run build`、预算 20 分钟、断言未放宽）。冻结量：提交 `f3f9c7b…`、tree `d0d02354…`、后端源码聚合 `c3161b9b…`（67 文件，同第84/91节值即后端零改动）、API 镜像 `sha256:908cf165568b…`、web 镜像 `sha256:f2928999404b…`、前端源码 `4285ae31…`（15 文件，自订补充口径）。**哈希口径限制**：源码聚合按工作区字节算，跨平台换行不同即不同值，发布以 commit SHA＋tree＋镜像 digest 为准。工作区限定：已跟踪文件除本轮文档外无未提交改动；根下 **5 个**（初稿误记 6 个）ACL 锁死的 `.pytest-*`/`.test-tmp-crud-0906` 证据目录未跟踪未 ignore 且不可读，`git status --porcelain` 打权限警告但**退出码 0**（初稿误记 2），勿删除勿改权限。详见[发布准备报告](docs/validation/release-prep-0918.md)与 SOLOMEAL_STATUS 第95节。

下一步（严格顺序，均须前置就绪）：
1. CI 绿只了结「远程流水线未跑」这一条。**P9-04 的新物理主机验收与 v1.0 发布仍是独立条件**，不得并入完成宣称；P5/P8/P9 整体、旧 48/60、`holdout_gate=failed`、真人清晰度 null 全部保持。
2. v1.0 发布（Release/Tag 与镜像 digest 绑定）须用户另行授权；本轮仅推送到私有 `origin`，未建任何 tag/release。Dependabot PR #1（`setup-node` 升版）仍 open、head 早于本轮两提交，处置（rebase/关闭）待用户决定。
3. 可选小改动：源 18080 是否重部署新前端（现线上验证版本 `review-fixes-0917`/`index-BTAvzu0t.js`）待用户决定；409 即时本地化的真实断线路径可在下次模型 weaknet 演练顺带补测。
4. 需授权/需资源，先给有界估算再由用户决定：独立人工清晰度包与新小票留出、新源码完整留出复验、新物理主机部署、主机断电与 MySQL 数据盘写满。

保留原样不改写：合成留出 Agent 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null、旧各批失败与超时样本；后续修复与小批诊断属已暴露回归，不冒充新盲测、不改旧分数。旧私有目录与各模型批次禁止重跑或追加，第82节五项真机反馈不重复索取，源 18080 用户试用环境不作故障目标。

环境与保护：18082 项目现含 2 个空的演示外洪泛账号（第91节 `ratelimit429941349`、第94节 `ratelimit429469801`），记入证据 scope；证据与凭据在私有 `D:/SoloMeal-Acceptance/p9-combined-0917-01/demo-evidence/`（含 credentials.json、deployed-429-*、deployed-errtext-* 与 review-fixes-0917-* 的 JSON/PNG），禁止打印或提交、禁止重跑。第94节以 `combined-429-v2.override.yaml`（web=solomeal-web:review-fixes-0917）启动后已 stop、卷保留；不带叠加文件启动会回到 p9-boundaries-0917。`verify_deployment.py` auth-flood 会耗尽登录配额须最后跑，且本项目今日已多次消耗配额需等回滚。演练项目卷不 down -v。

以下为历史快照。

# SoloMeal 接手（2026-09-17，第91节复核三处问题已全部修复并在真实堆栈补验通过，进入发布准备）

第93节（仅离线）按用户二次复核把 429 恢复判定补严：每次点击收集本轮全部 5 类 api GET、要求全 200，并以刷新按钮 busy 禁用窗口闭合界定本轮结束。第94节（用户授权）构建 `solomeal-web:review-fixes-0917`（f2928999404b）重启 18082 后实跑两脚本全部通过：**429 恢复成立，真实耗时 3.6 秒/2 次点击（取代作废的 0.2 秒），final_refresh_responses 逐条 200 留证**；本地化验证在 POST 前零模型保护下全 409、failed 页面精确中文正文。补验中另修复两个驱动缺陷（列表投影无 result 使旧版正文断言从未生效；本 Playwright 的 `locator.waitFor` 不支持 enabled/disabled），应用代码零改动。见 docs/validation/p9-review-live-verify-0917.md。

第92节（仅离线）已修复 `docs/validation/review-section91-0917.md` 三处 P2：STEP_LIMIT/RUN_NOT_READY 文案改为可执行/中性提示（+反例单测，`npm test` 36 通过、`npm run build` 通过，产物 `index-BTAvzu0t.js` 即线上版本）；`deployed-429.mjs` 恢复判定绑定网络、计时改 `Math.round(ms/100)/10`；`deployed-error-localization.mjs` 零模型保护前移到 POST 前并按错误码断言精确中文正文。历史：第91节 35 前端单测复跑通过、三文件哈希匹配，但发现上述三问题。不覆盖旧证据、第92/93节无模型调用/部署，第94节模型新增 0，均无提交推送。见 docs/validation/section91-review-fixes-0917.md。

2026-09-17第91节：完成第90节列出的前两项零模型成本任务。（1）前端把内联在 `main.tsx` 的错误码表抽为 `frontend/src/errorText.ts` 并补全 RUN_NOT_READY 等 16 类码，未映射带码响应统一中文兜底、不再回显服务端英文原文；`AgentPanel.tsx` run 级失败展示统一走 `errorText`。后端零改动（磁盘 67 个 `.py` 与已验收 API 镜像逐文件 sha256 全匹配），英文契约文案原样保留。（2）新镜像 `solomeal-web:errtext-0917`（ID b5395f6b16f6）+ API p9-boundaries-0917，复用第85节 `solomeal-combined-0917`（18082，compose 叠加文件仅覆盖 web 镜像），真实 Nginx 桶页面场景通过：一次性空账号 150 请求→104×200/46×429、`Retry-After:60` 由 Nginx 本体返回、页面中文「请求较频繁…约 60 秒」并手动刷新恢复；`deployed-error-localization.mjs` 验证线上 bundle 含码表、全 run 逐一 advance 全 409 且原文逐字节一致、failed run 页面中文渲染。离线 `npm test` 35 通过（+6）、`npm run build` 通过、`npm run e2e` fixture 18 全过。模型新增 0、累计聊天 1685/视觉 30。源 18080 未触碰健康、未部署本轮前端；18082 验收后 stop 卷保留。P5/P8/P9 整体及旧 48/60 保持，无提交推送。见 docs/validation/error-localization-0917.md。

下一步按优先级：

1. 发布准备（清单 E 节第 3 步）：整理提交、跑远程 CI、冻结源码哈希与镜像 digest——解锁 P1-04 与 P9-04 剩余条件。**须用户授权提交推送**，动 git 前逐样检查内容、勿提交私有 env/凭据/证据目录。第91～94节复核修正与真实堆栈补验均已收口，无其他前置。
2. 可选小改动：源 18080 是否重部署新前端（现线上验证版本为 `review-fixes-0917`，即 `index-BTAvzu0t.js`；源 18080 仍是旧包，仅动 web），待用户决定；UI **即时**显示 409 本地化串的真实断线路径可在下次模型 weaknet 演练顺带补测。
3. 需授权/需资源，先给有界估算再由用户决定：独立人工清晰度包与新小票留出、新源码完整留出复验、新物理主机部署、主机断电与 MySQL 数据盘写满。

保留原样不改写：合成留出 Agent 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null、旧各批失败与超时样本、未提交推送；后续修复与小批诊断属已暴露回归，不冒充新盲测、不改旧分数。旧私有目录与各模型批次禁止重跑或追加，第82节五项真机反馈不重复索取，源 18080 用户试用环境不作故障目标。

环境与保护：18082 项目现含 2 个空的演示外洪泛账号（第91节 `ratelimit429941349`、第94节 `ratelimit429469801`），记入证据 scope；证据与凭据在私有 `D:/SoloMeal-Acceptance/p9-combined-0917-01/demo-evidence/`（含 credentials.json、deployed-429-*、deployed-errtext-* 与 review-fixes-0917-* 的 JSON/PNG），禁止打印或提交、禁止重跑。第94节以 `combined-429-v2.override.yaml`（web=solomeal-web:review-fixes-0917）启动后已 stop、卷保留；不带叠加文件启动会回到 p9-boundaries-0917。`verify_deployment.py` auth-flood 会耗尽登录配额须最后跑，且本项目今日已多次消耗配额需等回滚。演练项目卷不 down -v。

以下为历史快照。

# SoloMeal 接手（2026-09-17，最终验收清单与状态表收口）

2026-09-17第90节：仅文档。新增 docs/validation/final-acceptance-checklist-0917.md（按「已收口／部分完成／未通过／已移出范围」四类收口第1～89节成果，含逐行证据链接、对外表述红线、建议收口顺序），并把 SOLOMEAL_STATUS 第3、4节两张表按实际证据改写：P9 阶段 TODO→IN_PROGRESS，P6-01/03、P8-01/02、P9-01/02/03 标 DONE 并注明报告，P8-03 TODO→IN_PROGRESS；起步动作与「未做」快照里已被后续章节推翻的旧描述一并更正。本轮未重跑测试、未调用模型、未改应用代码或部署、无提交推送；18080 的 web/api/db 三容器只读复查仍 healthy。

下一步按优先级（前两项零模型成本，可直接做）：

1. 409「Run is not ready to advance」等服务端错误原文本地化（第89节 2b 唯一已知 UI 缺陷）。
2. 补一条真实 Nginx 限流堆栈下的浏览器 429 页面场景（第84节仅有拦截夹具、第85节列为未覆盖）。
3. 发布准备：整理提交、跑远程 CI、冻结源码哈希与镜像 digest——解锁 P1-04 与 P9-04 的剩余条件。
4. 需授权/需资源，先给有界估算再由用户决定：独立人工清晰度包与新小票留出、新源码完整留出复验、新物理主机部署、主机断电与 MySQL 数据盘写满。

保留原样不改写：合成留出 Agent 48/60＝80%、`holdout_gate=failed`、独立人工清晰度 null、旧各批失败与超时样本；后续修复与小批诊断属已暴露回归，不冒充新盲测、不改旧分数。旧私有目录与各模型批次禁止重跑或追加，第82节五项真机反馈不重复索取，源 18080 用户试用环境不作故障目标。

以下为历史快照。

# SoloMeal 接手（2026-09-17，浏览器UI层真实Agent断线恢复实测完成）

本次进度复核：用户再次明确取消三分钟视频录制，已同步PLAN与交付手册，不再安排录制。当前最新实施证据仍为第89节；STATUS下方旧阶段表存在过时描述（如P9 TODO、真实对照/试用待做），不能据此忽略第70～89节实际成果。本次只读核对Docker，18080的web/api/db均healthy，仅这三个容器运行；未重跑测试或模型，未修改应用与部署，无提交推送。

2026-09-17第89节：补第88节保留项，在真实模型环境（solomeal-agent-weaknet-0917，18085，前置代理18086/控制18087）把断线驱动方换成真实浏览器页面（AgentPanel+sse.ts）实测通过。5个新run各恰好2步：基线完成；单条advance被杀时Chrome在连接层透明重试，UI完全无感；连杀两条后被杀advance仍持租约，应用收到409并在告警区显示服务端英文原文「Run is not ready to advance」（未本地化），未受影响的SSE流与焦点同步仍自动把面板刷到「已完成 · 已执行 2 轮」，无需用户点击恢复；SSE流300ms被杀后sse.ts自动重连并携Last-Event-ID游标续收，状态单调推进至已完成（steps=2/event_seq=5/1次recommend_meal）。库存始终300.000g、事件恰1条、用餐0条，五run零业务写入无重复。模型请求10次（估算6～12内、上限16），累计聊天1675→1685/视觉30，token约5.9万～6.2万（估计），墙钟约38分钟。演练中定位并修复deploy/weaknet_proxy.py测试工具缺陷（每客户端连接仅建一次上游、不查at_eof()，nginx默认75秒空闲关闭后请求静默丢失，表现为浏览器POST永久挂起），改为逐请求透明重连，默认故障注入语义不变故第87/88节证据不受影响，80秒空闲复现修复前无响应/修复后200，两文件ruff通过。源18080未触碰健康；演示18082按用户决定stop卷保留（录制已取消）；演练项目收尾stop卷保留。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-agent-ui-weaknet-0917.md。

下一步：剩余另列项均须先给有界估算由用户决定再执行——主机断电、MySQL数据盘写满、新物理主机验收。UI层已知但未修的观察可作候选小改动：409 RUN_NOT_READY等服务端错误原文未本地化（第89节2b）；`failed`后人工「恢复执行」（/retry）、多标签并发与长离线仍未实测。不重跑或追加旧模型批次与已收尾私有目录，不重复索取第82节五项真机反馈。源18080用户试用环境不作故障目标。

私有D:/SoloMeal-Acceptance/p9-agent-ui-weaknet-0917-01/ui/（第89节，含token.json凭据，禁止打印或提交，禁止重跑或追加）、D:/SoloMeal-Acceptance/p9-agent-weaknet-0917-01（第88节，含agent.env、drill-account.json）；演练项目卷不删除、不down -v，不用时stop。旧p9-combined-0917-01规则继续有效：verify_deployment.py的auth-flood模式会耗尽登录配额须最后跑。

以下为历史快照。

# SoloMeal 接手（2026-09-17，真实Agent断线演练完成）

2026-09-17第88节：真实Agent（模型开启）断线演练通过。独立项目solomeal-agent-weaknet-0917（18085，镜像p9-boundaries-0917，DashScope qwen3.8-flash/json/thinking=false/3000）前置weaknet代理（18086/控制18087），最终批三场景一次通过：基线两步推荐；advance在服务端处理完成后断连、重读run恢复继续推进、每run恰2步无重复模型请求或写入；SSE流中途断连后携游标重连收到全部缺失帧无重复帧。业务零写入（300g/0餐/仅1条种子事件）。最终批6次模型请求/19.611秒（硬上限16次内，含调试累计12次模型尝试）。代理加法新增kill_mode="stream"（默认行为不变），新增驱动deploy/agent_weaknet.py，均ruff通过。累计模型请求按服务端尝试口径更新为聊天1675/视觉30（token未逐请求留证，估计约3.5万～4.4万）。源18080与演示18082全程健康未动，演练项目已stop卷保留。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-agent-weaknet-0917.md。

下一步：剩余另列项均须先给有界估算由用户决定再执行——主机断电、MySQL数据盘写满、新物理主机验收；三分钟演示录制由用户择机执行（预演就绪状态见第86节）。浏览器UI层Agent断线恢复未实测（本轮为API/SSE客户端语义验证），可作为后续补充项。不重跑或追加旧模型批次，不重复索取第82节五项真机反馈。源18080用户试用环境不作故障目标。

私有D:/SoloMeal-Acceptance/p9-agent-weaknet-0917-01含agent.env、drill-account.json、drill-final与drill-1..4过程证据（凭据禁止打印或提交）；演练项目卷不删除、不down -v。演示项目18082与其代理18083/18084保持运行供录制。旧p9-combined-0917-01规则继续有效：verify_deployment.py的auth-flood模式会耗尽登录配额须最后跑。

以下为历史快照。

# SoloMeal 接手（2026-09-17，受控弱网验收完成）

2026-09-17第87节：受控弱网验收通过。deploy/weaknet_proxy.py（18083→18082，控制18084）动态延迟+按HTTP/1.1逐请求断连，ruff通过。API实测300ms注入0.620～0.629s；做饭/撤销服务端处理后断连、同幂等键重试同一记录，库存220/300克、事件1/0只应用一次。浏览器三场景通过：断连显示「无法连接服务器，请检查网络后重试」、清除布防恢复、刷新后重新登录数据完整。模型新增0、累计1663/30；演示项目18082与代理保持运行，源18080未动。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-weaknet-0917.md。

下一步：真实Agent断线（模型开启）须先给有界估算（请求/token/墙钟，标注为估计）由用户决定再执行；主机断电、MySQL数据盘写满、新物理主机验收另列；三分钟录制用户本轮已取消。源18080用户试用环境不作为故障目标，不重跑或追加旧模型批次，不重复索取第82节五项真机反馈。

私有D:/SoloMeal-Acceptance/p9-combined-0917-01含env、credentials.json、预演截图与弱网证据（weaknet/），禁止打印或提交凭据；项目卷不删除、不down -v，不用时stop即可。verify_deployment.py的auth-flood模式会耗尽登录配额须最后跑；代理控制端口18084的POST /config可随时改延迟与布防、GET /stats看逐请求事件。

以下为历史快照。

# SoloMeal 接手（2026-09-17，三分钟演示预演完成）

2026-09-17第86节：按docs/delivery.md七段脚本在solomeal-combined-0917（18082）真实浏览器预演一次通过。预演前补传1像素合成小票保留为未确认草稿；登录/库存、推荐（覆盖100%）、预览后确认做饭（300→220克）、撤销刷新恢复（300克/0餐）、小票草稿逐行单位错误提示与改正保存（草稿版本3）、助手模型关闭历史六段页面操作全部符合脚本，第七段讲解口径已核对。预演后API核对：大米300克/鸡蛋2个、小票1完成1草稿、用餐2条均撤销、Agent 1条模型未配置失败。第1～3段截图成功（私有目录rehearsal-*.png），第4～6段IDE视口隐藏以结构快照文字留证。模型新增0、累计1663/30；项目保持运行供录制，源18080未动健康。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/demo-rehearsal-0917.md。

下一步：用户择机录制三分钟演示（预演未计时口播，录制须核对时长与失败画面口径；当前状态可直接开录，做饭/撤销可重复演示，草稿行可删除重录单位错误段）。随后推进受控弱网/真实Agent断线；新物理主机、主机断电与MySQL数据盘写满另列未验收，P8旧门槛不得改写。源18080用户试用环境不作为故障目标，不重跑或追加旧模型批次，不重复索取第82节五项真机反馈。

私有D:/SoloMeal-Acceptance/p9-combined-0917-01含env、credentials.json、预演截图与状态证据，禁止打印或提交凭据；项目卷不删除、不down -v，不用时stop即可。verify_deployment.py的auth-flood模式会耗尽登录配额须最后跑；草稿小票幂等键demo-draft-receipt-01重传不重复。

以下为历史快照。

# SoloMeal 接手（2026-09-17，P9合并部署验收完成）

2026-09-17第85节：新独立Compose项目solomeal-combined-0917（127.0.0.1:18082）整体验证p9-boundaries-0917的web/api组合通过。迁移退出0、四容器健康；demo seed/verify业务闭环与幂等重放通过；模型关闭降级API与页面可见；205批次默认页100、分批读全205、4组非法分页参数422；真实Nginx普通桶150请求31次429（Retry-After:60+RATE_LIMITED）、健康检查豁免、6秒恢复，模型桶40次31次429，认证桶20次10次429；真实浏览器登录/库存/助手关闭状态冒烟通过（视口隐藏无法截图，以结构快照文字留证）。新增deploy/verify_deployment.py（ruff通过）。模型新增0、累计1663/30；源18080未动且健康，新项目已stop卷保留。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-combined-0917.md。

下一步按docs/delivery.md预演三分钟演示（可重启solomeal-combined-0917或新起演示项目，预演后确认库存再录制），随后推进受控弱网/真实Agent断线；新物理主机、主机断电与MySQL数据盘写满另列未验收，P8旧门槛不得改写。源18080用户试用环境不作为故障目标，不重跑或追加旧模型批次，不重复索取第82节五项真机反馈。

私有D:/SoloMeal-Acceptance/p9-combined-0917-01含env、credentials.json与全部证据，禁止打印或提交凭据；项目卷不删除、不down -v。第二次demo verify业务断言全过、仅证据文件按"x"设计拒覆盖退出非零，非业务失败。镜像solomeal-api/web:p9-boundaries-0917保留，verify_deployment.py的auth-flood模式会耗尽登录配额须最后跑。

以下为历史快照。

# SoloMeal 接手（2026-09-17，P9请求边界与交付材料）

2026-09-17第84节：Nginx分组限流/429反馈、12类REST列表SQL分页与前端完整分批读取、容器thinking/预算/视觉额度配置已实现。后端530通过/16 MySQL跳过，Linux重叠子集58通过，前端29测试/构建及9浏览器场景通过；独立Nginx实际限流与禁网容器配置通过。三分钟演示脚本/技术问答/新主机清单已备，未录制或新机验收。源码c3161b9b…（67文件），模型新增0、累计1663/30。源18080健康且未重部署，P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-boundaries-0917.md。

下一步先按PLAN P9在新独立Compose项目整体验证新web/api组合（本轮API禁网配置、Nginx合成与页面夹具分别通过，尚未合并部署验收），再按docs/delivery.md预演/录制三分钟演示并推进受控弱网/真实Agent断线。新物理主机、主机断电和MySQL数据盘写满另列未验收，P8旧门槛不得改写。源18080用户试用环境不作为故障目标，不重跑或追加旧模型批次，不重复索取第82节五项真机反馈。

独立镜像solomeal-api:p9-boundaries-0917已构建；限流临时容器已清理，源solomeal-acceptance-0916a三容器最终健康，原恢复/故障/开发未启动、卷保留。未重部署源，因此用户现有页面暂未使用本轮代码。生产边界细节见deploy/README.md：分页默认100/最大200，前端仍全量分批读取（上限10000），嵌套历史/大候选未全面限制；thinking用omit省略，显式空值报错。首次失败与两个容器验证目录均保留。

以下为历史快照。

# SoloMeal 接手（2026-09-17，P9恢复故障演练完成）

2026-09-17第83节：P9备份故障保护与恢复演练完成。manifest改临时文件写入/flush/fsync后发布，停止服务纳入finally保护，缺schema恢复前拒绝。22保护测试Windows/Linux各过（同组）；真实1MiB tmpfs三路ENOSPC及独立MySQL部分导入/重试拒绝通过。新故障项目已停且卷保留，源18080健康，原恢复/开发仍停。模型新增0、累计1663/30，P5/P8/P9整体及旧48/60保持，无提交推送。下一步生产限流/分页、容器模型配置边界与交付材料；主机断电/MySQL数据盘写满尚未演练。见docs/validation/p9-fault-0917.md。

下一步按PLAN P9继续生产请求限流/分页与容器内模型配置边界，先核对现有API/前端契约和配置，再实现并验证；随后完善P9-03三分钟演示、技术问答和新主机交付清单。P9依赖P8，整体仍未完成。受控弱网/真实Agent断线、主机断电和MySQL数据盘写满另列未验收；不重复索取第82节五项真机反馈，不重跑旧模型批次。

本轮合成证据docs/validation/p9-fault-0917/，新项目solomeal-fault-68a00c4361e1已stop、卷保留；target.json仅记录随机私有env路径，不含凭据。该失败目标禁止再次restore，不删除卷；要扩展故障需新项目。源18080末次检查健康，原恢复18081及开发库仍停。部署管理器为宿主机工具，无需为本轮修改重部署源服务。

以下为历史快照。

# SoloMeal 接手（2026-09-17，安卓真人试用反馈已收录）

2026-09-17第82节：已核对用户填写的android-trial-form.json，PKX110/Android16/OnePlus浏览器五项真机检查全部报告通过，四个清晰度样本均5分（均值5.0），下一步理解均true，issues为空。作为单人补充试用结果记录；此前小票缺陷及修复留证保留。具体断网方式、时延/丢包参数未记录，不推断受控弱网或真实Agent断线已验收；P8全量人工门槛/旧48/60及P5/P8/P9整体未完成保持。模型新增0、累计1663/30，无代码或部署变更、无提交推送。

下一步回到P9恢复失败/磁盘不足演练、生产边界及交付材料。用户已完成本次表内试用，无须重复索取这五项结果；受控延迟/丢包及真实Agent断线另列，不从布尔结果推断。源18080保留，恢复18081仍以先前停止记录为准；本轮未检查容器。旧模型批次不得重跑/追加。

以下为历史快照。

# SoloMeal 接手（2026-09-17，小票确认反馈修复）

2026-09-17第81节：安卓小票确认无反馈定位为第1项个数与食材克单位冲突（HTTP422），原错误仅在长页顶部。新增逐行单位/整数校验、当前小票操作区错误反馈和入库中状态；24前端测试/构建/3小票浏览器测试通过。新版前端已部署到源18080且健康，只更新web。真实小票只读诊断，未代改或代确认；模型新增0，累计1663/30，后端未改。P5/P8/P9整体与旧48/60保持，未提交推送。见docs/validation/receipt-feedback-0917.md。

下一步：用户刷新后核对小票对应食材及实际数量，再保存确认；不代改单位或代确认。已用安卓进入网站并发现此问题，但修复后真机复验、弱网/清晰度评分仍待完成。之后回到第80节P9剩余任务；旧模型批次不重跑/追加。

以下为历史快照。

# SoloMeal 接手（2026-09-16，本地部署与联合恢复通过）

2026-09-16第80节：P9本地Compose空环境启动、模型关闭降级和真实MySQL/私有小票联合备份恢复通过；21表摘要及图片字节一致，幂等重放不重复写。12保护测试Windows/Linux各过（同组），源/恢复两次窄屏浏览器通过；安卓试用材料已备，真人评分/真机仍null。新增模型0，累计1663/30；源码a602c174…66文件。源solomeal-acceptance-0916a在127.0.0.1:18080健康，恢复b已停且卷保留，开发库未动。P9整体/P5/P8未完成、旧48/60保留，无提交推送。见deploy/README.md及docs/validation/deployment-restore-0916.md。

最新报告：[部署恢复](docs/validation/deployment-restore-0916.md)。私有D:/SoloMeal-Acceptance/p9-deployment-0916-01含随机env、demo/credentials.json、备份与证据，禁止打印或提交凭据。源项目18080保持运行供试用；恢复项目18081已停，卷不删除。原solomeal-dev-mysql仍停止，MySQL80未动。

下一步：用户选择安卓手机，按docs/android-trial.md连接实际设备；四轮清晰度材料及android-trial-form.json已准备，真实评分和网络操作必须由参与者执行，当前全null。可独立继续P9恢复失败/磁盘不足演练、生产限流/分页、容器内模型配置边界和三分钟演示/新主机交付，P9不标整体完成。现有部署与备份命令见deploy/README.md；不对既有卷执行down -v，不覆盖开发库。P8旧留出48/60及holdout_gate=failed不变，无新模型批次待跑。

以下第79节及更早为历史快照。

# SoloMeal 接手（2026-09-16，推荐响应真实四轮诊断完成）

2026-09-16第79节：推荐响应四轮真实诊断完成，客观4/4、模型原文语义4/4、产品展示语义4/4；后续模型历史含服务端正文，非纯模型提升或新盲测。新增8请求/49142token，累计聊天1663/视觉30；三哈希全匹配、Agent业务DML0，驱动单独授权补1蛋。13离线测试/ruff通过，源码a722eab4…；旧48/60、真人清晰度null及P5/P8未完成保留，无提交推送。两个p8-recommendation-response私有执行/审计目录已完成，禁止重跑或追加试次。下一步真人清晰度/试用、真机弱网及P9部署备份恢复，见docs/validation/recommendation-diagnostic-0916.md。

最新证据：[四轮真实诊断](docs/validation/recommendation-diagnostic-0916.md)及同名JSON。批次D:/SoloMeal-Acceptance/p8-recommendation-response-0916-01与独立审计p8-recommendation-response-audit-0916-01已收尾，不重跑、不追加。当前生产SYSTEM/tools未改，新源码差异来自独立诊断驱动。没有新模型批次待执行。

下一步先准备真人清晰度/同学试用材料，实际评分须由真实参与者填写；真实设备弱网仍未测。同步推进不依赖人类评分的P9部署/演示及数据库与私有上传联合备份恢复，先检查现有部署文件、端口、Docker和专用MySQL隔离，不使用MySQL80，不覆盖开发库。P8/P5和P9整体完成仍按PLAN原门槛，原留出48/60不改。提交推送无授权；既有持续模型调用授权保留，但无意义重复禁止。

以下第78节及更早为历史快照。

# SoloMeal 接手（2026-09-16，推荐后续动作离线修复）

2026-09-16第78节：推荐后续动作一致性离线修复完成；成功recommend_meal后的最终展示改由服务端按当前候选生成，逐菜限制做饭预览建议，原模型文字单独留证。后端149不同用例通过/1 MySQL跳过，前端21测试/构建/1新增脚本浏览器通过，ruff通过。模型新增0、累计聊天1655/视觉30；源码36a57a39…（64文件），旧48/60及P5/P8未完成保留，无提交推送。仅覆盖推荐出口，非真实模型语义提升；下一步新目录登记4 run最多32请求并分别评审模型原文/产品展示，见docs/validation/recommendation-response-0916.md。

最新报告：[推荐响应边界](docs/validation/recommendation-response-0916.md)。下一步先适配真实诊断驱动，model_message与message分开留证和评分，冻结夹具/协议与前后端哈希，再在新私有目录登记三轮加补库存重新查询共4 run；预算估计8–12请求/5万–9万token/1–3分钟模型耗时，上限32请求、不重试。尚未登记或执行，持续调用授权有效。所有既有已执行目录不重跑、不追加。随后真人清晰度/试用、真机弱网和P9。

以下第77节及更早为历史快照。

# SoloMeal 接手（2026-09-16，真实恢复/页面闭环与历史展示修复）

2026-09-16第77节完成：受控报价字段拒绝后的真实模型恢复通过；真实页面入库/做饭/撤销与刷新恢复通过（大米300→400→320→400g）。修复页面将内部历史JSON显示为用户正文的问题；前端20测试/构建、脚本模型三轮浏览器回归通过，后端22通过/1 MySQL跳过，Python入口ruff通过。

首批三轮原objective=false是驱动误把会话导航元数据计入旧run不可变，原失败保留；修正驱动后新三轮结构与旧run内容不变通过，但第三轮回答正确说缺1鸡蛋又建议生成做饭预览，**语义失败保留**。本轮20真实请求/118680token/模型耗时累计60.49秒；累计聊天1655/视觉30。20输入三哈希匹配，后端源码仍1d129290…，SYSTEM/tools/七冻结JSON不变；前端及诊断入口改动，无提交推送。额度中断恢复后核对收尾新增外发0。

证据：docs/validation/real-agent-0916.md及同名JSON；私有D:/SoloMeal-Acceptance/p8-real-agent-0916-01、p6-real-ui-0916-01、p8-real-multi-0916-02均已执行，**不得重跑或追加试次**；real-agent-audit-0916-01保存审计与全部证据哈希。页面最终快照undo-approved.json已在关闭前保存，服务Ctrl+C退出1未生成finally的after.json/runs.json，两临时服务进程已停止。v1驱动归档哈希与登记一致。原v19/v20/v21及purchase-contract-v2批次禁重跑规则继续有效。

下一步：先离线分析新三轮回答“库存不足却建议做饭预览”的通用一致性缺口，考虑让当前工具可执行状态约束后续动作展示/执行，不只堆提示或反复实测；完成离线验证后，再冻结新变更与有界预算。之后真人清晰度/试用、真实设备弱网及P9部署/备份恢复。原留出48/60、holdout_gate=failed、真人清晰度null、P5/P8未完成不变。P3引用第76节MySQL工程60/60通过，容器运行状态需使用前检查，仍不得改用MySQL80。

以下第76节及更早“下一步”均为历史快照。

2026-09-15第76节完成：昨日MySQL全量中断（334个通过标记、1 F/7 E，无JUnit/最终退出码）原样保留。今日新诊断复现MySQL JSON键顺序变化导致第三轮历史摘要重复嵌套，已改为结构比较。4纯函数反例通过；相关套件25通过，工程77实例通过/0跳过（16个MySQL专属竞争实例），冻结工程60/60、engineering_gate=passed；P3-04/P3完成。开发库前后及与昨日摘要一致，测试库仅余空迁移表，全部测试进程已结束。见docs/validation/mysql-pages-0915.md与mysql-{diagnostic,regression,engineering}-0915目录，原失败不覆盖。

昨日页面：16前端测试、构建、13既有浏览器场景及2新增场景最终通过；新增lifecycle与planning-boundaries覆盖归档恢复/菜谱编辑/版本取消、无候选/未知预算/旧方案拒绝。生命周期开发过程两次测试流程失败已修正。今天未重跑页面，均为临时SQLite/脚本模型，非真机。25与77套件有重叠，未重跑全497后端测试。当前源码1d129290b62f21d1fd6831dfcf3eb53e1b962f2f2fa47f9aa6e0e00248ddd50d（63文件），SYSTEM/tools未改，无模型调用，累计聊天1635/视觉30，无提交推送；原48/60、holdout_gate=failed、真人清晰度null及P8/P5未完成保留。

下一步：按新源码先给有界预算并登记独立真实多轮/报价字段拒绝后恢复诊断及真实模型页面闭环，补P5/P6实际模型证据；然后真人清晰度/试用与P9剩余范围。授权按PLAN持续条款，仍须新目录、输入哈希和失败留证，不重跑旧v19/v20/v21及purchase-contract-v2目录，不把回归冒充新盲测。MySQL专用容器已恢复并保持运行；不得改用MySQL80。下文第75节为历史。

2026-09-14第75节：独立purchase-contract-v2协议、三模式驱动与证据绑定评审完成；口述190g缺口与明确三份白米饭两个新场景各三模式一次，本批全部通过（非新盲测）。70离线测试/ruff通过；真实8请求/39326token/约34.48秒，累计聊天1635、视觉30，8输入三哈希匹配、业务DML0。源码34cc3880…，生产SYSTEM/tools/direct-v1及七冻结JSON未变；原A026失败、留出48/60、holdout_gate=failed、真人清晰度null及P8/P5未完成保留，无提交推送。详见docs/validation/p8-purchase-contract-v2-0914.md。

私有D:/SoloMeal-Acceptance/p8-purchase-contract-v2-0914-01已执行审计评审完毕，不得重跑或追加试次，旧v19/v20/v21目录同样保留。下一步回到PLAN P3-04/P8真实MySQL验收：先核对专用测试库配置、服务可用性与脚本隔离边界，再执行MySQL用例并留证；随后补P4～P6页面验收。A035慢尾根因、报价拒绝后真实恢复、真人清晰度与P9等缺口保留。

下文第74节及更早内容为历史快照。

2026-09-14第74节：A026题干/工具/评分契约离线核对完成。冻结文字oracle仅要求2包/200g/6元，servings=3及三候选等额外条件来自执行器；固定流程直接注入三份。隔离复现默认1份为缺30g/3元、指定3份为缺190g/6元，口述缺口estimate_purchase无需份数即正确。16相关回归及审计脚本ruff通过，源码1b7be0dd…与七冻结JSON未变，新增模型请求0、累计1627。原失败、留出48/60、holdout_gate=failed及P8/P5未完成保留。详见docs/validation/p8-a026-contract-0914.md。

下一步按报告草案实现独立purchase-contract-v2协议加载、三模式驱动与离线反例，明确区分口述缺口与三份菜谱规划；之后再冻结协议/配置/哈希、估算有界真实诊断并确定新批次。草案尚未冻结/登记/执行，不改v1判据或旧分数，所有既有私有批次禁止重跑/追加。无提交推送。

下文第73节及更早内容为历史快照。

2026-09-14第73节：先修正查询观测为evaluation-measurements-v3的missing_required_query/missing（不推断是否作答），cohort-metrics-v6继续非门槛。A035两轮，因此四场景最多5 run/40请求。新批次三项已暴露回归A026/A027/A035为2通过1失败，独立采购新形状1通过；164离线回归/ruff通过。12请求、69601token、47.58秒，无超时/缺usage/业务写入，累计已知聊天请求1627、视觉30。原留出48/60、holdout_gate=failed、P8/P5未完成不变。

当前源码`1b7be0ddc4889def69f19edd8f7cf74d1d7e0143aec6ed0cf9abaf35a5e4c4e6`；SYSTEM/tools与第72节一致。私有`D:/SoloMeal-Acceptance/p8-purchase-v21-diagnostic-0914-01`已完成登记/执行/审计/评审，12输入三哈希匹配，禁止重跑或追加试次。详见[报告](docs/validation/p8-purchase-v21-diagnostic-0914.md)、同名JSON及预登记protocol JSON。

A026本次查ID并用estimate_purchase正确完成190g→2包/200g/6元，来源日期真实；但没有原oracle要求的recommend_meal/servings=3，冻结失败保留，不能说其完全没查。A027先查过期报价再回答，A035两轮数据忠实且本次无超时，新形状独立通过。下一步先离线整理A026题干、工具能力和冻结oracle关系，未来修订另订版本协议；不猜份数凑分、不回填历史分数。报价字段被拒后的真实恢复路径本批未触发，仍只有离线证据；MySQL、完整P4～P6验收、真人清晰度/试用、P9部署等未完成。下文第72节及更早的“下一步/未登记”为历史快照。

2026-09-14第72节：把第71节三项离线问题落到工程边界——Agent侧`recommend_meal`/`propose_plan`/`run.constraints`取消模型可书写的`quotes`（价格来源与日期只取服务端保存报价，提交即`extra_forbidden`/`unknown_field`且不回显、不给ID恢复），新增第9项只读工具`estimate_purchase`按用户说出的缺口算整包支出（不猜份数、不关联菜谱、不预留库存），评测层加`required_query`观测量把A027"没查就答"与"查了答错"分开（非门槛，旧分数不变），A035只读既有证据判定为慢尾且根因未知。全量430通过/16 MySQL跳过、子集306通过/5跳过、改动文件ruff通过；本轮0模型请求、0重跑、无提交推送。v19留出48/60、`holdout_gate=failed`、v20六通过三失败、真人清晰度全null全部保留，P8/P5未完成。详见docs/validation/p8-purchase-v21-0914.md及同名JSON。

当前源码`1674f8313e0cad9bd81598a2acdd1182c6b56b58b90c23be54eca9e25126473e`（Agent v21/direct-v1/json-tools-v2），白名单8→9项且两处description改变，`tools_sha256 79ff5a75…`、`system_sha256 a9d52adb…`；累计已知聊天请求仍1615、视觉30。七份冻结evaluation JSON哈希与v20登记逐文件一致。

下一步：先按既有批次实测给出请求/token/墙钟估算并明确标注为估计值、由用户决定是否执行，再在新私有目录登记小规模v21真实诊断（建议已暴露的A026/A027/A035各一次，另加一条`estimate_purchase`新形状；`estimate_purchase`不在冻结40场景覆盖内，需另记协议）。不得重跑或向v20九个私有目录、v19/v20 manifest追加，失败不回填，已暴露场景回归不冒充新盲测，原留出48/60不变。A026冻结判据仍要求猜测的`servings==3`，本轮未改判据也未宣称其已修好。

2026-09-14第71节：v20补通用ID查询/结构化只读恢复反馈及澄清、报价查询规则；194回归通过/1 MySQL跳过、ruff通过。9个已暴露场景诊断6通过3失败（A026编造报价日期、A027不查询、A035首轮回答超时），原失败保留。新增17请求/已观察94749token/1缺usage，累计1615；17输入三哈希匹配，源码33816f7d…；P8/P5未完成。

私有登记D:/SoloMeal-Acceptance/p8-recovery-v20-0914-registration.json；p8-{A008,A014,A026,A027,A029,A034,A035,A037,A039}-recovery-v20-0914-01全部已执行、审计与评审。该批Agent v20/direct-v1/json-tools-v2，源码33816f7d200409e991502829bc6a545241688ab331679935beac5cea0a77f8ad。A035第二轮未执行，语义缺失保留；无新完整cohort登记。下文均为历史快照，以第72节为准。


2026-09-14第70节：v19合成留出180位置执行、审计、评审与聚合完成；Agent48/60（80%，未达85%）、固定60/60、直接26/42适用另18不适用。12个Agent失败全部保留，171退出码0/9退出码1。185请求/795947token，累计1598；恢复新增0，输入三哈希全匹配，源码7f8ab812…未变。holdout_gate=failed，真人清晰度null，P8/P5未完成。

下一步先离线修复通用查询/ID获取与错误恢复、澄清完整性、基于实际结果的后续建议；不能向旧manifest追加或重跑。源码变更后另登记有界诊断，原留出失败保留，修复后复验属于已暴露场景回归，不冒充新的盲测。

2026-09-14第69节：昨天v19统一debug 180位置已完成，恢复后离线审计评审聚合完成，新增外发0。Agent58/60、固定60/60、直接17/42适用另18不适用；A008-01漏问净含量、A014-01错误后续建议保留。190请求/833620token，累计1413；输入三哈希全匹配，180退出码均0，源码7f8ab812…不变。P8/P5未完成。

下文带日期旧段为历史，当前以第69～70节为准。

运行登记（2026-09-13）：v19新源码debug 180位置已登记，即将执行；私有D:/SoloMeal-Acceptance/p8-cohort-v19-debug-0913-01，manifest 641651095ff1fc75227eb036718bef347919fb4aeeb4974bf429322f4bb398b2，源码7f8ab812…；中断后先查execution.jsonl、进程与audit-final.json，禁止重跑已登记manifest。留出尚未登记，先完成本批审计评审。

2026-09-13第68节：第67节三项离线问题已修复：恢复expiry/stale_quotes/注入文本冻结契约，metrics-v4将固定流程语义硬约束标不适用（客观判据保留），清晰度恢复mean≥4。222个不同回归用例通过、ruff通过，85%边界/完整成功/失败/缺失均有测试。源码7f8ab81290559aba68d70a2b8e672bcad78af6b6b2c413d4086292996915d79a；模型外发0/新登记0。下一步按新哈希登记调试统一重复，再合成留出；P8/P5未完成。

最新先读[修复报告](docs/validation/p8-holdout-fix-0913.md)。当前Agent v19/direct-v1/json-tools-v2未变，聚合器v4；完整调试与留出均未登记/执行。先新源码debug 180位置、approve仅A010～12，独立审计评审聚合后再holdout 180位置、approve仅A030/31/33，执行前冻结参考价格与配置。不得重跑或追加旧manifest。语义不适用不等于客观约束免检，固定流程任务及写入等门槛仍保留。下文第67节问题为修复前历史，详情和局限见本轮报告。

2026-09-13第67节：独立审阅第66节，源码2cdd1681…核对一致，评测子集205项复跑通过；发现留出expiry/stale_quotes夹具偏离冻结契约、固定流程空硬约束评分使holdout_gate不能通过、清晰度min与冻结mean不符。仅审阅未修代码，模型外发0/新登记0。下一步先修三项离线问题并回归，再按新哈希登记批次；P8/P5未完成。

先读[独立审阅](docs/validation/p8-holdout-review-0913.md)。本轮未执行新批次或删除旧临时脚本；下文第66节“可执行/下一步登记”为修正前历史结论，优先修复审阅问题。

2026-09-13第66节：留出A021～A040的登记/执行/审计/评审/聚合支持已按冻结标签与门槛补齐（`--split`必填、每split仍180位置、确认扩展分置debug A010～12与holdout A030/31/33、聚合升v3并按全分母判定留出）；顺带修复带保质期库存让`get_inventory`在工具边界`json.dumps`失败、被吞成MODEL_PROTOCOL_ERROR的真实缺陷（A021原先不可能达成，REST因jsonable_encoder被掩盖）。完整套件401通过/16 MySQL跳过（Docker未运行，未启动）、评测子集205通过、改动文件ruff通过。本轮模型外发0、新登记0；调试与留出统一重复均未登记/执行，留出85%门槛仍未测量，P8/P5未完成。

最新先读[本轮报告](docs/validation/p8-holdout-offline-0913.md)。当前Agent v19/direct-v1（工具schema、SYSTEM正文、json-tools-v2、业务权限均未变），HEAD仍a923d77c，源码由ec7c2770…改为2cdd1681d65bc714695268fe2af49006059358fe3056148ddc9c7ae1c3867ce1（60文件）。下一步：先按既有批次实测给出请求/token/墙钟估算并标注为估计值、由用户选择，再登记20调试三模式180位置统一重复（`--split debug`，approve仅A010～12）与20合成留出（`--split holdout`，approve仅A030/31/33），各自审计/评审/聚合；不得向v16/v13/v12私有目录追加或重跑，失败不回填。留出限制随结论同读：合成集已被实现方读过、A015/A035逐字两轮提示由harness拟定、清晰度按min≥4聚合（README原文为mean≥4，更严不假通过）、真人清晰度仍全null。下文第65节及更早为历史快照。

2026-09-13第65节：v19将短/长续聊历史统一归入文本摘录，仅本轮工具结果作为活动消息；三轮回归及A015三次独立真实复验通过，旧v18失败保留。相关98项最终通过/1 MySQL跳过（分组复验有重叠），ruff通过。新增12请求/70071token，累计1223。下一步先离线补留出登记/执行/评审/聚合全链路，再新源码统一调试与留出；本轮未启动完整重复，P8/P5未完成。

最新先读[本轮报告](docs/validation/p8-context-v19-0913.md)。当前Agent v19/direct-v1，源码ec7c27702426f689096b69d52b795ee734e59662f6b0f11068953532f10fbcaa。私有p8-A015-context-v19-0913-01～03已执行、审计、评审，禁止重跑；12份输入三哈希匹配，语义3/3仅为本次诊断，真人清晰度null。先实现cohort slots/register/load_plan、evaluate范围与split、review rubric及聚合的留出支持并补离线回归，保持冻结标签/门槛；随后按新源码哈希登记20调试三模式统一重复，再20合成留出。当前均未登记/执行，不向旧批次追加。下文第64节及更早为历史快照。

2026-09-13第64节：v16独立r2评审更正为Agent56/60、固定60/60、直接27/42适用另18不适用；退出码178个0/2个1。v17三类通用修复6/9、v18进一步修复8/9，A015-v18-02旧轮用量复用失败保留。106回归通过/1 MySQL跳过，最终22通过/1跳过、ruff通过。新增46请求/277153token，累计1211。下一步先离线处理多轮最新结果引用，再有界复验及留出全链路支持；不启动完整重复，P8/P5未完成。

最新先读[本轮报告](docs/validation/p8-intent-v18-0913.md)。当前Agent v18/direct-v1，源码9be243feb6d6927cdedb680bd121022cea64d559fcbc0848f640126d1ceaf2ac。v16-r2修订评分已在新目录生成；v17/v18诊断均完成且禁止重跑。A015-v18-02工具正确返回160g/2蛋，回答仍写80g/1蛋，先离线核对当前轮结果引用路径再修复/独立复验。新统一180位置和留出均未登记；下文第63节及更早为历史。

审查更新（2026-09-12）：[v16独立审查](docs/validation/p8-cohort-v16-review-0912.md)发现退出码全部0的表述错误（实际178个0/2个1），以及A006-agent_tools-02普通推荐被说成待确认预览却评分通过。原证据/评审不修改，修订评分尚未生成；应先在独立复核版本处理漏判并更新汇总，再继续后续开发。源码、191输入哈希、用量和原聚合已复核一致，本轮外发0。下文57/60为原评审结果。

2026-09-12第63节：v16完整180位置统一批次执行、离线审计/评审/聚合完成；Agent57/60、固定60/60、直接27/42适用另18不适用，合计144通过/18失败/18不适用。Agent三失败保留（A001-02数组信封、A009-01猜单位并留下待确认写入、A015-02份数表述），第62节修复的两类未复现，本批无30秒超时。191请求/818246已观察token，累计1165，墙钟22分41秒。禁止重跑manifest、失败不回填；下一步离线复核失败通用缺口后按新源码哈希登记，20留出需先扩展登记的split支持。P8/P5未完成。

最新先读[完整报告](docs/validation/p8-cohort-v16-0912.md)。私有D:/SoloMeal-Acceptance/p8-cohort-v16-0912-01，manifest 69da5efe7e3fd35d78699e01cb132ba38ba197add6f9559e989d33c4f0ef640d，已完成，禁止重跑或向该目录追加；源码仍21b2ba809c8b08cdcc71ff9d9a4f8beccf293cc8b55296c0ac2e2acb56e2091f，未改生产代码。以下第62节及更早为历史，其中“尚未登记/执行”只描述当时状态。

2026-09-12第62节：拒绝解释/净含量澄清修复，v14/v15各5/6且新推测失败保留；v16六独立真实复验全部通过。91回归通过/1 MySQL跳过，最终16通过/1跳过、ruff通过。新增27请求/139902token，累计974；v13同输入超时离线分析完成、根因未知。下一步新登记v16完整180位置统一重复，再20留出；P8/P5未完成。

历史入口：[修复与复验报告](docs/validation/p8-clarification-v16-0912.md)。当时源码21b2ba809c8b08cdcc71ff9d9a4f8beccf293cc8b55296c0ac2e2acb56e2091f，Agent v16/direct-v1/json-v2/thinking=false/3000/30秒，计划新登记完整180位置、approve仅A010～12可执行模式、其余none；该项已在第63节完成。旧v13完整manifest及v14～v16诊断均禁止重跑，失败不回填。

2026-09-12第61节：v13完整180位置及恢复离线审计/评审/聚合完成；Agent55/60、固定60/60、直接20/42适用另18不适用。三首请求超时、A004拒绝解释及A008净含量澄清失败保留；A014三次通过。188请求/758184已观察token，累计947，恢复新增0。禁止重跑manifest；下一步通用修复/独立复验，再统一重复与20留出。P8/P5未完成。

最新先读[完整报告](docs/validation/p8-cohort-v13-0912.md)。私有D:/SoloMeal-Acceptance/p8-cohort-v13-0912-01，manifest b4a32fe91c9ae8c4b23afe0625a535de4e61bd68e05bc8a88d95f66983cc6640，已完成，禁止重跑；源码仍8db7525ce63f06359d2f691bc6fe80ee6adc3c607a5e566279cb9833e7012790。下文“即将执行/未登记”均为历史。

运行更新：v13完整180位置已登记，即将执行。D:/SoloMeal-Acceptance/p8-cohort-v13-0912-01，manifest b4a32fe91c9ae8c4b23afe0625a535de4e61bd68e05bc8a88d95f66983cc6640。中断后先检查execution-0912.jsonl、后台及audit-final-0912.json，禁止重启已有manifest。见docs/validation/p8-cohort-v13-0912.md；下文“尚未登记”为历史。

2026-09-12第60节：v13后续操作能力边界修复及A014三独立真实复验通过；118回归通过/1 MySQL跳过、ruff通过。现有A013同输入延迟1.86/超时31.04/27.86秒，根因未知且旧失败保留。新增6请求/31208token，累计759。下一步新登记v13完整180位置统一重复，再20留出；P8/P5未完成。见STATUS第60节和docs/validation/p8-capability-v13-0912.md。

最新先读[修复报告](docs/validation/p8-capability-v13-0912.md)。v13源码8db7525ce63f06359d2f691bc6fe80ee6adc3c607a5e566279cb9833e7012790；新统一批次尚未登记/执行，旧v12 manifest禁止重跑。以下第59节及更早为历史。

2026-09-12第59节：v12完整180位置执行、离线审计/评审/聚合完成；Agent58/60、固定60/60、直接23/42适用另18不适用。A013-02超时及A014-02不支持的忽略忌口确认路径保留，硬约束59通过/1缺失。189请求，累计753；额度中止恢复新增0，禁止重跑该manifest。下一步修复不支持的后续路径并独立复验、分析超时，再统一重复/20留出；P8/P5未完成。见NEXT_SESSION与STATUS第59节。

先读[完整报告](docs/validation/p8-cohort-v12-0912.md)。私有目录D:/SoloMeal-Acceptance/p8-cohort-v12-0912-01，manifest 572e8227c15c13ee97767e541ec0261f4c32099115383215bfacf8ffcfc88ffc；180已于16:09完成，全部输入/评审/聚合已保存，不得再次执行。源码59e27b54ce6856fa0191cd7107e1fd1da78a712903c34025d2bfb9130a736c71仍为Agent v12/direct-v1。189请求（1超时无usage），已观察753251token；累计753已知聊天请求，另1历史关机未知尝试，视觉累计30。恢复后只做离线工作，新增请求0。

下一步先阅读A014-agent_tools-02实际回答，补通用能力边界规则及离线回归，再登记新目录有界复验；A013-agent_tools-02首请求超时保留，先分析现有延迟证据，不能重跑覆盖或当作语义通过。源码变更须新登记统一批次。20合成留出仍0、真人清晰度null，MySQL/P4～P6完整验收/新小票/真人试用/P9范围保留。以下第58节及更早文字均为历史快照，“启动/未登记”不代表当前状态。

当前运行更新：v12完整180位置已在D:/SoloMeal-Acceptance/p8-cohort-v12-0912-01登记并启动，manifest 572e8227c15c13ee97767e541ec0261f4c32099115383215bfacf8ffcfc88ffc。先核查execution-0912.jsonl、后台执行状态及audit-final-0912.json，禁止再次运行已有目录；详见docs/validation/p8-cohort-v12-0912.md。下文“未登记/未执行”为此前历史。

最新先读STATUS第58节及[v12报告](docs/validation/p8-constraints-v12-0912.md)。默认约束、比较、忌口解释已补通用提示，v11复验7通过2失败（A007多余确认/不查询），原始证据与评审保留。v12明确本轮条件直接提取、库存菜谱先工具查询，A004/A007/A014各3次全部客观/Codex语义通过，真人清晰度null。比较最值在此次回答未出现，不证明稳定比较能力。

当前Agent solomeal-agent-v12，源码59e27b54ce6856fa0191cd7107e1fd1da78a712903c34025d2bfb9130a736c71，direct-v1未改；json-v2/thinking=false/3000/30秒，不改.env。私有p8-{A004,A007,A014}-constraints-v12-0912-01～03，18请求/94586token；v11另16/79733，合计新增34、累计564已知聊天请求，另1历史关机无返回尝试、视觉累计30。34输入三哈希匹配，两版独立review/manifest/scores及仓库脱敏JSON已保存。

下一步：核对v12实际源码，另登记新完整180位置三模式统一重复（未登记、未执行），approve仅A010～12可执行模式、其余none；旧v4 manifest禁止重跑，不向旧批次追加。完成独立审计/评审/聚合后进入20合成留出；留出仍0，P8/P5未完成。166回归通过/1跳过，最终59复验通过/1跳过（包含重复），ruff通过。MySQL/完整P4～P6/新小票/真人清晰度与试用/P9范围不变。以下第57节及更早为历史，执行顺序以本段为准。

最新先读STATUS第57节及[完整v4报告](docs/validation/p8-cohort-v4-0912.md)。此前登记批次已于09-12 10:15完成全部180位置；额度中止后恢复核验完成，新增外发0，禁止重跑该批次。Agent56/60、固定60/60、直接26通过16失败/42适用另18不适用。四个Agent失败：A004-01擅改默认30分钟为60、A007-02错误最短耗时比较、A014-01/03错误忌口状态与拒绝原因解释。硬约束59/60未通过100%，真人清晰度null，留出0，P8/P5未完成。

私有D:/SoloMeal-Acceptance/p8-cohort-real-v4-0911-01，manifest仍e48d7cbe5acd3825614510750ff3a3c3263421aeb584e1f09168f7139e379839；audit-final与audit-recovery哈希完全相同。192聊天请求/731007token，输入三类哈希全匹配；累计530已知聊天请求，另1历史关机无返回尝试、视觉累计30。参考估计0.6413686元非账单。下一步修复四失败通用规则与离线回归→新目录有界复验→另登记完整统一重复→20合成留出；保持原配置预算，不改.env，失败不回填。下文第56节及更早数据为历史。

最新先读STATUS第56节及[直接模型报告](docs/validation/p8-direct-v1-0911.md)。direct-v1接入三个直接路径，cohort-v4冻结双提示并校验真实输入，旧v3可读；180专项/ruff通过。四诊断试次新增5请求：1通过/2失败/1不适用，失败保留；累计338已知聊天请求。全新D:/SoloMeal-Acceptance/p8-cohort-real-v4-0911-01已登记180位置，全部未启动；manifest e48d7cbe5acd3825614510750ff3a3c3263421aeb584e1f09168f7139e379839。下一步核对源码/配置、记录当日官方单价后执行该完整批次。Agent v10/direct-v1，3000/30秒/thinking=false，不改.env。留出仍0，P8/P5未完成。下文第55节及更早数据为历史。

最新先读STATUS第55节及[v10修复报告](docs/validation/p8-routing-v10-0911.md)。上一交接A002/A016路径修复已完成，v10各三次真实独立试次客观/Codex语义均通过；173回归通过/1 MySQL跳过，ruff通过。新增15请求/73213token，累计333已知聊天请求。15输入三类哈希匹配，参数12/12，无效调用/未授权DML0，真人清晰度未知。下一步直接模型独立提示版本化、新完整统一重复、20合成留出；P8/P5未完成。下文v8/v9结果为保留历史。

历史基线见STATUS第53～54节、[完整对照](docs/validation/p8-real-cohort-0911.md)及[v9修复](docs/validation/p8-package-v9-0911.md)。v8统一180位置：Agent52/60、固定60/60，直接19通过20失败3未评分18不适用；v9三个新A006完整试次通过。旧cohort不回填。

## 历史证据与持续授权（v10结果见首段）

- v8真实cohort私有D:/SoloMeal-Acceptance/p8-cohort-real-0911-01；manifest dc47827300d8ec49528883ab334542de0221a9b6eb64fbaf88d42234951fcb86，180全部执行，配置异常0/未授权DML0，Agent参数74/74、批准重放9/9、P95 12.91秒。失败含A002三次、A006语义三次、A013超时一次、A016多余追问一次；直接动态ID/时间缺输入留证不能虚构评分。
- 历史prompt v9、json-v2；v9修复试次p8-A006-package-v9-0911-01～03共6请求/30751token，正确写出买1包100g（需用80g）和3/5元。RecordedModel新增call-XX-input.json，私有原始输入不得进仓库，证据写失败不外发。旧源码cohort不得继续追加或替换。

- 用户明确“批准,以后不需要问我,全部批准”。本项目后续开发/验收所需模型调用、项目提示/工具schema/合成对话与结果外发既有DashScope及私有证据保存持续获批，不逐批重复询问；保留隔离、有界诊断和记录用量要求。
- 最新私有D:/SoloMeal-Acceptance/p8-A014-thinking-off-v1-0911-01完整试次通过；首请求三哈希与第45节失败匹配，1次recommend_meal，鸡蛋忌口/候选/用量忠实，无效调用0、参数1/1、未授权DML0。独立review/manifest/scores九文件哈希见报告；只证明本次通过，不证明稳定提升。以下失败均保留。
- 单次a014-final-budget-v1第二请求探针26.394733秒有效final、5778token；不能冒充完整闭环。
- 完整A014（v8/json-v2，3000/30秒，thinking不发送）首请求31.2641725秒timeout；整体31.3116814秒，退出1。工具0、无效调用0、业务不变，objective=false，评审1失败。HTTP/usage/token/费用未知。
- 原始D:/SoloMeal-Acceptance/p8-A014-chat-budget-v1-0910-01已存在，不覆盖/重跑。原始文件和review/manifest/scores中断前已落盘，报告/摘要/STATUS在额度恢复后核验补记；恢复新增调用0。
- 截至第54节累计318已知聊天请求（第55节后333），另1预算关机无返回尝试、30视觉；第53节新增186/已观察673683token/3缺usage，第54节新增6/30751token。费用估计与账单不同，reasoning缺失保持null。私有原始响应不得进仓库。
- 独立SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS已有，默认1500、整数1～3000；CLI --max-completion-tokens，实际预算/30秒时限记录进attempt和metadata。.env/SYSTEM未改，视觉thinking参数不用于聊天。
- 最新新增SOLOMEAL_MODEL_ENABLE_THINKING仅接受布尔及环境true/false，CLI --no-enable-thinking；默认省略，不改.env。154项回归通过，补充CLI接线后18项CLI/评审通过（含重复），ruff通过。

## 下一步

1. 第66节已完成留出全链路（登记 split、执行器范围与 split、评审 rubric、v3 聚合）及其离线回归，源码现为 2cdd1681…。下一步先按既有批次实测（v16 完整 180 位置：191 请求、818246 已观察 token、墙钟 22 分 41 秒）给出两批成本与耗时估算并明确标注为估算，由用户决定是否执行；随后在全新私有目录分别登记 `--split debug`（180 位置，approve 仅 A010～A012）与 `--split holdout`（180 位置，approve 仅 A030/A031/A033），各自预检、执行、审计、评审、聚合。旧 v16 三处 Agent 与 15 处直接模型失败照例保留不回填，其可泛化缺口分析仍是未完成 backlog，只作离线核对、不按场景答案特判，也不向旧目录追加。
2. 20 合成留出此前为 0，脚本层阻塞已解除：`cohort_agent.slots()`、`evaluate_agent.py`、`review_agent.py`、`cohort_metrics.py` 均已按 split 工作并补专项离线回归，冻结标签与门槛未改。留出仍未登记、未执行，85% 门槛保持“未测量”，不能用 debug 的 95.00% 冒充留出验收；历史 freeze 与 amendments-v1.1/A005、v1.2/A007 保留。
3. 动态进度只写DRIVER与STATUS，不改冻结README；私有原始输入与响应不得入仓库，Codex语义不冒充真人清晰度（当前全null），旧直接输入缺口不补造。MySQL工程7场景、P4/P5/P6完整验收、浏览器/真机、人工清晰度、新独立小票留出、真人试用及P9部署/备份恢复仍待完成，PLAN正式范围不删减。
4. 以下约定为历史：v4/v8/v10各批次的完整180位置均已完成并禁止重跑，各版本源码不同故不得向旧目录追加；两个旧无模型工程批次与全部失败同样保留。

## 环境与保护

- backend/.venv/Scripts/python.exe、frontend依赖已有；聊天开关默认false，视觉true，评测只在内存开启聊天且显式json，不改.env、不输出密钥。开发库和根data不触碰。
- MySQL只用solomeal-dev-mysql、127.0.0.1:13316，测试仅solomeal_test串行，不能指向开发solomeal/MySQL80/其他容器；SQLite不当MySQL并发证据。第66节Docker守护进程未运行且本轮未启动，16项MySQL门控用例保持跳过，MySQL并发证据仍属未完成。
- pytest新专用--basetemp、-p no:cacheprovider；git仅单次-c safe.directory=D:/Code/meal-manager，不改全局配置。已有未提交成果保留；本段未提交推送。
- 每段结束同步STATUS和本文件；PLAN保留目标，计划不等于已实现。授权已持续更新，旧报告“待批准”仅为历史，不再据此重复询问。
