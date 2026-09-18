# AGENTS.md

<!-- SOLOMEAL_PLAN_ENTRY_START -->

2026-09-18第98节：穷举第96/97节保留的「其它面板同类挂载 GET 竞态」——四处一处为真、三处排除（`AgentPanel`/`ReceiptPanel`/`InventoryEditor` 不构成覆盖窗口）；真实缺陷在 `ShoppingPanel` 报价表单：挂载 GET `/quotes` 晚落地翻转 `key={selected+':'+version}` 使 React 重挂载、清空已输入。修复净 1 行 `key={selected}`；新回归 `quotes-race.test.mjs` 门控扣请求＋双向验证（旧代码必失败）。本地：前端 36、产物 `index-xzzr0Hjd.js`、e2e **20/20**、插件随 pre-commit 373+298。**前端冻结量取代第97节**：产物 `D2Luux6J`→`xzzr0Hjd`、聚合 `1a99ab46…`→`17670f7b594d…9a68`；**如实记录**：同法复算修复前字节得 `160ee684…`≠第97节值，聚合口径按工作区字节、本机 `core.autocrlf`（实测 sse.ts 混合换行）致其跨工作区不可重建——系第95节已声明限制，发布锚点只认 commit SHA＋tree＋产物名＋镜像 digest。后端/API 镜像不变、web 镜像待重建。代码提交 `fd795a1`；CI 复验与 18080 重部署为后续、以 Actions 列表为准。模型新增 0、累计 1685/30。见 docs/validation/quotes-mount-race-0918.md 与 SOLOMEAL_STATUS 第98节。
2026-09-18第97节：用户授权处置三项低成本决定之第1项——第96节保留的 UI 侧偏好覆盖缺陷已修：`main.tsx` `Preferences` 加 `edited` ref，挂载 GET 落地仅在未编辑时回填（+4/−2 行）；新增 e2e 回归 `preferences-race.test.mjs`（注入 1500ms 延迟、断言输入不被覆盖且 PUT 存 `["煮锅"]`），并做双向验证（还原旧代码该用例必失败）。本地：插件 373+298、前端 36、build 产物 `index-D2Luux6J.js`、e2e 19/19。**前端冻结量自本节取代第95节值**：源码聚合 `4285ae31…`→`1a99ab46a45e…ba48`（同口径 15 文件）、产物 `BTAvzu0t`→`D2Luux6J`；后端 `c3161b9b…`/API 镜像不变、web 镜像待重建。两文档性哈希不被 freeze 测试引用，CI 无预期失败。代码提交 `4c47ee2`；远程 CI 复验、18080 重部署、Dependabot PR #1 为本轮后续，以 Actions 列表为准。未做：其它面板同类竞态未穷举、未 stress 重跑。模型新增 0、累计 1685/30。见 docs/validation/ui-preferences-clobber-fix-0918.md 与 SOLOMEAL_STATUS 第97节。
2026-09-18第96节：第95节的收口文档提交（`5ef812f`/`1b6cf00`）推送后 run `35320718788` 的 `browser-e2e` 失败 2/18、`ci-complete` failure，其余七作业 success——CI 全绿自此只在冻结点 `f3f9c7b` 成立、不在 HEAD 成立。先排除回归（diff 仅 7 个 `.md`、两轮产物同为内容哈希 `index-BTAvzu0t.js`）再定位根因：偏好面板每次挂载 GET `/me/preferences` 并回填受控输入（`frontend/src/main.tsx:79`，保存按钮 `disabled={busy}` `:80`），e2e 驱动切 tab 后不等待即 `fill`，慢 GET 落地会把已输入厨具覆盖成服务端旧值，且覆盖必然早于点击（Playwright 要等 busy 解除），PUT 遂存空厨具，`backend/app/services/planning.py:115` 按厨具子集硬过滤得 0 候选，页面即 CI 里逐字相同的「没有符合条件的菜谱」。注入 1500ms 延迟做 A/B：旧写法 PUT body `equipment: []` 复现、新写法 `["煮锅"]` 通过；修复 `d3fcb9d` 只改四个 e2e 文件（新增 `openPreferences`、四处调用点改用），断言未放宽、应用代码零改动，复跑 `35322761131` 九作业含 `ci-complete` 全 success（`08:18:03Z`）；本节文档提交 `348fdf6` 的 run `35324565914` 亦九作业全绿（`08:39:22Z`），即文档改动未触及冻结校验。前端源码聚合复核仍 `4285ae31…`（15 文件，`e2e/` 不在口径内，算法已补记），产物/后端 `c3161b9b…`/两镜像 digest 未变，第95节冻结值不被推翻。**插件套件计数更正**：同一 `test_unit.py` 在 `39ab68f` 计 372、`f3f9c7b` 起计 373（`test_unit.py:2271` 逐 `- uses:` 行核对钉版，backend 作业新增一行 setup-node），Linux CI 376+300，交接文本按平台分别标注。**未做**：UI 侧同类「慢 GET 覆盖已输入」缺陷保留（修它要改 `main.tsx`、动已冻结产物，待用户决定）；其它面板同类竞态未穷举；未做 stress 多轮重跑。模型新增 0、累计 1685/30，未部署、18080/18082 未动。见 docs/validation/browser-e2e-preferences-race-0918.md。
2026-09-18第95节：发布准备（用户授权完整执行）已收口到远程 CI 全绿（绿在冻结点 `f3f9c7b`；其后的 HEAD 见第96节）。420 文件安全盘点无真实凭据；本地套件全绿（插件本地 Windows 373+298（2 项平台 SKIP；Linux CI 376+300）、前端 36/build `index-BTAvzu0t.js`/e2e 18、后端 530 通过/16 MySQL 跳过，模型新增 0 累计 1685/30）；提交 7 个（`9a060b0` ci 行尾规范化、`f9fbcf8` backend、`5eb512f` frontend、`0935c99` deploy、`39ab68f` docs+evaluation、`1882669` 证据逐字节钉住、`f3f9c7b` CI 作业修复），pre-commit 钩子逐次实跑。**远程拓扑更正**：`sergiparpal/meal-manager` 只是 `docs/upstream.md` 记录的只读上游、用户与其无关联，早先 403 不是待修授权缺口；`origin` 改为用户自有私有仓库 `xpzzzzz/SoloMeal`，`upstream` push URL 置 DISABLED。**三类 CI 失败先在 Linux 等价检出复现再修**：冻结清单 sha256 按原始 CRLF 字节记录、LF 规范化致两条 freeze 测试失配（`.gitattributes` 把 31 个被摘要记录的路径标 `-text` 并回钉原字节，diff 增删逐行相等、零内容改动）；`mypy -p meal_manager` 误纳 `deploy/`+`docs/`（exclude 收口）；backend 作业两轮全量 pytest 撞 15 分钟上限且缺 `frontend/dist`（作业内 `npm ci && npm run build`、预算 20 分钟、断言未放宽）。run `35319166877`（push @ `f3f9c7b`）九作业含 `ci-complete` 全 success；browser-e2e 该轮通过、不宣称竞态已消除（该保留随即被第96节验证：偏好面板挂载读取确为真实竞态，已在测试驱动侧消除并复跑全绿）。冻结：提交 `f3f9c7b…`、tree `d0d02354…`、后端源码聚合 `c3161b9b…`（67 文件，同第84/91节即后端零改动）、API 镜像 `908cf165568b…`、web 镜像 `f2928999404b…`、前端源码 `4285ae31…`（15 文件自订口径）；源码聚合按工作区字节计算，跨平台换行不同即不同值，发布以 commit SHA＋tree＋镜像 digest 为准。工作区限定：已跟踪文件除本轮文档外无未提交改动，根下 5 个（初稿误记 6 个）ACL 锁死的 `.pytest-*`/`.test-tmp-crud-0906` 证据目录未跟踪未 ignore 不可读，`git status --porcelain` 打权限警告但退出码 0（初稿误记 2），勿删勿改权限。P5/P8/P9 整体及旧 48/60、`holdout_gate=failed`、真人清晰度 null 保持；CI 绿只了结远程流水线一条，P9-04 新物理主机与 v1.0 发布仍为独立条件。Dependabot PR #1 仍 open 待处置。详见 docs/validation/release-prep-0918.md 与 SOLOMEAL_STATUS 第95节。

2026-09-17第94节（含92/93节）：第91节独立复核三处 P2 全部修复并在真实堆栈补验通过。第92节（离线）：`errorText.ts` STEP_LIMIT 不再引导无效恢复（retry 不重置 steps）、RUN_NOT_READY 改中性提示（+反例单测）；本地化脚本零模型保护前移到 POST 前、failed 页面按码断言精确中文正文；429 计时改 `Math.round(ms/100)/10`。第93节（离线）：按用户二次复核把 429 恢复补严——每次点击收集本轮全部 5 类 api GET 要求全 200、以刷新按钮 busy 禁用窗口闭合界定本轮结束。第94节（用户授权）：新镜像 `solomeal-web:review-fixes-0917` 重启 18082（模型关闭）实跑两脚本通过——429 触发 103×200/47×429、Retry-After:60、页面中文提示，**恢复成立且真实耗时 3.6 秒/2 次点击（取代作废的 0.2 秒）**；补验中另修复两个驱动缺陷（run 列表投影无 result 使旧版正文断言从未真正生效；本 Playwright `locator.waitFor` 不支持 enabled/disabled 致窗口判定恒 false）。应用代码零改动、后端未变。离线 `npm test` 36、`npm run build`、`npm run e2e` fixture 18 全过；模型新增 0、累计 1685/30。源 18080 未动健康、仍未部署新前端；18082 stop 卷保留、累计 2 个一次性洪泛空账号。第91～94节的修正与补验已全部收口：2026-09-18 用户独立核对最终脚本、报告与两份实际 checks.json 后确认证据与汇报一致（429 计数、最后一轮 5 类接口全 200 的恢复记录、单个 run 详情的完整中文错误正文断言，且 frontend 目录无本轮同名证据残留），第91节「429 恢复已收口」的限定就此终结、无需就同一问题重跑；3.6 秒/2 次点击只是本次受控场景的实测值，不是恢复时间保证。旧报告与旧证据不改写。P5/P8/P9 整体及旧 48/60 保持，无提交推送。下一步发布准备（提交/远程 CI/冻结哈希）须用户授权。见 docs/validation/section91-review-fixes-0917.md 与 docs/validation/p9-review-live-verify-0917.md。

2026-09-17第91节：完成第90节前列的两项零模型成本任务。（1）服务端错误原文本地化——把内联在 `main.tsx` 的错误码表抽为 `frontend/src/errorText.ts`，补全 RUN_NOT_READY 等 16 类码，未映射带码响应统一中文兜底、不再回显服务端英文；`AgentPanel.tsx` run 级失败展示统一走 `errorText`；后端零改动（磁盘 67 个 `.py` 与已验收 API 镜像逐文件 sha256 全匹配），英文契约文案原样保留。（2）真实 Nginx 堆栈下的浏览器 429 页面场景——新镜像 `solomeal-web:errtext-0917` + API p9-boundaries-0917 复用 18082 项目（compose 叠加文件仅覆盖 web），一次性空账号 150 请求→104×200/46×429、`Retry-After:60` 由 Nginx 本体返回、页面中文「请求较频繁…约 60 秒」并手动刷新恢复；`deployed-error-localization.mjs` 验线上 bundle 含码表、全 run 逐一 advance 全 409 且服务端原文逐字节一致、failed run 页面中文渲染。离线 `npm test` 35 通过（+6）、`npm run build` 通过、`npm run e2e` fixture 18 全过。模型新增 0、累计聊天 1685/视觉 30。源 18080 未触碰健康、未部署本轮前端；18082 验收后已 stop 卷保留。P5/P8/P9 整体及旧 48/60 保持，无提交推送。下一步发布准备（提交/远程 CI/冻结哈希）须用户授权。见 docs/validation/error-localization-0917.md。

2026-09-17第90节：仅文档。新增docs/validation/final-acceptance-checklist-0917.md，把第1～89节成果按「已收口／部分完成／未通过／已移出范围」四类收口并逐行链接证据报告，含对外表述红线与建议顺序；SOLOMEAL_STATUS第3、4节两张表按实际证据改写：P9阶段TODO→IN_PROGRESS，P6-01/03、P8-01/02、P9-01/02/03标DONE，P8-03→IN_PROGRESS，起步动作与「未做」快照中被后续章节推翻的旧描述更正。阶段级P5/P8/P9刻意不标完成，合成留出48/60＝80%、holdout_gate=failed、独立人工清晰度null、未提交推送原样保留。下一步优先（零模型成本）：409等服务端错误原文本地化、真实Nginx限流堆栈下的浏览器429页面场景；随后发布准备（提交/远程CI/冻结哈希）；独立人工清晰度与新小票留出、新源码完整留出、新物理主机、主机断电/数据盘写满须先给有界估算由用户决定。本轮未重跑测试、未调用模型、未改应用代码或部署、无提交推送；18080三容器只读复查healthy。见docs/validation/final-acceptance-checklist-0917.md。

2026-09-17第89节：补第88节保留项，在真实模型环境（solomeal-agent-weaknet-0917，18085，前置代理18086/控制18087）把断线驱动换成真实浏览器页面（AgentPanel+sse.ts）实测通过。5个新run各恰2步：单条advance被杀时Chrome连接层透明重试使UI完全无感；连杀两条后应用收到409（推断为被杀advance仍在服务端执行持租约）并显示服务端英文原文「Run is not ready to advance」（未本地化），未受影响的SSE流与焦点同步仍自动刷到「已完成 · 已执行 2 轮」无需点击恢复；SSE流300ms被杀后sse.ts携Last-Event-ID游标自动重连续收，状态单调到已完成。库存始终300.000克、事件恰1条、用餐0条，五run零业务写入。模型请求10次（估算6～12内、上限16），累计聊天1685/视觉30，token约5.9万～6.2万（估计），墙钟约38分钟。修复deploy/weaknet_proxy.py测试工具缺陷（每客户端连接仅建一次上游、不查at_eof()，nginx默认75秒空闲关闭后请求静默丢失，表现为浏览器POST永久挂起），改逐请求透明重连，默认故障注入语义不变故第87/88节证据不受影响，ruff通过。源18080未动健康；演示18082（录制已取消）与演练项目均stop卷保留。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-agent-ui-weaknet-0917.md。

2026-09-17第88节：真实Agent（模型开启）断线演练通过（API/SSE客户端层）。独立项目solomeal-agent-weaknet-0917（18085，DashScope qwen3.8-flash/json/thinking=false/3000）前置weaknet代理（18086/控制18087），最终批三场景一次通过：基线两步推荐；advance服务端处理完成后断连、重读run恢复继续推进、每run恰2步无重复模型请求或写入；SSE流中途断连后携游标重连收到全部缺失帧无重复帧。业务零写入（300克/0餐/仅1条种子事件）。最终批6次模型请求/19.611秒（硬上限16内，含调试累计12次模型尝试）。代理加法新增kill_mode="stream"（默认行为不变），新增驱动deploy/agent_weaknet.py，均ruff通过。累计聊天1675/视觉30（token估计约3.5万～4.4万）。浏览器UI层断线恢复当时未实测，见第89节。源18080与演示18082全程未动。P5/P8/P9整体及旧48/60保持，无提交推送。见docs/validation/p9-agent-weaknet-0917.md。

2026-09-17第87节：受控弱网验收通过。deploy/weaknet_proxy.py（18083→18082，控制18084）动态延迟+按HTTP/1.1逐请求断连，可杀复用keep-alive连接上的单个请求，ruff通过。API实测300ms注入0.620～0.629s（基线约0.01s）；做饭/撤销在服务端处理完成后断连（RemoteProtocolError非502），同幂等键重试同一记录，库存220/300克、事件1/0只应用一次。浏览器三场景通过：断连显示「无法连接服务器，请检查网络后重试」且同页其他请求正常、清除布防恢复、刷新后重新登录数据完整。模型新增0、累计1663/30；演示项目18082与代理保持运行，源18080未动。P5/P8/P9整体及旧48/60保持，无提交推送。三分钟录制用户本轮已取消；下一步真实Agent断线须先给有界估算由用户决定，主机断电/MySQL盘满/新主机另列。见docs/validation/p9-weaknet-0917.md。

2026-09-17第86节：三分钟演示七段脚本在solomeal-combined-0917真实浏览器预演一次通过：登录/库存、推荐100%覆盖、预览确认做饭300→220克、撤销恢复300克/0餐、小票草稿逐行单位错误提示与改正保存、助手模型关闭历史；预演后API核对状态回到演示起点。第1～3段截图成功，第4～6段视口隐藏以结构快照留证。模型新增0、累计1663/30；项目保持运行供录制，源18080未动。P5/P8/P9整体及旧48/60保持，无提交推送。下一步用户录制演示、受控弱网/真实Agent断线。见docs/validation/demo-rehearsal-0917.md。

2026-09-17第85节：新独立Compose项目solomeal-combined-0917（18082）合并验收p9-boundaries-0917 web/api组合通过。迁移退出0、demo seed/verify闭环、模型关闭降级可见；205批次默认100/分批读全/非法参数422；真实Nginx普通桶150请求31次429、模型桶40次31次、认证桶20次10次，429契约正确、健康豁免、6秒恢复；真实浏览器冒烟通过（视口隐藏以结构快照留证）。新增deploy/verify_deployment.py，ruff通过。模型新增0、累计1663/30。源18080未动健康，新项目已stop卷保留，P5/P8/P9整体及旧48/60保持，无提交推送。下一步演示预演/录制、受控弱网/真实Agent断线。见docs/validation/p9-combined-0917.md。

2026-09-17第84节：Nginx分组限流/429反馈、12类REST列表SQL分页与前端完整分批读取、容器thinking/预算/视觉额度配置已实现。后端530通过/16 MySQL跳过，Linux重叠子集58通过，前端29测试/构建及9浏览器场景通过；独立Nginx实际限流与禁网容器配置通过。三分钟演示脚本/技术问答/新主机清单已备，未录制或新机验收。源码c3161b9b…（67文件），模型新增0、累计1663/30。源18080健康且未重部署，P5/P8/P9整体及旧48/60保持，无提交推送。下一步新独立Compose组合验收、演示预演/录制及受控弱网/真实Agent断线。见docs/validation/p9-boundaries-0917.md。

2026-09-17第83节：P9备份故障保护与恢复演练完成。manifest改临时文件写入/flush/fsync后发布，停止服务纳入finally保护，缺schema恢复前拒绝。22保护测试Windows/Linux各过（同组）；真实1MiB tmpfs三路ENOSPC及独立MySQL部分导入/重试拒绝通过。新故障项目已停且卷保留，源18080健康，原恢复/开发仍停。模型新增0、累计1663/30，P5/P8/P9整体及旧48/60保持，无提交推送。下一步生产限流/分页、容器模型配置边界与交付材料；主机断电/MySQL数据盘写满尚未演练。见docs/validation/p9-fault-0917.md。

2026-09-17第82节：已核对用户填写的android-trial-form.json，PKX110/Android16/OnePlus浏览器五项真机检查全部报告通过，四个清晰度样本均5分（均值5.0），下一步理解均true，issues为空。作为单人补充试用结果记录；此前小票缺陷及修复留证保留。具体断网方式、时延/丢包参数未记录，不推断受控弱网或真实Agent断线已验收；P8全量人工门槛/旧48/60及P5/P8/P9整体未完成保持。模型新增0、累计1663/30，无代码或部署变更、无提交推送。

2026-09-17第81节：安卓小票确认无反馈定位为第1项个数与食材克单位冲突（HTTP422），原错误仅在长页顶部。新增逐行单位/整数校验、当前小票操作区错误反馈和入库中状态；24前端测试/构建/3小票浏览器测试通过。新版前端已部署到源18080且健康，只更新web。真实小票只读诊断，未代改或代确认；模型新增0，累计1663/30，后端未改。P5/P8/P9整体与旧48/60保持，未提交推送。见docs/validation/receipt-feedback-0917.md。

2026-09-16第80节：P9本地Compose空环境启动、模型关闭降级和真实MySQL/私有小票联合备份恢复通过；21表摘要及图片字节一致，幂等重放不重复写。12保护测试Windows/Linux各过（同组），源/恢复两次窄屏浏览器通过；安卓试用材料已备，真人评分/真机仍null。新增模型0，累计1663/30；源码a602c174…66文件。源solomeal-acceptance-0916a在127.0.0.1:18080健康，恢复b已停且卷保留，开发库未动。P9整体/P5/P8未完成、旧48/60保留，无提交推送。见deploy/README.md及docs/validation/deployment-restore-0916.md。

2026-09-16第79节：推荐响应四轮真实诊断完成，客观4/4、模型原文语义4/4、产品展示语义4/4；后续模型历史含服务端正文，非纯模型提升或新盲测。新增8请求/49142token，累计聊天1663/视觉30；三哈希全匹配、Agent业务DML0，驱动单独授权补1蛋。13离线测试/ruff通过，源码a722eab4…；旧48/60、真人清晰度null及P5/P8未完成保留，无提交推送。两个p8-recommendation-response私有执行/审计目录已完成，禁止重跑或追加试次。下一步真人清晰度/试用、真机弱网及P9部署备份恢复，见docs/validation/recommendation-diagnostic-0916.md。

2026-09-16第78节：推荐后续动作一致性离线修复完成；成功recommend_meal后的最终展示改由服务端按当前候选生成，逐菜限制做饭预览建议，原模型文字单独留证。后端149不同用例通过/1 MySQL跳过，前端21测试/构建/1新增脚本浏览器通过，ruff通过。模型新增0、累计聊天1655/视觉30；源码36a57a39…（64文件），旧48/60及P5/P8未完成保留，无提交推送。仅覆盖推荐出口，非真实模型语义提升；下一步新目录登记4 run最多32请求并分别评审模型原文/产品展示，见docs/validation/recommendation-response-0916.md。

2026-09-16第77节：受控报价拒绝真实恢复、真实页面入库/做饭/撤销与刷新恢复通过；历史JSON正文展示已修复，前端20测试/构建/脚本三轮浏览器、后端22通过1 MySQL跳过。首批三轮驱动误判原失败保留，新三轮结构通过但缺鸡蛋仍建议做饭预览，语义失败保留。新增20请求/118680token，累计聊天1655/视觉30，20输入三哈希匹配；后端源码1d129290…未变，前端/诊断入口改变。原48/60、P5/P8未完成，无提交推送；下一步离线处理后续动作一致性，见NEXT_SESSION及docs/validation/real-agent-0916.md。三个0916执行目录禁止重跑/追加，额度恢复收尾新增模型0。

2026-09-15第76节：MySQL JSON键顺序引起历史摘要重复嵌套已修复；4纯函数反例、相关25项回归与工程77实例通过（有重叠），16个MySQL专属竞争实例全过，冻结工程60/60，P3-04/P3完成。开发库摘要与昨日及执行前后一致；旧全量中断1 F/7 E、独立诊断失败保留。昨日页面16单测/构建/15浏览器场景通过，今天未重跑。源码1d129290…，模型新增0、累计1635/30，旧留出48/60与P8/P5未完成保留，无提交推送。下一步新源码有界真实多轮/报价拒绝恢复及真实模型页面验收，见NEXT_SESSION和docs/validation/mysql-pages-0915.md。

2026-09-14第75节：独立purchase-contract-v2协议、三模式驱动与证据绑定评审完成；口述190g缺口与明确三份白米饭两个新场景各三模式一次，本批全部通过（非新盲测）。70离线测试/ruff通过；真实8请求/39326token/约34.48秒，累计聊天1635、视觉30，8输入三哈希匹配、业务DML0。源码34cc3880…，生产SYSTEM/tools/direct-v1及七冻结JSON未变；原A026失败、留出48/60、holdout_gate=failed、真人清晰度null及P8/P5未完成保留，无提交推送。详见docs/validation/p8-purchase-contract-v2-0914.md。

私有D:/SoloMeal-Acceptance/p8-purchase-contract-v2-0914-01已执行审计评审完毕，不得重跑或追加试次，旧v19/v20/v21目录同样保留。下一步回到PLAN P3-04/P8真实MySQL验收：先核对专用测试库配置、服务可用性与脚本隔离边界，再执行MySQL用例并留证；随后补P4～P6页面验收。A035慢尾根因、报价拒绝后真实恢复、真人清晰度与P9等缺口保留。

2026-09-14第74节：A026题干/工具/评分契约离线核对完成。冻结文字oracle仅要求2包/200g/6元，servings=3及三候选等额外条件来自执行器；固定流程直接注入三份。隔离复现默认1份为缺30g/3元、指定3份为缺190g/6元，口述缺口estimate_purchase无需份数即正确。16相关回归及审计脚本ruff通过，源码1b7be0dd…与七冻结JSON未变，新增模型请求0、累计1627。原失败、留出48/60、holdout_gate=failed及P8/P5未完成保留。详见docs/validation/p8-a026-contract-0914.md。

下一步按报告草案实现独立purchase-contract-v2协议加载、三模式驱动与离线反例，明确区分口述缺口与三份菜谱规划；之后再冻结协议/配置/哈希、估算有界真实诊断并确定新批次。草案尚未冻结/登记/执行，不改v1判据或旧分数，所有既有私有批次禁止重跑/追加。无提交推送。

2026-09-14第73节：查询观测升v3（missing_required_query/missing，不推断已作答）、聚合升v6非门槛；修正四场景最多5 run/40请求。v21新私有批次A026/A027/A035各一次为2通过1失败，独立estimate_purchase新形状1通过。A026实际正确算出2包/200g/6元，但未满足原recommend_meal/servings=3判据，失败保留；A035本次两轮通过，无超时不代表根因解决。164离线回归/ruff通过，新增12请求/69601token/47.58秒，累计1627；12输入三哈希匹配，源码1b7be0dd…，SYSTEM/tools与第72节一致。v19留出48/60、holdout_gate=failed及P8/P5未完成保留，无提交推送。详见docs/validation/p8-purchase-v21-diagnostic-0914.md。

下一步先离线整理A026题干、工具能力和冻结oracle的一致性，未来修订须另订版本协议，不猜份数凑分、不回填历史失败。本次私有p8-purchase-v21-diagnostic-0914-01已执行审计完毕，不得重跑或追加试次；v19/v20旧目录及manifest仍禁止重跑/追加。下文第72节“待登记”为历史。

2026-09-14第72节：三项离线边界收口——Agent侧规划输入与run.constraints去掉模型可书写的quotes（报价来源与日期只取服务端保存记录，提交quotes即`extra_forbidden`/`unknown_field`、不回显、不给ID恢复），新增第9项只读工具`estimate_purchase`按用户口述缺口算整包支出（不猜份数、不关联菜谱、不预留库存），评测层加`required_query`观测把"没查就答"与"查了答错"分开（非门槛，旧分数不变）。A035只读既有证据判为慢尾、根因未知，30秒/3000输出预算未动。全量430通过/16 MySQL跳过、相关子集306通过/5跳过、改动文件ruff通过；本轮模型请求0，累计已知聊天请求仍1615，源码1674f831…、`tools_sha256 79ff5a75…`改变，P8/P5未完成。详见docs/validation/p8-purchase-v21-0914.md。

下一步先按既有批次实测给出请求/token/墙钟估算并标注为估计值、由用户决定，再在新私有目录登记v21小规模真实诊断（A026/A027/A035各一次加一条`estimate_purchase`新形状）；A026冻结判据仍要求猜测的`servings==3`，本轮未改判据也未宣称其已修好。不得重跑或追加v20九目录与v19/v20 manifest，回归不冒充新盲测，原留出48/60与`holdout_gate=failed`保留。

2026-09-14第71节：v20补通用ID查询/结构化只读恢复反馈及澄清、报价查询规则；194回归通过/1 MySQL跳过、ruff通过。9个已暴露场景诊断6通过3失败（A026编造报价日期、A027不查询、A035首轮回答超时），原失败保留。新增17请求/已观察94749token/1缺usage，累计1615；17输入三哈希匹配，源码33816f7d…；P8/P5未完成。

下一步先离线处理报价事实来源/任意缺口计算工具边界与必要查询完成状态，分析A035既有超时证据；不要仅继续堆提示。v20九目录及v19旧manifest禁止重跑/追加；回归不冒充新盲测，原留出48/60不变。详见docs/validation/p8-recovery-v20-0914.md。

2026-09-14第70节：v19合成留出180位置执行、审计、评审与聚合完成；Agent48/60（80%，未达85%）、固定60/60、直接26/42适用另18不适用。12个Agent失败全部保留，171退出码0/9退出码1。185请求/795947token，累计1598；恢复新增0，输入三哈希全匹配，源码7f8ab812…未变。holdout_gate=failed，真人清晰度null，P8/P5未完成。

下一步先离线修复通用查询/ID获取与错误恢复、澄清完整性、基于实际结果的后续建议；不能向旧manifest追加或重跑。源码变更后另登记有界诊断，原留出失败保留，修复后复验属于已暴露场景回归，不冒充新的盲测。

2026-09-14第69节：昨天v19统一debug 180位置已完成，恢复后离线审计评审聚合完成，新增外发0。Agent58/60、固定60/60、直接17/42适用另18不适用；A008-01漏问净含量、A014-01错误后续建议保留。190请求/833620token，累计1413；输入三哈希全匹配，180退出码均0，源码7f8ab812…不变。P8/P5未完成。

2026-09-13第68节：第67节三项离线问题已修复：恢复expiry/stale_quotes/注入文本冻结契约，metrics-v4将固定流程语义硬约束标不适用（客观判据保留），清晰度恢复mean≥4。222个不同回归用例通过、ruff通过，85%边界/完整成功/失败/缺失均有测试。源码7f8ab81290559aba68d70a2b8e672bcad78af6b6b2c413d4086292996915d79a；模型外发0/新登记0。下一步按新哈希登记调试统一重复，再合成留出；P8/P5未完成。

2026-09-13第67节：独立审阅第66节，源码2cdd1681…核对一致，评测子集205项复跑通过；发现留出expiry/stale_quotes夹具偏离冻结契约、固定流程空硬约束评分使holdout_gate不能通过、清晰度min与冻结mean不符。仅审阅未修代码，模型外发0/新登记0。下一步先修三项离线问题并回归，再按新哈希登记批次；P8/P5未完成。

2026-09-13第66节：留出A021～A040登记/执行/评审/聚合离线补齐（register --split必填、每split仍180位置、确认扩展分置debug A010～12与holdout A030/31/33、聚合升cohort-metrics-v3按全分母判定留出85%）；并修复带保质期库存使get_inventory工具边界序列化失败的真实缺陷（A021此前不可能达成，REST被jsonable_encoder掩盖）。完整401通过/16 MySQL跳过（Docker未运行）、改动文件ruff通过。外发0、新登记0，调试与留出统一重复均未启动，留出85%仍未测量，P8/P5未完成。见STATUS第66节和docs/validation/p8-holdout-offline-0913.md。

2026-09-13第65节：v19将短/长续聊历史统一归入文本摘录，仅本轮工具结果作为活动消息；三轮回归及A015三次独立真实复验通过，旧v18失败保留。相关98项最终通过/1 MySQL跳过（分组复验有重叠），ruff通过。新增12请求/70071token，累计1223。下一步先离线补留出登记/执行/评审/聚合全链路，再新源码统一调试与留出；本轮未启动完整重复，P8/P5未完成。

2026-09-13第64节：v16独立r2评审更正为Agent56/60、固定60/60、直接27/42适用另18不适用；退出码178个0/2个1。v17三类通用修复6/9、v18进一步修复8/9，A015-v18-02旧轮用量复用失败保留。106回归通过/1 MySQL跳过，最终22通过/1跳过、ruff通过。新增46请求/277153token，累计1211。下一步先离线处理多轮最新结果引用，再有界复验及留出全链路支持；不启动完整重复，P8/P5未完成。

2026-09-12第63节：v16完整180位置统一批次执行、离线审计/评审/聚合完成；Agent57/60、固定60/60、直接27/42适用另18不适用，合计144通过/18失败/18不适用。Agent三失败保留（A001-02数组信封、A009-01猜单位并留下待确认写入、A015-02份数表述），第62节修复的两类未复现、本批无超时。191请求/818246已观察token，累计1165。禁止重跑manifest；下一步离线复核失败通用缺口后按新哈希登记，20留出需先扩展split支持。P8/P5未完成。见STATUS第63节和docs/validation/p8-cohort-v16-0912.md。

2026-09-12第62节：拒绝解释/净含量澄清修复，v14/v15各5/6且新推测失败保留；v16六独立真实复验全部通过。91回归通过/1 MySQL跳过，最终16通过/1跳过、ruff通过。新增27请求/139902token，累计974；v13同输入超时离线分析完成、根因未知。下一步新登记v16完整180位置统一重复，再20留出；P8/P5未完成。

2026-09-12第61节：v13完整180位置及恢复离线审计/评审/聚合完成；Agent55/60、固定60/60、直接20/42适用另18不适用。三首请求超时、A004拒绝解释及A008净含量澄清失败保留；A014三次通过。188请求/758184已观察token，累计947，恢复新增0。禁止重跑manifest；下一步通用修复/独立复验，再统一重复与20留出。P8/P5未完成。

2026-09-12第60节：v13后续操作能力边界修复及A014三独立真实复验通过；118回归通过/1 MySQL跳过、ruff通过。现有A013同输入延迟1.86/超时31.04/27.86秒，根因未知且旧失败保留。新增6请求/31208token，累计759。下一步新登记v13完整180位置统一重复，再20留出；P8/P5未完成。见STATUS第60节和docs/validation/p8-capability-v13-0912.md。

2026-09-12第59节：v12完整180位置执行、离线审计/评审/聚合完成；Agent58/60、固定60/60、直接23/42适用另18不适用。A013-02超时及A014-02不支持的忽略忌口确认路径保留，硬约束59通过/1缺失。189请求，累计753；额度中止恢复新增0，禁止重跑该manifest。下一步修复不支持的后续路径并独立复验、分析超时，再统一重复/20留出；P8/P5未完成。见NEXT_SESSION与STATUS第59节。

2026-09-12第58节：v11默认约束/比较/忌口解释修复7/9，两个A007新失败保留；v12澄清本轮条件提取和先查询后回答，九独立真实试次全部通过，18输入三哈希匹配。166回归及最终59复验通过（各1 MySQL跳过，包含重复），ruff通过。新增34请求，累计564。下一步新统一180位置三模式重复，再20留出；旧v4不重跑，P8/P5未完成。见NEXT_SESSION及v12报告。

新会话先读 [NEXT_SESSION.md](NEXT_SESSION.md) 获取简短交接，再按需读 STATUS/PLAN。
## SoloMeal independent application plan / 独立应用接手入口

For SoloMeal work, read [SOLOMEAL_PLAN.md](SOLOMEAL_PLAN.md) and
[SOLOMEAL_STATUS.md](SOLOMEAL_STATUS.md) alongside this file and the other
repository guidance file. PLAN defines the agreed target; STATUS records actual
progress, evidence, pending tasks and handoff notes. Update STATUS after each
implementation session. Planned features are not implemented features.

The user has selected an independent single-agent Web application as the target.
The original plugin guidance below describes the existing Hermes implementation.
Its stdlib-only, JSON-only and approximate-portion constraints continue to apply
to unchanged plugin code; they do not prohibit the planned independent backend,
frontend, database and their dependencies. P0 must document the reuse/migration
boundary before implementation. Preserve existing data, license and unrelated
changes. Keep AGENTS.md and CLAUDE.md consistent as the application evolves.

当前 P0 已完成；库存事务/归档、版本化方案、独立会话与确认工具及 React 页面已有实现；报价持久化与采购草稿确认入库也已实现；小票私有上传、可编辑草稿与整单确认入库已加入；2026-09-09指定配置下三份真实视觉与页面闭环验收通过，P7完成。P8已冻结100场景及门槛，前三场景真实调试与聊天观测已有；可选JSON协议下A003三次通过，原生/响应失败保留，已扩展10个调试场景、预算与真实确认闭环；A007关机中断记录保留，新目录复验通过。完整对照及部署仍待验收，以STATUS第36节和实际代码为准。
2026-09-11最新：v8真实统一180位置完成，Agent52/60、固定60/60，失败/缺失保留；v9包装量修复三个新A006通过，私有输入留证及154回归/ruff通过。以STATUS第53～54节、NEXT_SESSION为准；累计318已知聊天请求，P8/P5未完成，A002/A016等修复、新统一重复/留出待做。
用户已要求开始开发；提交/推送仍按具体授权。请阅读 docs/upstream.md 和 backend/README.md。
2026-09-11第56节：direct-v1与cohort-v4已实现，180专项/ruff通过；四真实诊断1通过2失败1不适用，累计338请求。新v4完整180位置已登记未执行，下一步见NEXT_SESSION；P8/P5未完成。
2026-09-11第55节：v10 A002/A016路径修复各三个真实试次通过，173回归通过/1 MySQL跳过、ruff通过；累计333已知聊天请求。下一步直接模型独立提示、新完整cohort及留出，P8/P5未完成。见[报告](docs/validation/p8-routing-v10-0911.md)。
原插件测试已补 Windows 分支，CI 已隔离新应用并加入 backend/frontend/browser-e2e 独立任务，全部汇入 ci-complete；远程运行仍待验收。
<!-- SOLOMEAL_PLAN_ENTRY_END -->

Repository guidance for agentic coding work in `meal-manager`.

Read `CLAUDE.md` before starting — it contains additional repository-specific guidance that should be consulted alongside this file and kept consistent with it.

This repo is a Hermes plugin that manages meals, fridge inventory, recipe data,
and Dynamic Ingredient Interface (DII) sessions. It uses only the Python
standard library and persists state in JSON files under `data/`.

## Fast Facts

- Python 3.12+.
- No third-party **runtime** dependencies. The plugin imports nothing outside the standard library, and nothing under `src/` or `__init__.py` may import a development tool. **Development/CI** tooling does exist and is pinned: `mypy==2.3.0`, `coverage==7.15.0`, and `ruff` (configured in `pyproject.toml`).
- No build step is configured. `pyproject.toml` holds tool configuration only — deliberately no `[build-system]` table and no `[project]` metadata, because this plugin is loaded by path as `hermes_plugins.meal_manager` rather than installed as a distribution.
- Lint is configured (`ruff`, narrow `F,B,I` selection) but is deliberately **not** a CI gate.
- Tests are plain Python scripts with assertions, not a pytest/unittest harness. Register every test function in `main()` via `run(test_fn)`, never as a bare call: `run` records a raised exception as a failure so one mistake cannot abort every test after it.
- CI (`.github/workflows/tests.yml`) runs on push to `main`, on pull requests, and on manual dispatch: a `tests` job (both scripts across Python 3.12/3.13/3.14), a `types` job (mypy), and a `coverage` job (`--fail-under=91`, a ratchet — raise it when coverage rises, never lower it to make a build pass). Any new job must be added to `ci-complete`'s `needs:` list; that job is the single required status check for the branch ruleset and it fails if a needed job is skipped, cancelled or failed. GitHub Actions are pinned to full commit SHAs with a trailing `# vX.Y.Z` comment. The `tests` job ends by verifying the suites left the checkout untouched: no `data/` under the repo root and a clean `git status`. Both are needed — `data/` is gitignored, so the porcelain check alone would not notice it appearing, and a fresh checkout has none, so its mere existence is the failure.
- Both suites also run before every commit via `.githooks/pre-commit`, which each clone activates once with `git config core.hooksPath .githooks`. Stdlib-only and quiet unless something fails; it deliberately skips `mypy` and `coverage`, which need an install a fresh checkout does not have. `git commit --no-verify` skips it and gets you nowhere, because `main` still requires `ci-complete`. A group of checks at the end of `test_unit.py` holds the hook and the workflow to what they claim — executable bit, both suites in both places, the declared Python floor present *in the matrix* (not merely somewhere in the file), every action pinned to a SHA, every job in `ci-complete`'s `needs:`. Every one of those failures is a silent one, which is why they are tested rather than trusted.
- Tools are auto-discovered: each module under `src/handlers/` exports `NAME`, `SCHEMA`, `HANDLER` and is picked up by `iter_tools()`. There is no central registry to keep in sync.
- Relative imports are required inside the package.
- Preserve the existing JSON data formats and tool names. Every format change on record follows the same courtesy — the loader accepts the old shape, migrates it in memory, and rewrites it on the next save, so no user ever runs a migration step:
  - `fridge.json`: flat array of names → `{name: count}` object (`null` = pantry staple, `0` = out of stock) → values may also be `{"count": n, "expires_on": "YYYY-MM-DD"}`. Entries without an expiry are still written as bare scalars.
  - `history.json`: `{dish: date}` → `{"schema_version": 2, "events": [...]}`, an append-only log. Legacy ids are derived with `uuid5` so re-migrating is idempotent.
  - `dishes.json`: dishes may carry `instructions`; the key is emitted only when set, so untouched catalogs do not churn.

## Core Commands

- Run the integration smoke test:

```bash
python3 test_integration.py
```

- Run the unit test script for domain logic:

```bash
python3 test_unit.py
```

- Run a single unit test function directly:

```bash
python3 -c "import sys, importlib, pathlib; sys.path.insert(0, str(pathlib.Path('.').resolve().parent)); m = importlib.import_module('.test_unit', pathlib.Path('.').resolve().name); m.test_calculate_score_basic()"
```

- Run a single integration-style test function with explicit setup and teardown:

```bash
python3 - <<'PY'
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path('.').resolve().parent))
m = importlib.import_module('.test_integration', pathlib.Path('.').resolve().name)
m._setup_tmp_data()
try:
    m.test_list_fridge()
finally:
    m._teardown_tmp_data()
PY
```

`_setup_tmp_data` creates a `tempfile.mkdtemp()` directory, points the repository and DII singletons at it via `configure()`, and seeds deterministic JSON fixtures. `_teardown_tmp_data` deletes the directory. The live `data/` under the repo root is never read or written. `_backup` / `_restore` still exist as compatibility aliases for older recipes.

- Run one tool interactively:

```bash
python3 -c "import sys, importlib, pathlib; sys.path.insert(0, str(pathlib.Path('.').resolve().parent)); m = importlib.import_module('.src.handlers.get_meal_suggestions', pathlib.Path('.').resolve().name); print(m.HANDLER({}))"
```

- Prefer the smallest relevant script or direct function call instead of the
  full integration suite when you only changed a narrow area.

## Imports

- Use relative imports inside the package, for example `from .src.repositories import dish_repo`.
- Do not switch to absolute `src.*` imports; Hermes loads the plugin as a
  package, and relative imports are the safe form.
- Keep standard library imports first, then local imports.
- Avoid import cycles; if a helper is shared, move it to a lower-level module.

## Formatting

- Follow the existing Python style rather than introducing a new formatter.
- Use 4-space indentation.
- Prefer double quotes for strings.
- Keep lines reasonably short and wrap long expressions or dict literals.
- Use blank lines to separate logical sections.
- Long modules often use `# ---------------------------------------------------------------------------`
  section dividers; keep that pattern when it helps readability.
- Keep comments sparse and only add them for non-obvious behavior.

## Naming

- Use `snake_case` for functions, variables, and module-level helpers.
- Use `UpperCamelCase` for classes and dataclasses.
- Use `UPPER_SNAKE_CASE` for constants.
- Prefix private helpers with `_`. Modules under `src/handlers/` that start with `_` (e.g. `_common.py`) are skipped by the auto-discovery walker.
- Keep tool handler module names equal to the registered `NAME` constant (e.g. `src/handlers/add_dish.py` exports `NAME = "add_dish"`).
- Preserve public API names unless there is a concrete reason to change them.

## Types

- Type hints are used selectively, not everywhere.
- When adding or changing public functions, add hints if they clarify intent.
- Prefer concrete collection types like `list[str]`, `dict[str, int]`, and
  `set[str]` where the type matters.
- Keep annotations simple; avoid heavy type machinery unless needed.
- Maintain compatibility with Python 3.12 syntax.

## Error Handling

- Validate user-supplied input at the tool boundary.
- Raise `ValueError` (or `LookupError` for not-found cases) inside handlers — do not catch and reformat. The `@tool_handler(NAME, SCHEMA)` decorator from `src/handlers/_common.py` is mandatory on every public handler; it logs the exception via `logger.exception` and converts it into the unified `{"error": ...}` JSON envelope.
- Always pass `SCHEMA` to the decorator. It derives the allowed argument keys from `SCHEMA["properties"]`, so an unknown key is rejected instead of silently ignored. If a handler needs to read a key, that key belongs in the schema — the schema is the tool's public interface and should be honest. `extra_args={...}` exists for keys that must stay undocumented; comment why.
- The envelope message is sanitized by `_safe_error_message`. `ValueError` and `LookupError` pass through verbatim (handlers write them for the user); `OSError` and `json.JSONDecodeError` are replaced with fixed text because they carry filesystem paths and file contents; anything else becomes "An internal error occurred". `JSONDecodeError` subclasses `ValueError`, so it must be tested first. Full detail always still reaches the log.
- Handlers return plain Python objects (dict, list, str). The decorator handles `json.dumps(..., ensure_ascii=False)` for both success and error paths.
- Do not let stack traces escape a handler function — the decorator's outer `try/except` is the single guarantee of that.
- Internal helpers and engine-layer code may raise freely; the decorator at the boundary is the catch-all.

## Persistence

- Use `atomic_write_json` from `src/__init__.py` for every JSON write.
- Keep persisted file formats stable.
- Create parent directories lazily when needed, not at import time.
- Treat missing or malformed JSON files as empty state unless the caller needs an explicit error. "Malformed" includes valid JSON of the wrong *shape* — check `isinstance` before reading attributes off parsed data. A DII session backup containing an array raised `AttributeError` out of the orphan sweep and took down every DII tool, including the sweep that would have cleaned it up.
- Use UTF-8 for all file I/O.
- Do not store transient scratch data in `data/` unless the feature explicitly needs persistence.
- The data directory is injectable. `src/repositories/__init__.py:configure(data_dir)` and `src/dii/__init__.py:configure(session_dir)` redirect the singletons in place; the top-level `register(ctx, *, data_dir=None)` wires both. Tests should never hit the real `data/` — use a tmp dir via `_setup_tmp_data` / `configure`.

## Concurrency

- **All five file-backed stores share one lock object**: the `data_lock` singleton from `src/filelock.py`, an advisory `fcntl.flock` over `<data_dir>/.lock` that covers the whole data directory. It is assigned to the same attribute each repository already exposed (`self.lock` on the dish, fridge, alias, and tuning repos; `self._lock` on the history repo), so every existing call site is unchanged. It is reentrant, cross-process, and degrades to in-process-only where `fcntl` is unavailable.
- Hold the appropriate lock around load-modify-save sequences. A bare load-modify-save is a bug even when each half is individually atomic.
- **There is one lock, not five.** `dish_repo.lock`, `fridge_repo.lock`, `alias_repo.lock`, `tuning_repo.lock` and the history repository's private `_lock` are all the *same* reentrant `DataDirLock` object over the whole data directory. Nesting them is free and cannot deadlock, and the nominal `alias -> dish -> fridge` order documents intent only — it is not a live constraint. Keep writing it that way so the code survives any future move back to per-file locks (`src/dii/finalizer.py` is the site that would fix the order), but do not reason about deadlock risk that does not exist.
- **Multi-repository mutations take one explicit window.** Acquiring per repository still produces *independent* windows, so a handler that touches several must wrap its whole sequence in `with data_lock:` — `register_cooked_meal`, `merge_ingredient_alias` and `delete_dish` all do. Their compensation logic stays (an in-window step can still fail), but no other process can observe the half-applied state between steps. Normalize arguments *before* the window so it covers only the mutations.
- **Acquisition can time out.** `DataDirLock` polls a non-blocking `flock` up to `LOCK_TIMEOUT_SECONDS` and then raises `DataLockTimeout`. It is a `TimeoutError` (hence an `OSError`), so `_safe_error_message` tests for it *before* the generic `OSError` branch; anything added to that function must preserve that ordering.
- **Normalize arguments before acquiring any repository lock.** `_common.normalize_ingredient_name` reads the alias map, so normalizing inside a `dish_repo.lock` / `fridge_repo.lock` block inverts the documented order. Every handler normalizes first, then locks.
- DII sessions also use per-session locks plus a global lock for session maps. Always take a session lock through the `IngredientSessionStore.session_lock(session_id)` context manager, which reference-counts holders and prunes the entry itself. Never delete from `_locks` anywhere else: removing a lock does not release it, so a holder mid-critical-section and the next caller end up on different mutexes.
- Do not bypass the locking helpers when changing persistence behavior.
- Read-only suggestion queries are intentionally lock-free because they rely on atomic file replacement.

## Domain Rules

- Ingredient and dish names are normalized with `strip().lower()` semantics. The rule lives in the module-level `dish.clean_label(value, *, label)` and is applied via `Dish.normalize_name` / `Dish.normalize_ingredient` (and the `_common.normalize_*` wrappers that add the non-empty and length checks). It is public and lives outside the `Dish` class on purpose: the tool boundary needs the same rule, and `_common._normalize_label` reaching into a `Dish._clean` was the only place one layer touched another's private API.
- `Dish.__post_init__` enforces that `Dish.name` is always stored normalized, so downstream consumers compare `dish.name == name` directly — do not add defensive `.strip().lower()` at call sites.
- Cooking history keys are normalized to lowercase on load, so `history.json` comparisons are case-insensitive.
- `Dish.ingredients` maps ingredient name to `bool`.
- `True` means essential.
- `False` means optional.
- Dishes cooked fewer than 2 days ago are excluded from suggestions.
- Scoring never rewards essentials — they are a gate enforced by `can_cook_with`. The match term is the count of *optional* ingredients in stock, capped at `OPTIONAL_CAP`.
- The fridge stores portion counts: `None` = pantry staple (unlimited), `0` = known out of stock, `n > 0` = roughly `n` dishes' worth. `MAX_PORTION_COUNT` bounds the stored value, not merely the argument, so every path that produces a count (`add`'s running total, an alias merge) clamps to it.
- `register_cooked_meal` consumes one portion of each essential ingredient after recording the meal; staples are untouched and counts floor at 0 rather than being deleted. It accepts an optional ISO `date` for backdated cooks, which skip the learning update.
- Cooking history is an append-only event log, projected to one date per dish on read. `history_repo.load()` returns the latest `cooked_on` per dish with retracted events excluded, so backdating a forgotten meal cannot rewind a more recent cook — that is a property of the model now, not a flag on the write.
- Retraction and deletion are different operations. `delete_history_entry` retracts (the row survives, visible through `list_cooking_history`, and stops counting toward the projection); `register_cooked_meal`'s rollback path calls `delete_event` (hard delete, because a cook that failed halfway never happened); `delete_dish` retracts every event for the dish it removes.
- Ingredient aliases canonicalize input at the tool boundary only. `_common.normalize_ingredient_name` resolves them; `Dish.normalize_ingredient` deliberately does not, so the domain layer stays pure and I/O-free. Do not "fix" that asymmetry.
- On an alias merge, essential wins over optional in a recipe, and in the fridge a pantry staple wins over any count while two counts sum. The result is clamped to `MAX_PORTION_COUNT` on the way out, so a hand-edited out-of-band count is normalized rather than copied through.
- Alias resolution is the whole tool boundary's job, DII handlers included: `init_ingredient_session` builds sessions from canonical names and `dii_remove_ingredient` resolves before looking one up. Validating a name and then using the raw one leaves the DII path blind to aliases.
- Fridge entries may carry `expires_on`. Expired items stay available and are only flagged — the date is the user's estimate, not ground truth. The tool boundary is strict about the date format; the loader is forgiving and drops an unreadable date rather than the ingredient.
- `Dish.instructions` is optional free-form text capped at `MAX_INSTRUCTIONS_LENGTH`; blank normalizes to `None` so "cleared" and "never set" stay a single state.
- Colliding normalized names in a dict argument are rejected, not silently merged — the values can disagree. List arguments still collapse repeats. `Dish.from_dict` stays permissive so existing catalog rows keep loading.
- Quick shopping suggestions surface dishes missing at most `max_missing` essential ingredients (default 1), ranked by smallest basket (`still_missing`) first, then reach, then score. Reach-first alone promoted ingredients that unlock nothing on their own once `max_missing > 1`.
- DII sessions reveal suggestions one at a time through the probability funnel.
- Removing an essential ingredient in a DII session should signal that recalculation is needed.

## Editing Rules

- Make the smallest correct change.
- Avoid broad refactors unrelated to the task.
- Do not rename persisted keys or tool `NAME` constants without updating every consumer (handler module name, `plugin.yaml`, `skill.md`, tests).
- Keep top-level `__init__.py` minimal — it should only walk `src/handlers/` and inject the skill. Tool definitions belong in their own modules under `src/handlers/`.
- Do not edit live `data/` files unless the task explicitly requires it.
- If you touch persistence or DII, run both test scripts before finishing.
- If you touch a single pure function, the targeted unit test is usually enough.
- Leave unrelated worktree changes alone; do not revert or overwrite them.

## Testing

- `test_unit.py` covers pure logic in `src/dish.py`, `src/suggestion.py`, `src/shopping.py`, `src/tuning.py`, `src/history_event.py`, and the `normalize_*` / argument-validation / error-sanitization helpers in `src/handlers/_common.py`. It also covers the repository behavior that needs no tool boundary — fridge portion counts (including non-finite values and the expiry grammar), the history event log (projection, migration idempotence, retract vs delete, corruption), and the alias map — against a tmp path, not the real `data/`.
- `test_integration.py` is the end-to-end smoke test for all tool handlers.
- The integration script creates a throw-away tmp directory, points the repositories and DII session store at it via `configure()`, seeds deterministic fixtures, and removes the directory when finished. The real `data/` files are never touched.
- It intentionally exercises error cases and may print stack traces for expected failures.
- For a single integration scenario, call `_setup_tmp_data` / `_teardown_tmp_data` around one `test_*` function.
- Prefer the narrowest test that covers the changed code path.
- `.github/workflows/tests.yml` runs `test_unit.py` then `test_integration.py` on Python 3.12, 3.13, and 3.14 / `ubuntu-latest`. Both must exit zero, so a script that only *prints* a failure without asserting will pass CI — assert, don't print.

## Tool And Schema Notes

- Keep each handler module's `SCHEMA["description"]` in sync with the actual handler behavior — schema and code live side by side.
- Keep `plugin.yaml` aligned with the modules under `src/handlers/` (the auto-registration is the source of truth for what is registered, but `plugin.yaml` is read by Hermes for discovery).
- Keep `skill.md` aligned with DII behavior and user-facing interaction flow.
- Use `README.md` as the source of truth for the high-level project summary and examples.

## Editor Rules

- No `.cursor/rules/`, `.cursorrules`, or `.github/copilot-instructions.md` files are present in this repository snapshot.
- `CLAUDE.md` contains additional repo-specific guidance and must be read before starting any work alongside this file; the two should stay consistent.
