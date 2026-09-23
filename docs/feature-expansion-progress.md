# SoloMeal 功能扩展执行与审查记录

2026-09-22 F4 主审查结论：**APPROVED**。R1 已修复关闭个人用时估计且无历史样本时的 `standard_disabled` 来源；F5 可以开始。预览现产物 `index-DYKrHTKB.js`，模型0请求、未提交推送、18080未动。

2026-09-22 F3 主审查已 **APPROVED**。F4 可以开始；预览 http://127.0.0.1:18088，最终产物 `index-LtnRZllD.js`、迁移 `c63a1e7d9f20`。模型0请求、未提交推送、18080未动。详见文末F3；下方旧阶段快照保留历史口径。

开发规格：[feature-expansion-plan-0921.md](feature-expansion-plan-0921.md)。本文件只记录真实实现与审查进展。

2026-09-22（主审查复核）：F1 为 APPROVED，R1～R6 已收口，可以开始 F2。真实预览为 http://127.0.0.1:18088，产物 `index-Csm0Deym.js`（该产物现已被 F2 的 `index-CbHSzxJh.js` 取代，见下一条）。批准范围为本阶段实现与代表性验证；真实模型冒烟仍未授权、未执行，不宣称真实生成已验证。未提交/推送、未跑远程CI、源18080未动。具体主审查复核证据见文末；以下开发交接、首次退回和修复记录保留历史口径。

2026-09-22（开发 agent）：F2 收藏、喜欢/不喜欢反馈与烹饪方式标签已实现并交付同一预览，状态 READY_FOR_REVIEW——页面现引用 `index-CbHSzxJh.js`，迁移 `b52e9c4a7d18` 已在预览 MySQL 执行（`alembic current` → head），三容器 healthy、`/health/ready` 200。本轮真实模型请求 0 次；未提交、未推送、远程 CI 未跑；源 18080 未动；F3 未开始。逐条证据见文末「F2 …」节。

| 阶段 | 功能 | 开发状态 | 预览URL | 主审查结论 |
|---|---|---|---|---|
| F1 | 菜谱发现与确认入库 | APPROVED | http://127.0.0.1:18088 | 2026-09-22复核：R1～R6收口，可以开始F2；真实模型冒烟未执行 |
| F2 | 收藏、反馈、烹饪标签 | APPROVED | http://127.0.0.1:18088 | 2026-09-22主审查通过，可以开始F3；见文末复核记录 |
| F3 | 做饭模式与实际耗时 | APPROVED | http://127.0.0.1:18088 | 2026-09-22主审查通过，可以开始F4 |
| F4 | 个人耗时估计 | APPROVED | http://127.0.0.1:18088 | 2026-09-22 R1 修复后主审查通过，可以开始F5 |
| F5 | 隐式偏好排序 | APPROVED | http://127.0.0.1:18088 | 2026-09-22 R1 修复后主审查通过 |
| F6 | 推荐场景、解释、换一道 | APPROVED | http://127.0.0.1:18088 | 2026-09-22 F6 R1 主审查通过，可以开始F7 |
| F7 | 合并采购 | APPROVED | http://127.0.0.1:18088 | 2026-09-23 F7 R1 修复后主审查通过，可以开始F8 |
| F8 | 今天首页 | READY_FOR_REVIEW | http://127.0.0.1:18088 | 待主审查；见文末F8节 |
| F9 | 日历统计（增强项） | 暂缓（2026-09-23 用户决定） | — | — |

## 阶段交接

开发agent按计划§12.3模板在此追加当前阶段详情。只有主审查agent可以填写APPROVED；没有完成审查不进入下一阶段。

### F1 菜谱发现、草稿审核与入库

```text
阶段：F1；状态：READY_FOR_REVIEW
基线/结果：base commit 3ca1976；本轮未创建提交（提交/推送需授权）。改动全部在工作树：
  19 个已跟踪文件修改（+159/−41 行：5 个仓库文档 +15/−1，其余 14 个代码/配置 +144/−40）+ 12 个新增文件（其中 2 个是 0921 计划与本记录文档），共 31 个路径。
  10 个新增代码/测试文件合计 2388 行（0921 首交付 2075 行，修复轮 +313 行几乎全在测试），
  主要 diff 在 backend/app/services/recipe_discovery.py。
  `git status --porcelain` 可定位全部改动；本轮自建的临时脚本/pytest 产物已删除，工作树里没有它们。

变更：功能＝发现表单→一次最多 3 道候选→逐道编辑/按字段校验→确认加入菜谱库（同事务建缺失食材）
  →丢弃→「用当前条件重新推荐」沿用批次保存的条件；模型未配置时可全程走手工草稿。
  新增主要文件：backend/app/models/discovery.py、schemas/discovery.py、
  services/recipe_discovery.py、api/discovery.py、tests/test_recipe_discovery.py；
  frontend/src/DiscoveryPanel.tsx、src/draftValidation.ts、
  frontend/e2e/recipe-discovery.test.mjs、frontend/tests/draft-validation.test.mjs；
  backend/scripts/browser_fixture.py 增 --recipe-discovery 脚本化 provider。
  改动主要文件：backend/app/core/config.py（开关与独立预算）、app/main.py（provider 装配＋路由）、
  app/models/food.py＋app/services/food.py（菜谱来源字段、复用归属锁与幂等封装）、compose.yaml（三个环境变量透传）；
  frontend/src/main.tsx（「发现菜谱」tab＋推荐面板「发现更多」入口）、src/errorText.ts（草稿错误码中文）、
  src/session.ts（新列表登记分批读取）、src/style.css、e2e/support.mjs、e2e/mobile.test.mjs（tab 清单）。
  迁移名：a71f0d4c9b23（recipe_discovery：两张新表 + recipes.source_type/source_ref）。
  upgrade 已在预览 MySQL 执行；downgrade 路径每轮在 SQLite 测试夹具里实跑（conftest 结束降级到 base），
  未在预览 MySQL 上实跑回滚。

预览：http://127.0.0.1:18088（独立 Compose 项目 solomeal-features-0921，自有 MySQL 数据卷与
  小票上传卷，未引用源 18080 的任何卷；源 18080 至今未动，仍是第98节的 index-xzzr0Hjd.js）。
  实际构建：首页引用 /assets/index-Csm0Deym.js（2026-09-22 修复轮 npm run build 产物，取代 0921 的
  index-DahiIrSg.js），即页面确实加载新前端，非仅容器 healthy。
  健康：web/api/db 三容器 Up (healthy)，GET /health/ready 与 /health/live 均 200。
  迁移已在预览库执行：容器内 `alembic current` → a71f0d4c9b23 (head)。
  启动/重部署：docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env
        -p solomeal-features-0921 up -d --build --wait   （0922 修复轮即以此命令重建 web/api 并 --wait 到 healthy）
  停止：docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env
        -p solomeal-features-0921 stop   （卷保留，数据不丢）
  凭据只在该私有 env 文件里，未提交、不写入本文档。
  登录说明：预览是独立空库，用页面「第一次使用？创建账号」自助注册任意新账号即可，无需邀请码；
  口令不在本文档中，试用者自定。

用户试用（下列 6 步已用真实浏览器逐步跑通，含最终库存断言）：
  1) 注册新账号 → 打开「厨房偏好」，现有厨具填「煮锅」、默认人数 2、最多用时 30 → 点「保存偏好」，
     按钮短暂禁用后重新可用、面板保留所填值（第 5 步能推荐出来即说明偏好已存到服务端）。
     注意：不填厨具时推荐会说「没有符合条件的菜谱」，这是既有偏好过滤行为，不是本阶段缺陷。
  2) 「食材库存」→ 名称「挂面」、单位「克」→「添加种类」→ 选挂面（克）、数量 800 → 「确认入库」，
     表格出现挂面 800 克一行。
  3) 「发现菜谱」→ 顶部显示「当前未配置可用的生成模型」且「生成候选」按钮为禁用（预览未配真实模型，
     如实提示）→ 点「手工新建草稿」出现可编辑候选卡。
  4) 填菜谱名称/人数 2/用时 20/厨具 煮锅/做法一行 → 点「增加食材行」填 挂面 150 → 先勾「可选配料」
     → 点「按当前填写校验」：卡片内出现「至少要有一种不是可选的食材。」且「确认加入菜谱库」仍禁用；
     取消勾选再校验：提示消失 → 「保存草稿」（提示草稿已保存、库存未改变）→「确认加入菜谱库」变为可用，
     点击后显示「…」已加入菜谱库。
  5) 点「用当前条件重新推荐」→ 跳到「我的菜谱」推荐面板，出现「<该菜名> · 2 人份 · 现有库存足够」→
     「保存这餐方案」→ 已保存方案区出现该方案 →「确认做完」→ 模态里再点「确认做完」→
     提示已记录、库存同步更新。
  6) 刷新页面重新登录 →「我的菜谱」仍有该菜谱（持久化）→「食材库存」为 650 克（800−150）。
  另可试「丢弃」：丢弃草稿不改库存、不产生正式菜谱（e2e 第一条已断言这一点）。

测试：（数字见下节「F1 测试执行结果」，全部为本轮实跑）

模型：本轮真实模型请求 0 次，无 usage 数据（因为没有调用）。所有生成路径用脚本化 provider：
  backend/tests/test_recipe_discovery.py 内的 Scripted（含 usage 字段与故障注入）、
  browser_fixture --recipe-discovery（模型名 scripted-discovery-fixture）。
  预览环境 capabilities 实测 model_enabled:false，POST /recipe-discoveries 返回
  503 MODEL_NOT_CONFIGURED——未把 mock 通过写成真实生成通过。

偏差：
  1) 新增独立开关与预算：SOLOMEAL_RECIPE_DISCOVERY_ENABLED（默认 false）、
     SOLOMEAL_DISCOVERY_MAX_OUTPUT_TOKENS=3000、SOLOMEAL_DISCOVERY_TIMEOUT_SECONDS=30，
     不复用也不修改旧 Agent 全局预算（§3.4 要求）；compose.yaml 为此多写了三行透传。
  2) 「确认加入菜谱库」前的同名菜谱按 §3.3-7 处理为 warning（需勾选确认后才能加入），不是 error。
  3) 模型返回空候选数组记为 completed＋0 条草稿（可再次点击生成），不按技术失败处理；
     但「不是 JSON」「顶层结构不对」「非空条目全被结构校验丢弃」自 0922 修复轮起不再进入这一分支，
     而是 DISCOVERY_FAILED＋批次 failed，且不自动重试（R3）。
  4) 未配置模型时「生成候选」按钮禁用并给出说明，手工草稿入口始终可用（§3.1 的明确要求）。
  5) external 只作为预留来源类型，页面无入口、不宣称已接通搜索（§3.4）。
  6) 草稿编辑器 React key 用 draft.id（不含 version），避免服务端版本号回写导致重挂载清掉已输入内容
     ——沿用第98节同一类竞态的结论；e2e 打开发现页时先等待挂载 GET 落地再填写。
  7) 未做「打开菜谱发现」的 Agent 对话入口：§3.4 明确它不是 F1 完成门槛，本阶段按钮直连
     discovery service，Agent 的 recommend_meal 仍只读、未塞入付费调用。

遗留：
  阻塞：无。
  非阻塞 1：真实模型单次生成冒烟未执行——本批未获得真实调用预算授权（计划建议 ≤2 次调用）。
    接口/校验/入库逻辑已由脚本化 provider 与 API 测试覆盖；授权后最短路径：预览环境配好模型
    →capabilities 变 model_enabled:true→页面点一次「生成候选」。
  非阻塞 2：预览 MySQL 库中留有试用账号（f1preview_* 等）与其菜谱/库存/用餐记录，未清理以保持上面
    第 1～6 步可复查；口令不在本文档。0922 修复轮又新增 5 个一次性账号：最终通过的 2 个为
    f1r5_c5e3mi（数量上限）与 f1r1_c5e3mi（kg/l 页面复核），另外 3 个来自中途失败的三次尝试
    （驱动自身写错：错误响应体形状假设、账号未注册即登录、局部常量遮蔽全局 URL），
    只建了账号、食材种类与 1 份未丢弃的待核对草稿，没有正式菜谱、库存批次或用餐记录。
    均未使用既有用户数据，也未触碰 18080。
  非阻塞 3：未提交/未推送，因此远程 CI 未跑；改动只在工作树，审查如需可定位提交需先取得授权。
  非阻塞 4：源 18080 未重部署，不含 F1；替换源环境按用户当时授权执行。
  非阻塞 5：本轮未放宽任何超时、未预热首个导航；预览与 e2e 实跑未复现第99节记录的 30 秒导航停顿
    （该停顿根因按第99节口径仍保持未闭合，不在本轮追查范围）。

请求：请主审查 agent 复核 F1 的 R1～R6 修复（逐条改动与复测证据见文末「R1～R6 修复与复测」），
  并复查其未回归的原始重点：草稿确认的事务原子性与库存不变量、发现条件不可被自动放宽、
  未信任的模型文本过滤、跨用户隔离、迁移在 MySQL 上的字段兼容与 upgrade 结果；未开始 F2。
审查结论：
```

#### F1 测试执行结果

以下数字为 2026-09-21 首交付本机实跑，未放宽任何断言或超时；2026-09-22 修复轮的复测见其后同口径表。

| 项目 | 命令（在指定目录） | 结果 |
|---|---|---|
| 后端完整套件 | `cd backend && .venv/Scripts/python.exe -m pytest -q --basetemp=.tmp-pytest-f1-final2 -p no:cacheprovider --junitxml=...` | exit 0；575 通过 / 0 失败 / 0 错误 / 16 跳过（225.7s）。跳过项即既有的 MySQL 专属用例（本机未配 `SOLOMEAL_TEST_DATABASE_URL`），与本轮改动前同口径 |
| 发现模块单跑 | `... pytest tests/test_recipe_discovery.py` | 29 通过 / 0 失败（含本轮新加的回滚原子性用例）。0922 修复轮为 44 通过，见下表 |
| 后端 lint | `... -m ruff check <本次新增与修改的 .py> --ignore B008` | All checks passed。`app/api/discovery.py` 的 B008 与既有 `app/api/food.py`、`shopping.py` 完全同类（FastAPI `Depends()` 默认值惯用法），非本轮引入的新规则。未跑 `ruff format`：仓库既有文件本身不符合该格式（`app/api/food.py`、`app/services/planning.py` 会被重排），不作为本轮口径 |
| 前端单测 | `cd frontend && npm test` | 46 通过 / 0 失败（含 `tests/draft-validation.test.mjs`；脚本已把 draftValidation.ts 纳入 tsc 检查） |
| 前端构建 | `cd frontend && npm run build` | tsc --noEmit + vite 通过 → `dist/assets/index-DahiIrSg.js`；`npm run e2e` 再次构建得到同一内容哈希。0922 修复轮产物为 `index-Csm0Deym.js`，18088 首页现引用该文件（见下表） |
| 浏览器 e2e | `cd frontend && npm run e2e` | 22 通过 / 0 失败（101.5s，`--test-concurrency=1`）。新增 `e2e/recipe-discovery.test.mjs` 两条：脚本化 provider 的 生成→按字段报错→改名→保存→确认入库→重新推荐→库存零变化 全流程；无 provider 时生成入口关闭且手工草稿可校验保存。`e2e/mobile.test.mjs` 的 tab 清单已含「发现菜谱」 |
| 预览真实浏览器闭环 | 一次性 Playwright 脚本驱动 http://127.0.0.1:18088（脚本为临时工具，已删除，不入仓库） | 上面「用户试用」1～6 步全部通过，最终断言库存 650 克、重登后菜谱仍在、页面无 console/未捕获错误 |
| 预览 MySQL 读写闭环 | 页面＋API（httpx）对同一预览库 | 注册→建食材→手工草稿→校验→保存→确认入库→推荐→保存方案→确认做完→扣减 800→650 克→重新登录数据保持；另一用户读取该草稿 404。迁移 `a71f0d4c9b23` 已在该库执行（容器内 `alembic current` → head） |

##### 2026-09-22 R1～R6 修复后的针对性复测

按用户要求只重跑与改动相关的部分，未跑后端全套与 e2e 全套；未调用真实模型；未放宽任何断言或超时。

| 项目 | 命令（在指定目录） | 结果 |
|---|---|---|
| 后端发现模块 | `cd backend && TMP=/d/tmp/solomeal-pytest-f1 TEMP=... .venv/Scripts/python.exe -m pytest tests/test_recipe_discovery.py -q` | 44 通过 / 0 失败（44 个点、exit 0；较 0921 的 29 条多出 15 条，即 R1/R3/R4/R5 的新用例与参数化展开）。需重定向 TMP/TEMP：本机 `%LOCALAPPDATA%\Temp\pytest-of-xiaopeng` 目录 ACL 拒绝 scandir（`PermissionError [WinError 5]`，目录时间戳 09-14，与本轮改动无关），pytest 建 basetemp 即失败；按 AGENTS.md 既有口径未删未改其权限 |
| 后端 lint | `... -m ruff check app/services/recipe_discovery.py tests/test_recipe_discovery.py` | All checks passed |
| 前端单测 | `cd frontend && npm test` | 46 通过 / 0 失败（与 0921 同数，本轮未新增纯函数用例：R2/R6 属组件行为，见 e2e） |
| 前端构建 | `cd frontend && npm run build` | tsc --noEmit + vite 通过 → `dist/assets/index-Csm0Deym.js` |
| 发现页 e2e | `cd frontend && node --test --test-concurrency=1 --test-timeout=180000 e2e/recipe-discovery.test.mjs` | 4 通过 / 0 失败（10.6s）。原 2 条＋新增 2 条（R2 逐键输入、R6 第六批条件） |
| 双向验证（R2/R6） | 临时把 `DiscoveryPanel.tsx` 还原为修复前写法（备份后逐字符还原，sha256 `bea55030…` 已核对一致）→ 重新 build → 只跑两条新用例 | 两条均失败且失败签名即缺陷本身：厨具输入框得 `煮锅炒锅`（逗号被吞）、带最早批次条件的候选卡数 `0 !== 1`（批次映射被截断）。恢复修复版后重新构建回 `index-Csm0Deym.js`，4 条再次全绿 |
| 18088 重部署 | `docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait` | migrate 退出 0、api/web/db 三容器 healthy；容器内 `alembic current` → `a71f0d4c9b23 (head)`；`/health/live`、`/health/ready` 均 200；首页 HTML 引用 `assets/index-Csm0Deym.js`（确为修复轮产物） |
| 18088 页面级 R1 | 一次性 Playwright 脚本驱动真实 Chromium（脚本在 gitignored 的 `frontend/.tmp-e2e/f1-preview-0922.mjs`，不入库） | capabilities `model_enabled:false`（全程 0 次模型调用）；页面建 挂面(克)/生抽(毫升) 两种类→手工草稿填 0.5 千克 与 1 升→校验 errors=[]→保存→确认入库→「我的菜谱」显示 挂面 500 克、生抽 1000 毫升；API 侧同一菜谱存 `500.000 g`/`1000.000 ml`；页面无未捕获错误。截图 `frontend/.tmp-e2e/f1-r1-preview-0922.png`（gitignored）另显示手工草稿分支文案「这是手工草稿，重新推荐会按当前厨房偏好进行。」 |
| 18088 API 级 R5 | 同一脚本，账号 `f1r5_c5e3mi` | 100000000 克草稿：`/validate` 返回 `quantity_too_large`；`/accept` 返回 **422** `DRAFT_INVALID`，message 指向 `ingredients[1].quantity`（不再是 500）；食材与菜谱行数前后相等，随后丢弃草稿 |

未执行项与原因：
- 后端 575 项全套、e2e 22 项全套：**0922 修复轮未重跑**，按用户「不必重跑全部测试」只做针对性验证；
  当日实跑范围即上表（发现模块 44、前端单测 46、发现页 e2e 4、18088 页面与 API 复核）。
  全套是否需要在提交前重跑，由主审查 agent 决定。
- 真实模型生成冒烟（计划 §3.4 建议 ≤2 次调用）：**未执行**，本批未获得真实调用预算授权。预览 capabilities 实测
  `model_enabled:false`，接口返回 503 `MODEL_NOT_CONFIGURED`；所有生成路径均由脚本化 provider 覆盖，
  没有把 mock 通过写成真实生成通过。R3 的解析分支覆盖用 `httpx.MockTransport` 假传输完成，同样未调用模型。
- 远程 CI（GitHub Actions）：**未执行**，因为本轮未提交、未推送（需授权）。
- 源 18080 重部署：**未执行**，按 §12.1/§13 不属于本阶段，且需授权。
- 旧的 185 请求合成留出、9 轮 stress、30 秒首个导航根因：**未重跑、未追查**（§12.1 明确排除）。
  本轮 e2e 22 条与预览浏览器闭环均未出现该导航停顿；这只是「本轮未出现」，第99节口径下根因仍为未闭合，
  未放宽超时、未预热首个导航。
- 16 个 MySQL 专属后端用例在本机跳过：需要专用 `solomeal_test` 库，本机未配置，与既有基线一致。
- 预览 MySQL 上的 `alembic downgrade`：未实跑（避免打断可复查的预览），SQLite 夹具每轮实跑降级。

## F1 主审查（2026-09-22）

**结论：CHANGES_REQUESTED；F2 暂不放行。** 下面是功能内的具体缺陷，不新增研究型评估或多轮审计要求。开发agent只修这些问题，更新18088预览，针对性复测后重新交回审查。

### R1 / P1：kg/l 只换单位标签，数量没有换算

位置：`backend/app/services/recipe_discovery.py:134,343-360`。quantity_and_unit返回原数量与基础单位；recipe_input又用原数量配基础单位，原始kg/l已经丢失。

实际18088 API复现：草稿0.5kg校验errors=[]、确认200，正式菜谱为0.500g；1l同样变为1.000ml。真实Chrome页面也完成手工草稿→保存→确认→我的菜谱，显示「审查大米 0.5 克」。这会进一步影响推荐缺口和做饭扣减，不能放行。

最小修复：复用现有convert，在单位规范化时同步换算数量且只换算一次；新食材/已有食材都覆盖。复测0.5kg→500g、1l→1000ml及原生g/ml不变，至少一例确认后核对正式菜谱数量。

### R2 / P2：编辑器实时清洗吞掉逗号和换行

位置：`frontend/src/DiscoveryPanel.tsx` DraftEditor的厨具input与步骤textarea（约160～162行）。onChange立即split/trim/filter再join，刚输入的末尾分隔符被删除。

真实浏览器逐键复现：已有「煮锅」后输入「，炒锅」得到「煮锅炒锅」；已有「煮熟」后按Enter再输入「盛出」得到「煮熟盛出」。测试用一次fill粘入完整多行绕开了正常键盘行为，不能证明用户可编辑多个步骤。

最小修复：保留原始编辑字符串，保存/校验时再解析为列表。复测真实逐键输入逗号、Enter、两步内容，保存刷新后仍为两件厨具/两步，不只用fill完整字符串。

### R3 / P2：解析失败被标为成功的零候选

位置：`backend/app/services/recipe_discovery.py:481-507`（_candidates）及ModelDiscoveryProvider.generate。

纯函数实测：`not json`、`{}`、合法`{"candidates":[]}`全部返回[]。生产provider会把这三种都传给_finish，结果为completed，而计划要求技术解析失败有清楚错误。合法空数组可以成功，但无JSON/错误顶层结构/所有非空条目均被结构校验丢弃不能伪装成模型没有合适菜谱。

最小修复：区分合法空候选与解析/结构错误，后者走DISCOVERY_FAILED并保存failed状态；不自动重试。用httpx脚本化transport覆盖生产provider的响应解析即可，不需要真实模型调用。

### R4 / P2：模型库存上下文包含过期批次且漏加同食材库存

位置：`backend/app/services/recipe_discovery.py:167-183`。查询没有排除过期批次；按日期排完后seen只保留每种食材第一批数量，其余直接丢弃。

隔离内存数据库实测：同食材过期10g、有效200g、无到期日300g，inventory_context只返回10g。这样「优先使用现有库存」优先提供的是过期数据，且与正式recommend的有效库存500g不一致。

最小修复：按现有规划的日期口径先排除过期/归档/零库存，再按ingredient_id汇总；最多30种的限制施加在汇总后的食材集合，并按有效批次的最近到期日排序。复测上述例子应为500g，以及纯过期食材不进入上下文。无需调用模型。

### R5 / P2：草稿数量范围与正式RecipeItem不一致，确认返回500

位置：`backend/app/services/recipe_discovery.py:32,121-126,355-360`。草稿允许MAX_QUANTITY=99999999999.999，但正式Quantity为max_digits=11/decimal_places=3（最多8位整数）。

实际18088 API复现：1000000000g的草稿校验errors=[]，确认返回500 Internal Server Error，用户看不到可修正的数量字段提示。

最小修复：在validate_payload阶段复用正式字段约束，并检查换算后的基础数量可保存；确认路径不能让这类ValidationError变成500。测试输入上限附近、换算后越界，要求返回字段错误且不留下新食材/正式菜谱。

### R6 / P2：第六个及更早批次的草稿会丢失重新推荐条件

位置：`frontend/src/DiscoveryPanel.tsx:54,118`。待办草稿读取全部，但batches只保留recent.slice(0,5)。确认较早批次草稿时batchOf查不到，added.constraints=null；main.tsx的recommendWith(null)回退当前厨房偏好，而非原发现条件。

这是可确定的代码路径，尚未用真实模型制造六批重现。例：旧批次要求1人/15分钟，当前偏好2人/30分钟，确认旧草稿后会用后者重新推荐，违背「条件不会被自动放宽」文案。

最小修复：最近5条仅用于历史展示，保留完整batch映射，或按draft.batch_id获取详情后再推荐；详情读取失败不能静默回退。用脚本化provider创建6批、保留最早草稿，断言点击重新推荐发出的请求仍为最早批次条件。

### 本次实际审查范围与保留项

- 阅读主要服务/API/Schema/迁移/前端代码及开发交接的测试结果；没有重跑575项后端或22项E2E，不将开发报告数字称为主审查复跑结果。
- IAB和node_repl工具因kernel assets路径错误不能初始化，改用本地Playwright驱动真实Chrome访问18088。最终页面操作从注册、手工编辑到正式菜谱展示跑通，逐键输入与数量错误在真实页面复现。中间两次审查脚本因标签定位失配超时，改用稳定textarea/select定位后通过；不归因于应用首导航flake。
- 实际预览API验证R1/R5；纯函数验证R3；隔离内存数据库验证R4；R6为代码静态确认。审查真实模型请求0，无新增费用。
- 18088新增少量review_f1_*/review_api_*专用审查账号和菜谱/草稿，未使用现有用户数据；没有新增库存批次或做饭扣减，未触碰18080。审查截图在gitignored的frontend/.tmp-e2e/f1-review-0922.png，临时驱动位于系统Temp，不纳入提交。
- 本次仅修改执行记录，未代开发agent修复应用代码、未提交、未部署。修复后只需针对上述问题与受影响主流程复测，不要求多轮全套测试。
- 真实模型冒烟未授权、远程CI未跑，均不是本次退回原因。继续如实标记即可；不能在修复期间偷偷调用模型。

## R1～R6 修复与复测（2026-09-22，开发 agent）

只改上述六处与它们的测试驱动；未开始 F2；真实模型请求 0 次；未提交、未推送；源 18080 未动。
下表「复测」一列写的是**实际执行过的断言**，不是「应当如此」的推断。

| 问题 | 改动 | 复测（本轮实跑） | 结果 |
|---|---|---|---|
| R1 kg/l 只换标签 | `recipe_discovery.py:103-149` `quantity_and_unit` 改为返回**基础单位下的数量**：单位规范化后调用一次既有 `food.convert`（`app/services/food.py`），与正式菜谱入库走同一把换算；原先「只把 unit 换成 g/ml、数量原样带走」的分支删除 | 后端 `test_kilograms_and_litres_are_converted_once_into_the_stored_base_unit`：0.5 千克→500 克、1 升→1000 毫升，120 克／250 毫升／2 个原样不变；既断言 `/validate` 返回的换算计划，也断言确认后**正式菜谱里存的数值** | 通过。另在 18088 真实页面走「手工草稿 0.5 千克＋1 升→校验→保存→确认→我的菜谱」，页面显示 500 克／1000 毫升，API 侧存 `500.000 g`／`1000.000 ml` |
| R2 编辑器吞逗号/换行 | `DiscoveryPanel.tsx:146,159-160,174,176`：新增 `raw` 状态保存键盘原始文本，输入框/文本域绑定 `raw`；`words()`/`lines()` 只在生成待校验、待保存的 payload 时解析（`lines` 为本轮新增的按行解析） | e2e 新用例「逐键输入厨具与步骤」：`pressSequentially('煮锅')`＋`pressSequentially('，炒锅')` 后断言输入框仍为 `煮锅，炒锅`；`pressSequentially('水开下面')`＋`press('Enter')`＋`pressSequentially('盛出')` 后断言仍为两行；保存后读服务端 payload `equipment=['煮锅','炒锅']`、`steps=['水开下面','盛出']` 且 `validation_errors=[]`；切到「我的菜谱」再切回来（组件重挂载）断言两个字段仍是两项 | 通过。双向验证：还原修复前写法重新构建，同一用例得到 `煮锅炒锅`，即失败签名就是缺陷本身 |
| R3 解析失败伪装成零候选 | `recipe_discovery.py:508-538` `_candidates`：顶层不是 `{candidates:[...]}`、或条目非空但全部被结构校验丢弃时 `raise ValueError`，由 `ModelDiscoveryProvider.generate` 既有边界转成 `AppError(502,"DISCOVERY_FAILED")`，`start()` 落批次 `failed`；合法 `{"candidates":[]}` 仍返回 `[]`→completed。未新增任何自动重试 | 后端 `test_a_malformed_answer_is_never_reported_as_an_empty_result`（8 个参数化输入：散文、`{}`、顶层数组、`candidates` 非数组、每行都被丢弃、行不是对象、无 content 等，逐个断言抛错）＋`test_the_production_provider_separates_an_empty_answer_from_a_broken_one`（`httpx.MockTransport` 假传输驱动**生产 provider**：合法空→201/completed/usage 18/0 草稿；三种坏答案→502 `DISCOVERY_FAILED`、批次 `failed`、`error_code` 已记、`usage is None`；同幂等键重放后 `len(calls)==1`，证明确实没有自动重试） | 通过。原 `test_generated_text_is_filtered_to_the_fields_the_service_reads` 中现已抛错的样例移出，保留其字段过滤职责 |
| R4 库存上下文含过期且漏加 | `recipe_discovery.py:181-212` `inventory_context` 重写：SQL 先按 `archived is false`、`quantity>0`、`expires_on` 为空或 `>=today` 过滤（与 `planning.py` 同一日期口径），再在 Python 侧按 `ingredient_id` 汇总数量、取有效批次中最近到期日，30 种上限施加在**汇总后**的集合上并按「有到期日优先、日期早优先」排序 | 后端 `test_inventory_context_sums_the_batches_a_meal_can_actually_use`：同食材过期 10 克＋有效 200 克＋无到期日 300 克→**500 克**；纯过期食材完全不出现在上下文里；已归档批次经 `POST /inventory/{id}/archive` 后同样被排除；排序断言 青菜(明天) 早于 大米(5 天后)；上下文字段仍只有 `{name,quantity,unit}` | 通过。未调用模型 |
| R5 草稿数量范围与正式表不一致 | 删除草稿侧自定的 `MAX_QUANTITY`；`recipe_discovery.py:36-40,143-147` 改为按**换算后的基础数量**对照正式字段上限 `MAX_BASE_QUANTITY=99999999.999`（即 `schemas.food.Quantity` 的 11 位精度/3 位小数），超限记 `quantity_too_large` 字段错误并指向具体行；`errors=[]` 才可能进入确认，故确认路径不再出现 500 | 后端 `test_a_draft_quantity_stops_where_the_recipe_field_ends`：99999999.999 克通过、100000000 克报 `ingredients[1].quantity/quantity_too_large`、99999.999 千克通过、100000 千克（换算后越界）报错；对已存于库中的超限草稿直接调确认→422，且食材行数与菜谱行数前后不变。18088 预览 API 复核：`/validate` 报 `quantity_too_large`、`/accept` 返回 **422** `DRAFT_INVALID`（message 指向 `ingredients[1].quantity`）而非 500，未留下食材或菜谱 | 通过 |
| R6 第六批草稿丢失条件 | `DiscoveryPanel.tsx:57,106`：`batches` 保留服务端返回的**完整**批次列表（`session.ts` 的 `pagedList` 已登记该列表，本就是全量分页读取），`slice(0,5)` 只留在历史展示处；`:127-135`「加入之后」按三种情况分支——手工草稿（说明按当前厨房偏好）、批次条件在（显示该批次的 人数/用时并沿用）、条件读不到（`role="alert"` 明确报错并**禁用**按钮，不再静默回退偏好） | e2e 新用例「确认第六批之前的草稿后，重新推荐仍带该批次保存的条件」：脚本化 provider 建 6 批（第 1 批 1 人/15 分钟，后 5 批 2 人/20 分钟，厨房偏好 2 人/30 分钟）→断言历史只展示 5 条而最早那批的候选卡仍在待核对列表并显示其自身条件→确认入库→捕获「用当前条件重新推荐」实际发出的 `POST /recommendations` body：`servings===1`、`max_minutes===15`、`equipment===['煮锅']` | 通过（6 批各登记一次、页面无未捕获错误）。双向验证：还原 `slice(0,5)` 后同一用例断言「带最早条件的候选卡数」得 `0 !== 1` 而失败 |

测试驱动侧的两处必要修正（不改断言强度，只改时序与定位）：
1. 面板在 `run()` 的 `finally` 里比列表渲染晚一个 render 才清 `busy`，单次 `isDisabled()===false` 读取可能抓到「因 busy 而禁用」。本轮首跑该文件出现的 3 次失败里，1 条既有用例与 R6 新用例各栽在这一处（把该文件原样复制成临时探针单独重跑即通过，可确认是时序而非应用行为）。新增 `waitEnabled()` 轮询（最多 10 秒），三处「按钮应变为可用」的断言改用它；「按钮应保持禁用」的断言未动。
2. Chromium 对包裹 `<textarea>` 的 `<label>` 计算可访问名时会把文本域内容折进名字，逐键输入后 `getByLabel('做法（每行一步）',{exact:true})` 不再匹配（首跑第 3 次失败即此；主审查记录里也出现过同类失配）。步骤框改用 `draft.locator('textarea')`（该组件内唯一 textarea）。

该 e2e 文件本轮实跑 4 次：修好上面两点后首跑 3/4（唯一失败是我在 `waitForRequest` 谓词里误写 `r.request().method()`，Playwright 的 Request 对象本身就有 `.method()`，属驱动笔误）→ 修正后 4/4 → 为双向验证把前端还原成修复前写法重跑，两条新用例按预期失败 → 恢复并重建后再跑，4/4。未放宽任何超时、未预热首个导航。

保留项（修复轮不改变其状态）：真实模型单次生成冒烟仍未授权、未执行；远程 CI 仍未跑（未提交/未推送）；
源 18080 未重部署；「条件读不到即停用」这条防御分支没有自动化用例覆盖（面板级组件在本仓库无组件测试harness，
且该分支要求批次列表缺项而草稿仍在，正常路径下 `pagedList` 读取失败会先整体报错）。

## F1 主审查复核通过（2026-09-22）

**APPROVED：R1～R6全部收口，可以开始F2。** 本次没有发现这些修复中的新阻塞问题；不要求继续追加全套测试或重复审计。

主审查实际执行：

- 在18088用真实Chrome重新运行上轮相同的页面复现流程：逐键输入得到「煮锅，炒锅」与「煮熟\n盛出」；手工草稿0.5kg→校验→保存→确认→正式菜谱页面显示500克。
- 重新运行上轮预览API复现：0.5kg保存500.000g，1l保存1000.000ml；1000000000g现在校验报quantity_too_large、确认422 DRAFT_INVALID，不再500。
- 针对R3/R4执行 `pytest tests/test_recipe_discovery.py -q -k 'production_provider_separates or inventory_context_sums'`（系统Temp中新建独立basetemp、禁用cacheprovider）：5项通过，保留两条既有依赖弃用警告。验证生产provider经MockTransport区分合法空数组/坏响应，以及有效批次数量汇总与过期排除；真实模型请求0。
- 核对R6完整batch映射、最近5条仅用于展示及缺条件时禁止推荐的代码；读取六批次浏览器回归，其断言覆盖实际POST /recommendations的1人/15分钟/煮锅条件。本次未重复运行该e2e，用开发agent已报告通过结果和修复代码完成复核。
- HTTP实读18088首页引用index-Csm0Deym.js，/health/ready返回200。未重建、未改部署、未接触18080。

开发报告中的44项后端、46项前端、4项e2e不冒称本次主审查全量复跑。新增少量review_f1_*/review_api_*审查账号/菜谱留在独立预览库；未创建库存批次或做饭扣减。仅更新交接状态，应用代码未代改。

保留：真实模型生成端到端冒烟尚未执行，不能写为通过；远程CI未跑、改动未提交。以上保持可见，但不作为F2开发阻塞。F2仅按计划实现收藏/反馈/烹饪标签及可操作页面，完成后再次交回主审查，不自动推进F3。

## F2 收藏、喜欢/不喜欢反馈与烹饪方式标签（2026-09-22，开发 agent）

```text
阶段：F2；状态：READY_FOR_REVIEW
基线/结果：base commit 3ca1976；本轮未创建提交（提交/推送需授权）。F1 的改动同样仍在工作树，
  因此 `git status --porcelain` 显示的是 F1＋F2 合计（21 个已跟踪文件修改＋17 个新增路径，
  即 F1 记录的 12 个加 F2 的 5 个）。
  F2 自身范围可逐文件定位：7 个已跟踪文件 +252/−41 行
  （backend/app/models/food.py +23、app/schemas/food.py +26/−1、app/services/food.py +128/−30、
  app/api/food.py +20/−2；frontend/src/main.tsx +33/−6、src/style.css +21/−1、package.json +1/−1）；
  5 个 F2 新文件共 629 行（迁移 34、后端测试 376、src/cookingMethods.ts 27、
  tests/cooking-methods.test.mjs 37、e2e/recipe-feedback.test.mjs 155）；
  另有 6 个「F1 新增（未跟踪）文件」里的 F2 改动：backend/app/schemas/discovery.py、
  app/services/recipe_discovery.py、frontend/src/DiscoveryPanel.tsx、src/draftValidation.ts、
  frontend/e2e/recipe-discovery.test.mjs、frontend/tests/draft-validation.test.mjs。
  本轮未在仓库里留下临时目录：pytest 的 basetemp/junit 都指到仓库外的 `D:/tmp/solomeal-f2/`（该目录仍在，
  上表 604/0/16 与 444.7s 即从其 junit 读出，可离线复核）；仓库内唯一新增的运行时文件是 gitignored 的
  一次性预览脚本 `frontend/.tmp-e2e/f2-preview-0922.mjs` 与其 1 张截图（沿用 F1 的 `.tmp-e2e` 口径，`.gitignore:29` 的 `.tmp-*` 覆盖）。

变更：功能＝每账号一条菜谱评价（收藏 + 喜欢/不喜欢/中性，两者互不影响）＋ 菜谱烹饪方式标签
  （8 个枚举、每道最多 3 个、只由人工选择），评价与标签都在页面即时可见、刷新后仍在；
  删除菜谱只清该菜谱的评价行，不动用餐/做饭快照；本阶段不改任何排序。
  新增主要文件：backend/migrations/versions/b52e9c4a7d18_recipe_feedback.py、
  backend/tests/test_recipe_feedback.py、frontend/src/cookingMethods.ts、
  frontend/tests/cooking-methods.test.mjs、frontend/e2e/recipe-feedback.test.mjs。
  改动主要文件：backend/app/models/food.py（RecipeFeedback 表＋Recipe.cooking_methods）、
  app/schemas/food.py（CookingMethod 枚举与去重/上限校验、RecipeFeedbackInput）、
  app/services/food.py（set_feedback/get_feedback/feedback_map、recipe_view 带标签、删除时清评价）、
  app/api/food.py（GET/PUT /recipes/{id}/feedback，列表与详情内嵌 feedback）、
  app/schemas/discovery.py＋app/services/recipe_discovery.py（草稿标签读写与字段级报错）、
  frontend/src/main.tsx（卡片收藏/喜欢/不喜欢/清除评价、只看收藏筛选、编辑器标签多选）、
  src/DiscoveryPanel.tsx（草稿标签多选＋词表外写法的移除入口）、
  src/draftValidation.ts（3 个新错误码中文）、src/style.css、package.json（tsc 清单）。
  迁移名：b52e9c4a7d18（recipe_feedback：新表 recipe_feedback＋索引，recipes 增
  cooking_methods JSON 可空列）。upgrade 已在预览 MySQL 执行（`alembic current` → head）；
  downgrade 路径每轮在 SQLite 测试夹具里实跑（conftest 结束降级到 base），未在预览 MySQL 实跑。
  后端 API 兼容性：只新增字段与新端点，既有请求/响应形状未改。

预览：http://127.0.0.1:18088（独立 Compose 项目 solomeal-features-0921，自有 MySQL 数据卷与
  小票上传卷，未引用源 18080 的任何卷；源 18080 至今未动，仍是第98节的 index-xzzr0Hjd.js）。
  实际构建：页面里唯一加载的 `assets/index-*.js` 为 index-CbHSzxJh.js（本轮 npm run build 产物，
  取代 F1 的 index-Csm0Deym.js），且首页 HTML 的 script 标签引用同一文件名——即页面确实跑新前端，非仅容器 healthy。
  健康：web/api/db 三容器 Up (healthy)，GET /health/live 与 /health/ready 均 200；
  容器内 `alembic current` → b52e9c4a7d18 (head)。
  启动/重部署：docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env
        -p solomeal-features-0921 up -d --build --wait   （本轮即以此命令重建 api/web 并 --wait 到 healthy，
        migrate 一次性容器退出码 0）
  停止：docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env
        -p solomeal-features-0921 stop   （卷保留，数据不丢）
  凭据只在该私有 env 文件里，未提交、不写入本文档。
  登录说明：预览允许自助注册，用页面「第一次使用？创建账号」填任意用户名与自己定的口令即可，
  无需邀请码；本文档不记录任何口令。

用户试用（下列 6 步已用真实 Chromium 在 18088 逐步跑通，脚本与实测断言见下节「F2 测试执行结果」最后一行）：
  1) 注册一个新账号 → 进「我的菜谱」：网格显示新账号的空态，看不到别人的菜谱
     （评价与标签都按账号隔离，这一步同时确认新账号评价起点为空）。
  2) 「食材库存」→ 名称「鸡蛋」、单位「个」→「添加种类」：食材下拉出现「鸡蛋（个）」。
  3) 「我的菜谱」→「添加自己的菜谱」→ 填名称/厨具/做法/一行鸡蛋，在「烹饪方式（最多 3 个，
     用于以后筛选）」里勾「炒」「煮」→「保存菜谱」：新卡片标题下出现两枚中文标签「炒」「煮」，
     编辑器里「已选：炒 / 煮」；再建第二道不勾标签的菜谱，该卡片不出现标签行。
  4) 在第一道卡片上点「收藏」：按钮变「已收藏」并填充、下方出现
     「评价已保存（版本 1）。本阶段推荐排序不使用评价。」；依次点「喜欢」→「不喜欢」→
     只有「不喜欢」呈按下态（换评价是替换，不是同时选中）；点「清除评价」→ 清除入口消失、
     收藏仍是按下态（评价与收藏互不牵连）。
  5) 「发现菜谱」→「手工新建草稿」→ 填名称/人数/用时/厨具/做法/一行鸡蛋，勾「煮」「炖」→
     「按当前填写校验」显示 errors 为空 →「保存草稿」（草稿已保存，库存未改变）→
     「确认加入菜谱库」→ 提示已加入；切到「我的菜谱」，该卡片直接显示「煮」「炖」。
     另有一种情形不在预览里、而在离线 e2e 里实测：草稿被页面外部写入词表外写法（`PUT /recipe-drafts/{id}`
     存 `deep_fry`）时，页面把它显示在「无法识别的写法需要改成上面的标签」里并给「移除」按钮，
     移除前「确认加入菜谱库」保持禁用，移除并保存后即恢复可用（见 e2e 第 5 条）。
  6) 勾「只看收藏」→ 网格只剩已收藏那道；取消勾选恢复全部 → 刷新页面重新登录 →
     收藏与评价仍是按下态（来自服务端，不是内存残留）。另一账号读/写这两道的评价均 404。

测试：（数字见下节「F2 测试执行结果」，全部为本轮实跑）
模型：本阶段真实模型请求 **0 次**，无 usage 可报；未使用真实生成。所有草稿路径由页面「手工新建草稿」
  与 F1 的脚本化 provider 覆盖；R3 那类解析分支用 `httpx.MockTransport` 假传输，同样不调用模型。
  计划 §3.4 的单次生成冒烟仍需具体预算授权后才做，本轮未申请、未执行，也没有把 mock 写成真实生成通过。

偏差：
  1. 「0–3 个去重值」实现为**重复即 422 拒绝**（`cooking_method_duplicate`），不静默去重——
     与仓库既有「同名冲突拒绝而非合并」的规则一致；页面复选框本身也无法重复勾同一项。
  2. 「重复同一状态不得累积」实现为：一人一道只有一行评价（唯一约束 `uq_feedback_recipe`），
     换评价是整状态替换；每次 PUT 仍按既有 `expected_version` 机制把 version +1（同键同请求幂等重放除外），
     即「不累积」指不产生第二条记录、不出现两个按下态，而非版本不变。实测 4 次保存 → version 4。
  3. 评价**不写进** `recipe_view`，因此做饭/方案快照里不含评价（只含标签）：快照是当时的菜谱事实，
     不该把某账号的私有偏好冻进去；列表与详情才内嵌 `feedback`。
  4. 标签是**人工专属**affordance：`candidate_schema()` 里弹出该属性、`CANDIDATE_FIELDS` 不含它，
     所以模型文本里的 `cooking_methods` 一律丢弃 → `PROMPT_VERSION` 仍为 `recipe-discovery-v1`，
     不宣称模型能产出标签（计划「不由模型自动补历史标签」的更强口径：模型根本读不到也写不进）。
  5. 词表外的存量写法不静默丢弃：草稿侧按 `Text` 存、按字段问题报 `cooking_method_invalid`，
     页面显示原文并给「移除」，改完才能入库——避免外部写入被悄悄抹掉。

遗留：
  阻塞项：无。
  非阻塞 1：保存评价后卡片状态就地更新（不重拉列表）。若同一时刻有一个更早发出的 `/recipes` 响应晚落地，
    理论上会瞬时显示旧评价，下一次刷新以服务端为准；本轮未为此写自动化用例（服务端是唯一真源）。
  非阻塞 2：`plans.state()` 现在内嵌 `cooking_methods`，故 F2 之前创建的 pending 方案会被判为「菜谱已更新」
    一次，走既有「按当前库存更新」即恢复。**这条是代码路径推断，不是实测**：预览库里确有 1 条 pending
    `meal_plan`，但其所属账号口令从未保存，无法在页面复现该流程。若主审查认为需要实测，请给可复现账号或授权新建。
  非阻塞 3：预览 MySQL 上未实跑 `alembic downgrade`（不打断可复查的预览）；SQLite 夹具每轮实跑降级到 base。
  非阻塞 4：16 个 MySQL 专属后端用例本机跳过（需专用 `solomeal_test` 库），与既有基线一致。

未执行项及原因：
  - 远程 CI（GitHub Actions）：未提交、未推送（需授权），故未跑。
  - 源 18080 重部署：不属本阶段（§12.1/§13），且需授权。
  - 真实模型生成冒烟：未获本批调用授权，未执行。
  - 9 轮 stress 多轮重跑与 30 秒首个导航根因：第99节明确排除，未重跑、未放宽超时、未预热首个导航。
    本轮 e2e 27 条与预览浏览器闭环未出现该停顿——这只是「本轮未出现」，根因仍为未闭合。

请求：请主审查agent审查 F2；未开始 F3。
审查结论：
```

#### F2 测试执行结果

以下数字为 2026-09-22 本机与 18088 预览实跑，未放宽任何断言或超时。

| 项目 | 命令（在指定目录） | 结果 |
|---|---|---|
| 后端完整套件 | `cd backend && TMP=/d/tmp/solomeal-f2 TEMP=... .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --junitxml=D:/tmp/solomeal-f2/junit-f2.xml` | exit 0；604 通过 / 0 失败 / 0 错误 / 16 跳过（444.7s）。跳过项即既有 MySQL 专属用例（本机未配 `SOLOMEAL_TEST_DATABASE_URL`），与改动前同口径 |
| 新增反馈模块 | `... pytest tests/test_recipe_feedback.py` | 14 通过 / 0 失败。覆盖：零起点与整状态替换、猜错 expected_version→409、同键同请求重放/同键不同请求冲突、跨用户读写 404 与复合外键、删菜谱清本菜谱评价而做饭快照仍留 `["boil"]`、标签经编辑与做饭后仍在、词表外/重复/超 3 个的 422、旧行 NULL 读 `[]`、列表内嵌评价只多 1 次查询、排序未变、模型文本里的标签被丢弃、草稿带问题标签不能入库 |
| 后端 lint | `... -m ruff check --select F,I <本轮 8 个新增/修改 .py>` | All checks passed。`--select` 按仓库 `pyproject.toml`（F,B,I）另跑时，`app/api/food.py` 报 49 处 B008——全部是既有 FastAPI `Depends()` 默认值惯用法、改动前后同类，且 ruff 依 AGENTS.md 口径**不是** CI 门槛；其余 7 个文件 B 亦干净。未跑 `ruff format`（仓库既有文件本身不符合） |
| 前端单测 | `cd frontend && npm test` | 50 通过 / 0 失败（含 tsc 显式清单已纳入 `src/cookingMethods.ts`；新增 cooking-methods 3 条、draft-validation 1 条） |
| 前端构建 | `cd frontend && npm run build` | tsc --noEmit + vite 通过 → `dist/assets/index-CbHSzxJh.js` |
| 浏览器 e2e 全套 | `cd frontend && npm run e2e` | 27 通过 / 0 失败（136.9s，`--test-concurrency=1`，含构建）。新增 `e2e/recipe-feedback.test.mjs` 2 条（桌面：标签中文显示、收藏/喜欢/不喜欢/清除、跨账号 404、重登仍在、只看收藏筛选、做饭后删菜谱→评价 404 而用餐记录仍可读且撤销按快照恢复 6 个；窄屏 390px：零横向溢出、无 <40px 可点按钮、标签与按钮不挤破版面）；`e2e/recipe-discovery.test.mjs` 追加第 5 条（草稿选标签→入库→卡片显示；词表外写法留在原处可移除，移除前不能入库） |
| 18088 重部署 | `docker compose --env-file .../preview.env -p solomeal-features-0921 up -d --build --wait` | migrate 退出 0、api/web/db 三容器 healthy；`alembic current` → `b52e9c4a7d18 (head)`；`/health/live`、`/health/ready` 均 200；首页 HTML 引用 `assets/index-CbHSzxJh.js` |
| 18088 旧数据读取 | 容器内只读探针（不写库） | 11 条 F2 之前的菜谱 `cooking_methods` 全部读作 `[]`、feedback 读作 `{favorite:false,rating:neutral,version:0}`；列表批量评价一次查完（`feedback_map` 返回 `{}`）。迁移后 MySQL 列实测：`recipes.cooking_methods` = json / NULLABLE=YES；`recipe_feedback` 列 = favorite,id,rating,recipe_id,updated_at,user_id,version |
| 18088 真实浏览器 6 步 | 一次性 Playwright 脚本驱动真实 Chromium（脚本在 gitignored 的 `frontend/.tmp-e2e/f2-preview-0922.mjs`，不入库） | 上面 1～6 步全部通过：产物断言（页面加载的 `index-*.js` 恰为 index-CbHSzxJh.js 且与首页 HTML 一致）、capabilities `model_enabled:false`（全程 0 次模型调用）、页面未捕获错误 0；服务端整状态实测 `[['预览挂面',['boil','stew'],false,'like',1],['预览煮蛋',['stir_fry','boil'],true,'neutral',4]]`；另一账号读/写评价均 404；重登后按下态仍在。截图 `frontend/.tmp-e2e/f2-preview-0922.png`（gitignored，1 张）显示两枚标签、已收藏/喜欢填充态与「只看收藏」说明行 |

该预览脚本实跑 3 次：前 2 次分别断言在**我自己脚本的定位假设**上（第 1 次在「发现菜谱」tab 上查菜谱卡片选择器、第 2 次假设卡片标题是 h3，实际是 h2），
不是应用缺陷；第 3 次全通过即上表结果。两次失败的运行在预览库里各留下一个一次性账号与其数据，
故当前预览库实测为 24 用户 / 17 菜谱 / 5 评价行 / 6 道带标签菜谱 / 23 草稿 / 1 条 pending 方案
（F1 与主审查账号也在同一库里，「F1 主审查复核通过」一节已记录该类留痕）。未删改他人数据。


## F2 主审查通过（2026-09-22）

**APPROVED：可以开始F3（做饭模式与实际耗时），F3尚未开始。** 未发现本阶段阻塞问题，不追加全套重跑或新的审计任务。

- 核对反馈表/迁移、GET/PUT、用户锁、版本/幂等、删除关联反馈、标签校验、前端收藏/评价；收藏与rating独立，反馈未写入业务快照，未接入排序。
- 阅读并复用开发agent的18088页面脚本，仅在系统Temp副本调整import与本机Chrome启动通道，实跑注册→带标签菜谱→收藏/喜欢/不喜欢/清除→草稿标签入库→收藏筛选→重登持久化，全部通过。产物index-CbHSzxJh.js、model_enabled=false、页面异常0；另一账号GET/PUT评价均404。新增审查账号f2_cgv06l及专属数据留在预览库，未改他人数据。
- 实跑 `pytest tests/test_recipe_feedback.py -q -k 'deleting_a_recipe or guessed_version or idempotent_per_key'`，独立Temp basetemp、无cacheprovider：3项通过，保留2条既有依赖弃用警告。覆盖版本冲突、同键重放/异请求冲突、删菜谱清评价而做饭快照可读。
- 未重复开发报告的604后端/50前端/27浏览器全套，不将其数字称为主审查复跑结果。真实模型0请求、未提交推送/部署，18080未动；仅改交接文档。

保留：旧pending快照缺标签字段，确认时可能PLAN_STALE，需用户“按当前库存更新”后再确认；这是代码核对，未在迁移前真实方案页面实测，不声称自动更新。更早列表响应覆盖刚保存反馈的窗口未复现，保留非阻塞风险。词表外标签离线e2e由开发agent实跑，本次未在18088重复注入。真实模型冒烟与远程CI未执行，不阻塞F3。

下一步仅执行F3，交付可操作步骤模式、暂停/继续、结束确认及实际用时填写/修改，复用原库存事务；完成后停在READY_FOR_REVIEW，不自动做F4。


## F3 做饭模式与实际耗时（2026-09-22）

**阶段：F3；状态：APPROVED。** 主审查已完成；可以开始F4，不能自动跳过F4审查进入F5。

### 实现与范围

基线为HEAD `3ca1976` 加领取时已有的F1/F2未提交工作树，本阶段也未提交推送。不是干净HEAD构建，不能把全部git diff算作F3。

- 菜谱卡片和推荐卡片增加“开始做饭”，可选人数/可选食材，显示换算用量、步骤号、完成勾选、上/下一步、总计时、暂停/继续、结束确认。用量用十进制整数运算向上取整，遵循服务端g/ml千分位、piece整数规则。
- 计时按accumulated_ms加当前运行区间计算，interval只刷新显示；按user_id/recipe_id/version存localStorage，不存token。刷新登录后提示恢复/丢弃，运行中后台时间计入、暂停时间不计；退出登录/会话失效清该用户草稿。界面明确仅支持单标签页。
- 结束先暂停，默认max(1,ceil(ms/60000))，允许1～480整数或不记录；超界提示手工修正、不截断。改过输入则source=manual，否则timer；无值则source=null。
- 确认复用food.cook/run_operation库存事务。新增可选expected_recipe_version，阻止菜谱变动后静默改用新用量；库存不足/版本错误保留计时和步骤。用户可读取核对最新版，再显式选择保留计时、重置步骤后继续。
- 网络错误时持久化提交正文与原operation_key，重试同一次确认；结果未确定前锁定正文。成功才清草稿、显示用餐记录。原“记录做完这道菜”与方案确认按钮继续可用，默认用时为空。
- CookingRecord新增actual_minutes/duration_source/feedback_version，默认null/null/1；CookingInput与ConfirmPlanInput接收用时；PUT /cooking/{id}/duration带expected_version和Idempotency-Key，只改反馈，不改created_at、快照、库存或事件。历史可填写/修改/清空；撤销后展示旧用时但禁止修改。

新增6文件：backend/migrations/versions/c63a1e7d9f20_cooking_duration.py、backend/tests/test_cooking_duration.py、frontend/src/CookingMode.tsx、frontend/src/cookingTimer.ts、frontend/tests/cooking-timer.test.mjs、frontend/e2e/cooking-mode.test.mjs。

修改（部分已有F1/F2改动）：backend/app的models/food.py、schemas/food.py、schemas/planning.py、services/food.py、api/food.py、api/planning.py；frontend/src/main.tsx、style.css、frontend/package.json；本交接及AGENTS/CLAUDE/NEXT_SESSION入口状态。不实现个人耗时估计或推荐排序改变。

### 预览与试用

URL：**http://127.0.0.1:18088**。独立项目solomeal-features-0921，保留现有预览数据库/图片卷，没有清库。最终工作树构建为`index-LtnRZllD.js` / `index-Bbm6Tqri.css`，真实Chromium已断言script与本地dist一致。

migrate退出0，api/web/db均healthy；alembic current=`c63a1e7d9f20 (head)`，live/ready均200。SQLite夹具逐用例执行升降级；未在保留用户数据的预览MySQL运行降级。源18080未部署，只读核对仍加载`index-xzzr0Hjd.js`。

部署：`docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait`；停止用同前缀`stop`，不删卷。凭据留在原私有配置，不写入文档。登录可用原账号，或页面“第一次使用？创建账号”自助注册。

试用：
1. 准备一条定量菜谱及足够库存，在“我的菜谱”或推荐卡片点“开始做饭”，选择人数/可选食材，再点“开始步骤与计时”。
2. 勾当前步骤、切换上/下一步，暂停后等待数字不变，继续后重新计时；库存和用餐记录不变。
3. 刷新并登录，点“继续未完成做饭”恢复原步骤与计时；也可退出并保留计时去补库存。
4. “结束并确认做饭”检查实际分钟，可改写或不记录，再“确认做饭并扣库存”，成功进入用餐记录。
5. 在记录中填写/修改用时，保存只改变用时；留空可清除。
6. 撤销并恢复食材，库存恢复、用时展示但不能修改。仅浏览/计时不必完成，可退出或丢弃。

### 实际验证

| 项目 | 命令/范围 | 结果 |
|---|---|---|
| F3后端 | backend/.venv/Scripts/python.exe -m pytest backend/tests/test_cooking_duration.py -q -p no:cacheprovider --basetemp=.tmp-f3-pytest | 10通过：范围/成对字段、同键重放/异请求冲突、一次扣减、修改清空无业务写入、版本/账号隔离、库存失败回滚、撤销拒改、旧调用null、plan confirm传递用时 |
| 相关后端 | 同解释器pytest test_food.py、test_planning.py、test_recipe_feedback.py，basetemp=.tmp-f3-regression | 25通过/2跳过，共收集27；跳过两项需专用MySQL库的并发做饭测试；保留两条既有依赖弃用警告，非全套 |
| lint | ruff check --select F,I 本阶段8个.py | 通过；新增import排序提示已修复 |
| 前端单测 | npm --prefix frontend test | 53通过；新增3条验证2分运行+5分暂停+3分运行=5分、取整/超界/时钟倒退、十进制用量向上取整 |
| 构建 | npm --prefix frontend run build | TypeScript/Vite通过，最终index-LtnRZllD.js |
| F3浏览器 | node --test --test-concurrency=1 frontend/e2e/cooking-mode.test.mjs | 3通过/18.24s；桌面/390px流程、暂停与运行中刷新、修改/撤销/登出清草稿、服务端成功后丢响应同正文同key重试只扣一次、库存/版本错误保留草稿后恢复 |
| 旧浏览器回归 | 同runner：accounts.test.mjs、lifecycle.test.mjs、planning-boundaries.test.mjs | 3通过/19.10s；账号隔离、库存/菜谱/方案原流程、预算及旧方案错误反馈 |
| 真实18088 | frontend/.tmp-e2e/f3-preview-0922.mjs（gitignored） | 主流程通过，库存300→220→300，仅一条用餐记录，改12分钟/manual后撤销；异常0；生成capability model_enabled=false |
| 最终视觉复查 | frontend/.tmp-e2e/f3-visual-0922.mjs（gitignored） | 实际加载index-LtnRZllD.js，390px溢出0，8个操作按钮最小153×44px，异常0；同目录桌面/窄屏各1张截图，已查看图片 |

如实保留调试：首次桌面计时用例混入真实点击毫秒，5分钟多几毫秒正确进位为6，断言失败；固定启动前Playwright时钟后通过，应用取整规则未放宽。一次编辑因Python默认编码失败，旧测试再次运行仍失败，后改用UTF-8。前两次预览主流程完成，但脚本错查不存在的/capabilities导致能力断言失败（第二次路径编辑失败，脚本未真正更正）；改用/recipe-discoveries/capabilities。第三次连续登录撞Nginx限流，09:59:46 UTC日志明确login=429/auth_requests；未改限流/超时，恢复后第四次全通过。预览留有4个专属一次性账号及测试数据，未改他人数据。截图发现按钮挤成竖排后仅补CSS换行，最后单独复查真实页面；上列功能测试在此CSS调整前完成，最终CSS由真实页面验证。

模型：本阶段真实请求**0次**、无usage，不调用生成或Agent。F1真实生成冒烟仍未执行，不在F3补做。

偏差：增加可选expected_recipe_version及显式新版核对入口，作为保留计时后恢复的防护；步骤模式从菜谱/推荐走原cook，保存方案仍走原confirm（支持用时字段，原按钮默认不记录）。不实现后台计时或多标签同步。

遗留：无已知本阶段阻塞项。系统时钟跳变可手改用时；浏览器禁用存储时有提示，刷新可能丢草稿。未跑远程CI（未提交推送）、真实模型、MySQL专属并发、全量/压力重跑；未动旧冻结证据和18080。F4～F9未开始。

### F3 主审查结论（2026-09-22）

**APPROVED：可以开始F4。** 主审查独立复核了步骤/计时状态、库存事务、幂等重试、版本冲突、用时反馈归属与迁移兼容性；未发现阻塞问题。

- 独立运行 `backend/.venv/Scripts/python.exe -m pytest tests/test_cooking_duration.py -q -p no:cacheprovider --basetemp=.tmp-f3-review`：10 项通过。首次使用 `D:/tmp` 作为 basetemp 触发 Windows 权限错误，改用仓库可写临时目录后通过；权限错误不属于应用失败。
- 独立运行 F2 关键兼容用例（删菜谱保留历史、标签经过做饭快照）：通过；独立运行 `node --test --test-concurrency=1 e2e/cooking-mode.test.mjs`：3 项通过。
- 阅读实际 18088 页面与代码：页面仍加载 `index-LtnRZllD.js`，`/health/live` 与 `/health/ready` 返回 200，容器健康，`alembic current` 为 `c63a1e7d9f20 (head)`。未改 18080、未调用模型、未提交推送。

保留的非阻塞边界：计时依赖浏览器 localStorage，明确提示禁用存储可能丢草稿；仅支持单标签页；未运行 MySQL 专属并发测试、远程 CI 或压力测试。这些不阻塞本阶段批准。F4 尚未开始。

## F4 个人耗时估计（2026-09-22，开发 agent）

```text
阶段：F4；状态：READY_FOR_REVIEW（主审查 CHANGES_REQUESTED 后的 R1 修复已交回复查）
```

### 实现与范围

基线为HEAD `3ca1976` 加领取时已有的F1/F2/F3未提交工作树，本阶段同样未提交、未推送。不是干净HEAD构建，不能把全部git diff算作F4。

- 规则只有一处：新增 `backend/app/services/personal_time.py`。窗口180天、最多20条、`weight=n/(n+3)` 且12条起封顶4/5、`estimated=ceil((1-weight)*T+weight*median)` 只向上取整一次。中位数用「两倍中位数」整数表示，偶数条取中间两数之和；全部计算走整数/有理数，因为浮点实现会在 `T=20、样本[6,6,6,6]` 上把精确的12抬成13。
- 样本范围严格按规格：当前用户、`status=completed`、`actual_minutes` 非空、快照菜谱id与version同时等于当前菜谱、`servings` 等于本次请求人数；按 `created_at DESC, id DESC` 取前20条。撤销记录、无用时记录、他人记录、别的菜谱或人数都不参与；不带version的旧快照仍然展示但永不匹配，所以新菜谱版本从标准时间重新开始，不按人数外推。
- 迁移 `e4a7c1b9d305_personal_time_estimate.py`：`user_preferences.personal_time_enabled` BOOLEAN NOT NULL `server_default='1'`；模型与 `Preferences` schema（strict bool）同步。开关存在服务端，换设备不会悄悄重新打开。
- `planning.recommend()` 每次请求只读一次历史样本，再逐候选算 `time_estimate` 放进候选；`TIME_LIMIT` 用有效预计分钟判断（等于上限算通过），菜谱自身 `minutes` 不改写。
- 方案链路共用同一函数：`plans.state()` 新增 `time_estimate` 与 `preferences.personal_time_enabled`，方案保存/修订、`validate_confirmation`、`shopping.create`、Agent 提案与批准前的新鲜度比较都通过 `personal_time.effective()` 重算，因此预览之后补记用时或切换开关会让旧预览 `PLAN_STALE`。
- 前端：新增 `frontend/src/personalTime.ts` 的 `timeLabel()`，推荐卡片显示一行「标准20分钟 / 你的预计25分钟，基于3次记录」，开关开着且0样本显示「标准20分钟，暂无个人记录」，关闭时显示「标准20分钟，已关闭个人用时估计」，关闭且确有记录时补「（另有N次记录未使用）」；厨房偏好新增开关与说明文字；`style.css` 加 `.time-estimate`。菜谱卡片与 `recipe.minutes` 不变。

新增6文件：`backend/app/services/personal_time.py`、`backend/migrations/versions/e4a7c1b9d305_personal_time_estimate.py`、`backend/tests/test_personal_time.py`、`frontend/src/personalTime.ts`、`frontend/tests/personal-time.test.mjs`、`frontend/e2e/personal-time.test.mjs`。

修改：`backend/app` 的 models/identity.py、schemas/identity.py、services/planning.py、services/plans.py、services/shopping.py、services/agent.py、services/agent_actions.py；`frontend/src/main.tsx`、`src/style.css`、`frontend/package.json`（tsc 文件列表）；本交接及 AGENTS/CLAUDE/NEXT_SESSION 入口状态。不实现F5的隐式偏好排序，也不改推荐排序权重。

### 预览与试用

URL：**http://127.0.0.1:18088**。独立项目 solomeal-features-0921，沿用现有预览数据库与图片卷，没有清库，不影响他人数据。当前线上构建为 R1 的 `index-DYKrHTKB.js` / `index-DxlX5toR.css`（取代交审首轮的 `index-Cimt5APQ.js`，CSS 未变），真实Chromium已断言页面script与本地dist逐字一致。

migrate容器退出0，`alembic current` = `e4a7c1b9d305 (head)`（R1 无新迁移），api/web/db三容器healthy，`/health/live` 与 `/health/ready` 均200。部署：`docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait`；停止用同前缀 `stop`，不删卷。凭据只留在原私有env，不写入文档。预览累计新增2个一次性账号：交审首轮 `f4_prev_mucmkt0m`、R1 复验 `f4_prev_muco9qbx`，各自的菜谱/库存/用餐数据都留着。

试用（真实页面已逐步执行，桌面与390px各一张截图）：
1. 登录后进「厨房偏好」，填厨具、把「最多用时」设为24，保存。
2. 进「我的菜谱」点「生成本餐推荐」，卡片下方出现「标准20分钟，暂无个人记录」（开关默认开着）。
3. 在「厨房偏好」把开关关掉、且此时还没有任何用时时（R1 补的步骤）：接口返回 `source=standard_disabled`、`sample_count=0`、`sample_median=null`、`weight=0`、`estimated_minutes=20`；把开关再打开则回到 `source=standard`。这就是主审查指出的那一格状态，现已可辨识。
4. 在菜谱卡片点「记录做完这道菜」并确认，到「用餐记录」点「填写用时」输入40保存（库存按菜谱扣减，本例500→420克）。
5. 回「我的菜谱」重新生成推荐：24分钟上限下该菜消失并提示「没有符合条件的菜谱」；把上限改到30后卡片显示「标准20分钟 / 你的预计25分钟，基于1次记录」。
6. 在「厨房偏好」取消勾选「按我做过的实际用时估计」并保存，回到24分钟上限重新推荐：候选恢复，文案变为「标准20分钟，已关闭个人用时估计（另有1次记录未使用）」。
7. 退出并重新登录，开关仍为关闭（保存在服务端），18088 页面已核对；库存与推荐/偏好写入都不改库存（500→420→仍420）。撤销那条记录后开关保持关闭时的文案「标准20分钟，已关闭个人用时估计」在浏览器夹具用例 `e2e/personal-time.test.mjs` 里核对（18088 脚本没有撤销步骤，不冒充真实页面步骤）。

### 实际验证

| 项目 | 命令/范围 | 结果（R1 复跑，2026-09-22） |
|---|---|---|
| F4后端 | `backend/.venv/Scripts/python.exe -m pytest tests/test_personal_time.py -q -p no:cacheprovider --basetemp=.tmp-f4-pytest`（TMP/TEMP 指向仓库外可写目录） | **18通过**（原17＋R1新增1条）：§6.2全部例子（含1→23、3→25、9→28、12→28、[20,30]→22、浮点陷阱[6,6,6,6]→12）、权重序列与20条封顶、0样本回退、**关闭且0样本仍为 `standard_disabled`（服务层与接口层各一处）**、预计25遇上限24被拒/25通过、人数与菜谱版本隔离、撤销/无用时/他人排除、20条最新截断（中位数22.5）、180天两侧、旧快照展示不匹配、开关关闭与整状态PUT回默认、方案补记用时后PLAN_STALE与关闭后revise/confirm |
| 相关后端 | `pytest tests/test_agent_actions.py tests/test_agent_sessions.py tests/test_agent_recovery.py` | 本轮由全套覆盖；交审首轮单独跑为 28通过/1跳过（跳过项需专用MySQL库） |
| 全套后端 | `pytest -q -p no:cacheprovider --basetemp=.tmp-f4-pytest-all` | **616通过/16跳过/0失败，退出0**。计数取自进度行字符（616 个 `.`＋16 个 `s`、无 `F`/`E`）——本轮该日志缺 pytest 的最终汇总行，故按字符计数并如实标注口径；首轮记的 615 与该值差 1，即 R1 新增的那条用例 |
| lint | `ruff check` 本阶段改动.py＋迁移 | 仅1条既有 `agent_actions.py` B905（HEAD同一函数已存在，未顺手改）；R1 改的两个 .py 无新增告警 |
| 前端单测 | `npm --prefix frontend test` | **59通过**（`personal-time.test.mjs` 由5条增至6条：新增「关闭且无记录时不谎称有未使用记录」） |
| 构建 | `npm --prefix frontend run build` | TypeScript/Vite通过，产物 `index-DYKrHTKB.js`（CSS `index-DxlX5toR.css` 未变） |
| 全套浏览器 | `node --test --test-concurrency=1 --test-timeout=180000 e2e/*.test.mjs` | **两轮**：第一轮 1 项失败——`e2e/pagination.test.mjs:19` 首个 `page.goto` 撞 30 秒上限、抛在 `support.mjs:95` 的 `openPage()`；第二轮不与其它负载并发重跑为 **31通过/0失败、退出0**。含 `e2e/personal-time.test.mjs`（登记→建菜谱→偏好24→记录做饭→填40分钟→候选消失→30分钟见预计→关闭开关候选恢复→**撤销后仍显示关闭文案**→API核对库存与状态） |
| 真实18088 | `node frontend/.tmp-e2e/f4-preview-0922.mjs`（gitignored） | **两轮**：第一轮同样在 `openPage` 首个导航 30 秒超时；第二轮通过——bundle断言线上即 `index-DYKrHTKB.js`、0样本文案、**关闭＋0样本的接口探针（`standard_disabled`/0/`null`/权重0/预计20，开回来则 `standard`）**、24分钟被挤掉、30分钟显示「你的预计25分钟，基于1次记录」、关闭后「另有1次记录未使用」、退出重登开关仍关、库存500→420且推荐/偏好写入不改库存、390px横向溢出≤1、按钮高度、页面异常0；桌面与窄屏截图各1张并已查看（窄屏可见关闭态文案） |

如实保留的调试与读数更正：
- 第一次后台全套后端得到的「623通过」读数不可作为依据：我把 `plans.state()` 加第4个参数时落下三处调用点（`agent.py` 提案state、`agent.py` 批准前新鲜度比较、`agent_actions.py` 的 `prepare_cooking` preview）。单独跑 `tests/test_agent_actions.py` 才暴露为2项失败（run status=failed）。修正后agent相关与全套均绿。改签名必须按调用点核对，模块内测试通过不等于全链路通过。
- 第一次全套浏览器（与后台pytest并发跑）出现1项失败：`e2e/receipt-vision.test.mjs:25` 的「对应食材」select读到空串。单独跑该文件通过；不与其它负载并发重跑整套为31/31通过。根因未闭合，按§12不放宽超时/不预热首个导航，也不据此宣称缺陷已排除。
- **R1 更正（主审查发现，我首轮判错了）**：撤销后/无记录时的文案口径。首轮实现里 `estimate()` 先判 `if not samples` 就返回 `source=standard`，把「开关关闭」这件事在 0 样本时吞掉了；我当时不但没当成缺陷，还反过来把前端「关闭且0样本」的分支删掉、并在本节写成「该状态服务端不会产生」的既成口径。计划 §6.3 要求关闭时一律返回 `standard_disabled`，与样本数无关，因此那句话是**用实现解释契约**、方向错了。R1 只把开关判断提到空样本判断之前（`median` 对空列表取 `None`，避免 `median_numerator([])` 越界），并补服务层＋接口层两条断言；前端相应恢复该分支、文案为「标准20分钟，已关闭个人用时估计」（有记录才补「另有N次记录未使用」）。教训：状态机里「谁造成的」这类语义不能因为某个组合当前不可达就删掉，可达性是我的判断而不是计划的规定。
- R1 两轮浏览器/页面验证各出现 1 次第99节已登记的同签名停顿（首个 `page.goto` 撞 30 秒、抛在 `support.mjs:95`）：全套浏览器第一轮落在 `pagination.test.mjs:19`、18088 脚本第一轮落在 `openPage`，重跑均通过。**未放宽超时、未预热首个导航、未据此宣称该停顿已排除或归因闭合**（根因仍未闭合，见第99节）。

模型：本阶段真实请求**0次**、无usage，未调用生成或视觉模型；浏览器测试全部使用脚本夹具 `backend/scripts/browser_fixture.py`（明确标注不是实际AI）。18088预览的 `SOLOMEAL_RECIPE_DISCOVERY_ENABLED=false` 是既有环境状态。

偏差：
1. ~~「关闭且无样本」返回 `standard`~~ ——**该偏差在 R1 撤销**：它不是偏差而是违反 §6.3 的缺陷，已按上文更正记录修复，现在关闭状态一律 `standard_disabled`。
2. `/me/preferences` 仍是整状态PUT，请求体不带 `personal_time_enabled` 会按schema默认回到true；前端每次提交完整状态所以页面不会丢，后端测试已钉住该行为，未新增局部更新端点。
3. 推荐候选新增 `time_estimate` 字段，Agent 的 `recommend_meal` 工具结果对模型多显示这一份服务端数据（只读、来自已完成记录，无新增外发）。
4. 20条上限在读取端截断，未加数据库索引或缓存。

遗留：
- 阻塞：无已知本阶段阻塞项。R1 的改动同样未提交、未推送。
- 非阻塞：估计只在「同菜谱版本+同人数」内生效，跨人数不外推（按规格）；每次推荐多一条历史查询；无version旧快照永不匹配，历史多的账号在补记前不会个性化；两类未归因现象各自保留——① 第99节登记的「首个 `page.goto` 撞 30 秒」签名本阶段命中 2 次（R1 全套浏览器第一轮落在 `pagination.test.mjs:19`、18088 脚本第一轮落在 `openPage`，重跑均通过）；② 交审首轮那次的症状不同（`receipt-vision.test.mjs:25` 的「对应食材」select 读到空串），单独跑与不并发重跑均通过，同样未归因。两者都没有用放宽超时或预热首个导航去消除；未跑MySQL专属并发、远程CI（未提交推送）、9轮压力重跑；未动源18080与旧冻结证据。

```text
请求：请主审查agent审查F4；未开始F5。
审查结论：CHANGES_REQUESTED（2026-09-22）。关闭个人用时估计且没有历史样本时，计划要求服务端返回 source=standard_disabled；当前 personal_time.estimate() 在空样本分支提前返回 source=standard。修复该分支并补回归断言后重新交回审查；F5未开始。
```

### F4 主审查结论（2026-09-22）

**CHANGES_REQUESTED。** 独立复核通过 F4 公式、样本范围、版本与人数隔离、推荐时间边界、计划新鲜度、偏好持久化和 18088 真实主流程；但发现一项与计划 §6.3 不一致：开关关闭时服务端应返回 `source=standard_disabled`，而 `backend/app/services/personal_time.py` 的 `estimate()` 在 `if not samples` 分支先返回 `source=standard`，导致关闭开关且无历史样本时来源不可辨识。请只修正该分支并补回归断言，重新构建验证后交回 F4；不要开始 F5。

### F4 R1 修复（2026-09-22，开发 agent）

只改主审查指出的那一处，未动公式、样本查询、迁移与方案链路。

```text
阶段：F4；状态：READY_FOR_REVIEW（R1 已交回复查）
基线：HEAD 3ca1976 ＋ F1/F2/F3/F4 未提交工作树；本轮仍未提交、未推送
```

改动5个文件（2 个实现＋3 个测试），净增 1 条后端用例、1 条前端单测：

- `backend/app/services/personal_time.py`：`estimate()` 里把「开关关闭」判断提到「空样本」提前返回之前，`sample_median` 改为对空列表取 `None`（`median_numerator([])` 会越界）。关闭时一律 `standard_disabled`，`weight=0`、`estimated_minutes=标准分钟`，与样本数无关；开关开着且无样本仍是 `standard`。
- `frontend/src/personalTime.ts`：补回「关闭且0样本」的文案分支「标准20分钟，已关闭个人用时估计」，只有确有记录时才追加「（另有N次记录未使用）」，不谎报未使用记录数。
- `backend/tests/test_personal_time.py`：服务层直接断言 `formula(dish, 1, [], personal_time_enabled=False)` 为 `standard_disabled`/`median=None`/`weight=0`/预计=标准；新增接口层用例 `test_disabling_the_estimate_without_any_history_still_reports_the_switch`（关掉开关、一条记录都没有时，推荐候选的 `time_estimate` 即该格状态）。
- `frontend/tests/personal-time.test.mjs`：新增关闭＋0样本文案一条。
- `frontend/e2e/personal-time.test.mjs`：撤销那条记录后的期望由「暂无个人记录」改为「已关闭个人用时估计」——该用例里开关此时仍是关闭的，正是主审查那格状态在页面上的读法。

复验（一轮针对性验证，命令与计数见上表）：后端 F4 18通过、全套 616通过/16跳过/退出0；前端单测 59通过；构建 `index-DYKrHTKB.js`；全套浏览器第二轮 31/31；18088 重新部署后真实页面第二轮通过（含关闭＋0样本的接口探针与两张截图）。首轮各出现 1 次第99节同签名的 30 秒首导航停顿，未放宽超时、未预热，根因保持未闭合。

模型：本阶段累计真实请求仍 **0 次**。

```text
请求：请主审查agent复查 F4 的 R1（只看 §6.3 那一格状态是否已闭合）；未开始F5。
审查结论：APPROVED（2026-09-22）。R1 修复已通过主审查复核，可以开始F5；F5此前未开始。
```

### F4 R1 主审查结论（2026-09-22）

**APPROVED：可以开始 F5。** R1 将关闭开关的判断移到空样本分支之前，并补服务层、接口层及前端文案断言；关闭开关且无样本现在返回 `source=standard_disabled`、`sample_count=0`、`sample_median=null`、`weight=0`、标准预计分钟。

- 独立复跑 F4 后端测试：18/18 通过。
- 独立复跑前端构建与个人用时测试：构建通过，6/6 通过。
- 独立访问 18088：健康检查 200/200，首页实际加载 `index-DYKrHTKB.js`；F4 真实浏览器流程通过，页面异常为 0，库存与用餐记录结果符合交接记录。
- 未调用真实模型、未修改 18080、未提交或推送。

先前 CHANGES_REQUESTED 的唯一问题已闭合。F5 可以开始，但不应在本阶段追加 F5 实现。

## F5 隐式偏好与解释（2026-09-22，开发 agent）

```text
阶段：F5；状态：READY_FOR_REVIEW（等待主审查）
基线：HEAD 3ca1976 ＋ F1/F2/F3/F4 未提交工作树；本阶段仍未提交、未推送
```

实现范围：新增 `personalization.py`，按近90天最多200条 completed 记录、上海自然日同菜去重、必选非 staple 食材/烹饪方式集合和 `2^(-age_days/30)` 衰减计算隐式偏好；叠加 F2 收藏/喜欢/不喜欢分数并夹到 [-15,15]，不喜欢只降该菜不硬过滤。推荐返回 `personalization`、`base_score` 和最多两条理由，新增 `/api/v1/me/personalization` 摘要接口。

新增 `user_preferences.personalization_enabled`（迁移 `f5a8c2d7e901`）并写入方案快照；关闭时 `preference_points=0`，与个人用时开关独立，切换后既有方案按原有新鲜度校验变为 `PLAN_STALE`。前端厨房偏好加入独立开关和“我的偏好摘要”，只展示真实记录窗口/数量，不声称模型训练。

验证：F5 专项后端规则测试 4 通过；相关 planning/feedback/plans/Agent 回归通过；前端既有测试、TypeScript 与构建通过；预览 `http://127.0.0.1:18088` 的 live/ready 均 200，迁移 `f5a8c2d7e901`，api/web/db healthy，产物 `index-CpwZ1zhf.js` / `index-DxlX5toR.css`。真实页面已创建一次性本地账号核对开关、摘要和退出重登后的关闭状态。

模型真实请求 0 次；源 18080 未动；预览库未清空；改动未提交未推送。请求主审查核对候选理由、关闭后的排序恢复、方案新鲜度和移动宽度操作可见性；不自动开始 F6。

### F5 主审查结论（2026-09-22）

**CHANGES_REQUESTED。** 独立审查确认迁移、用户隔离、反馈分数、关闭开关、硬约束、方案新鲜度字段和预览健康均有实现，但以下问题阻塞批准：

1. **[P1] 候选级解释没有进入推荐页面。** `backend/app/services/personalization.py` 已返回 `reasons`，但 `frontend/src/main.tsx` 只渲染一个“个性化排序已开启/关闭 · 基于 N 次记录”的全局 banner；`preferenceText()` 虽然定义了，却没有被 JSX 调用。用户看不到该候选为何上升/下降，未满足 §7.3 “前端用文字解释”和 §7.4 浏览器验收。
2. **[P1] 无法生成计划要求的真实次数文案。** 服务端 reasons 只有 affinity 数值和 ingredient_id/method，没有每个特征在去重窗口中的实际出现次数/总窗口计数。即使接上 `preferenceText()`，也无法如实生成“最近5次完成记录中3次使用鸡肉”；不能用衰减 affinity 冒充原始次数。需要同时保留并返回解释所需的去重窗口计数，前端按响应数据生成文字。
3. **[P2] 历史样本上限口径偏离。** `history()` 查询 `MAX_RECORDS * 2`（400）条后再去重并最多保留200条，可能把最近第201～400条原始完成记录带入画像；计划 §7.1 写的是近90天最多200条 completed 记录按时间/id降序。需明确并固定为计划口径，并补边界测试。

复核证据：F5 专项 4 条服务层测试及 planning/feedback/plans 相关回归通过，前端 TypeScript/构建通过，18088 live/ready 200、迁移 `f5a8c2d7e901`；这些结果不能覆盖上述功能缺口。当前不得开始 F6；修复后只需针对解释展示、计数、200条边界和受影响浏览器路径复验，再交主审查。

### F5 R1 主审查结论（2026-09-22）

**APPROVED：可以开始 F6。** 针对 CHANGES_REQUESTED 的三项修复均闭合：

- `history()` 改为按 `created_at DESC, id DESC` 只取最新 200 条原始 completed 记录；新增边界测试验证第 201 条不进入窗口。
- `score_candidate()` 为食材/方式理由返回去重窗口内的 `occurrence_count` 与 `window_count`；前端生成真实“最近1次完成记录中1次使用鸡蛋”文案，窗口少于5条会明确“偏好仍在积累”。
- 推荐页新增“本次推荐依据”区域，逐候选显示反馈理由或隐式食材/方式理由；新增浏览器测试覆盖完成记录、喜欢反馈、推荐理由展示和页面异常为零。

R1 验证：F5 相关后端回归 **28通过/1跳过**；新增 `frontend/e2e/personalization.test.mjs` 通过；前端 TypeScript、单测、构建通过，产物 `index-D6hW-hTw.js`；18088 live/ready 均 200，迁移仍为 `f5a8c2d7e901`，api/web/db healthy。模型真实请求0次、18080未动、改动未提交未推送。F6 可以开始，不应在本阶段追加 F6 实现。


## F6 推荐场景、原因展示与换一道（2026-09-22，开发 agent）

```text
阶段：F6；状态：READY_FOR_REVIEW
基线：HEAD 3ca1976 ＋ F1～F5 未提交工作树；本阶段仍未提交、未推送
审查结论：留空，由主审查 agent 填写
```

实现：
- `backend/app/schemas/planning.py` 新增 PlanningInput.scenario 枚举，旧请求缺省 custom 保留自带权重；页面初始为默认场景。服务端按 §8.1 固定五预设权重，快速做取 min(当前时间,20)。AgentPlanningInput 不变，不改变旧工具输入契约。
- `backend/app/services/planning.py` 为 less_shopping 在预算/报价可行性优先级之后、分数之前按 missing_ingredient_count 升序排列全部候选；新增缺口种类与 rejection_counts，同一道菜可以分别计入多个排除原因。无新表、无迁移。
- 新 `frontend/src/RecommendationPanel.tsx`，由 main.tsx 接入：场景、自定义时间/权重、局部加载和错误；快速做保留手动时间基线，默认恢复厨房偏好时间/默认权重，参数编辑清空旧结果与跳过集合。一次显示前三道，换一道从同一次完整排序结果中取下一条，不请求接口、不写反馈、不调用模型；跳过集合跟随结果，切tab保留，耗尽可重置/调整/发现。重新推荐重置集合。
- 卡片含标准/个人时间、按食材行比例的“食材满足度”、最多两条中文原因、采购缺口；缺报价且已知费用0时只写价格未知。保留F5中文解释，修正无完成记录时收藏/喜欢理由被空历史提示遮住的分支顺序。保存方案传完整本次request，保留场景、时间等条件。
- 无候选显示原因聚合数量，明确数量不能相加为不同菜谱总数；提供厨房偏好/发现入口，不自动放宽硬约束。

预览：**http://127.0.0.1:18088**。实际加载 `index-C-6cZspy.js` / `index-BqZ64srH.css`，live/ready均200，api/web/db healthy；迁移仍 `f5a8c2d7e901 (head)`。工作树构建，库和卷均复用；本轮真实页面验证新增两个一次性账号，第二个保留一条方案。

启动/重部署：`docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait`；停止用同前缀 `stop`，不删卷。登录使用原预览账号，或“第一次使用？创建账号”，文档不存密码。

试用（我的菜谱 → 用现有食材安排一餐）：
1. 选择清冰箱/少买东西/换换口味并生成；展开权重可核对参数，少买东西注明不代表最低价。
2. 手填32分钟→快速做变20→清冰箱恢复32→默认恢复厨房偏好时间。
3. 查看候选时间、满足度、原因、采购与价格；保存这餐方案后在下方查看。
4. 连续换一道，已跳过菜不再回来；耗尽显示“本次候选已看完”，重置或重新推荐可恢复。
5. 改为1分钟生成，查看超时等原因数量和发现入口；不会自动改人数/忌口/厨具。

验证：
- 后端命令：`pytest tests/test_recommendation_scenarios.py tests/test_planning.py tests/test_plans.py tests/test_personalization.py -q -p no:cacheprovider --basetemp=.tmp-f6-targeted`。首轮22通过/1失败/1跳过；新增测试造菜漏必填source而HTTP422，补字段后仅重跑F6专项 **7/7通过**。合并为 **23个不同用例通过、1个既有MySQL专属用例跳过**。覆盖五预设、quick更小上限、全候选排序（原第6名一缺口菜升第2，零缺口第1）、原因重叠、自定义兼容、偏好/库存/用餐不变。首次测试数据失败保留，不冒称首轮全绿。
- ruff检查本阶段两个后端实现文件及新测试通过；前端单测 **59/59**，TypeScript/Vite构建通过。
- 浏览器命令：`node --test --test-concurrency=1 --test-timeout=180000 e2e/recommendation-scenarios.test.mjs e2e/personalization.test.mjs e2e/personal-time.test.mjs` **3/3通过**。F6覆盖预设、时间基线、自定义、未知价、五菜换完/重置/重新推荐、换菜零推荐请求、硬约束原因、发现入口、库存/反馈/用餐/保存偏好不变。后续补“切tab保留耗尽状态”和“方案保留场景/时间”断言，仅复跑新用例 **1/1通过**。
- 真实18088：设置 `F6_PREVIEW_URL=http://127.0.0.1:18088` 运行同一F6用例 **1/1通过**；补保存方案断言后 **1/1通过**。实际MySQL方案request.scenario=clear_fridge、max_minutes=32；页面异常0，390px横向溢出≤1px。桌面/窄屏截图各一张已查看，位于gitignored的 `frontend/.tmp-e2e/f6-desktop.png` 和 `f6-mobile.png`。
- 全工作树 `git diff --check` 报混合CRLF路径的trailing whitespace（含main.tsx与既有identity.py），不宣称全树干净；未改写冻结文件行尾消除提示。

模型：真实请求 **0次**、无usage；没有调用生成/视觉模型。源18080未重部署，预览卷未清空，旧评测证据未改。未跑旧压力/全套/远程CI；首导航30秒历史问题本轮未出现，不据此宣称已解决。
偏差：无业务规格偏差；API缺省custom用于向后兼容，页面初始默认场景。无新迁移。
遗留：无已知F6阻塞；尚待独立主审查。**F7未开始**。
请求：请主审查agent审查F6；开发状态仅READY_FOR_REVIEW。


### F6 主审查结论（2026-09-22）

**CHANGES_REQUESTED。F7不得开始。** 本轮按用户要求切换为主审查角色，重新核对§8规格、实现与测试，并在实际18088复核；同一任务此前参与实现，不称为另一个独立agent的审查。

一项阻塞 **[P2] 偏好尚未加载时，快速做会放宽用户用时上限**：`frontend/src/RecommendationPanel.tsx:34` 的 `Math.min(baseMinutes??20,20)` 把尚未读取到的偏好当作20；`:43` 把这个临时值作为显式max_minutes提交，服务端因此不会使用已保存的更小上限。偏好GET随后返回还会改变输入框，却不失效旧结果。

18088真实复现（产物 `index-C-6cZspy.js`，门控仅延迟浏览器的GET，不修改服务端响应）：
1. 新测试账号保存max_minutes=10，建立15分钟菜谱。
2. 扣住推荐面板挂载的 `/me/preferences` GET，选择快速做并生成。
3. 实际POST max_minutes=20；服务端constraints.max_minutes=20，返回这道15分钟菜。
4. 释放GET后输入框显示10，15分钟候选仍在页面。
5. 同状态点击重新推荐，constraints.max_minutes=10、candidates=[]，形成对照。

复现脚本：`frontend/.tmp-e2e/f6-review-race.mjs`（gitignored）。这是明确的§8.1 min(当前值,20)违约和表单/结果不一致，不是旧首导航30秒问题。

修复要求：未有手动时间基线且偏好尚未读取时，不把临时20当用户时间发送；可保留null由服务端用偏好计算，或等偏好加载成功再允许提交。偏好返回不能让显示参数与保留结果不一致。补“已保存10分钟＋慢GET＋快速做”的浏览器回归，复核正常基线恢复后重新交审；本轮只审查，未代改业务代码。

其他已复核：五场景权重、服务端全候选少买排序、重叠原因计数、换菜耗尽/重置、未知价文案和保存方案参数有实现。后端F6专项复跑7/7，18088既有F6完整浏览器流程复跑1/1；后者等待正常偏好加载，不能覆盖上述竞态。18088 ready=200、页面产物核对一致。没有理由重复全套或旧压力测试。

模型0次；源18080与部署未改，未提交推送。当前结论只有CHANGES_REQUESTED，修复后只针对该问题和受影响路径复查。


### F6 R1 修复（2026-09-22，开发 agent）

**READY_FOR_REVIEW。** 仅修复主审查指出的偏好加载竞态；未开始F7，未自行改判APPROVED。

- `frontend/src/RecommendationPanel.tsx`：删除未知时间基线回退20的逻辑。没有手动值且偏好尚未返回时，effectiveMinutes与请求max_minutes均保持null，由既有服务端先取保存偏好、再应用quick的min(时间,20)。已有手动基线照常取min，不被迟到的偏好覆盖。后端、迁移、排序和模型逻辑未改。
- 新增 `frontend/e2e/recommendation-preferences-race.test.mjs`：门控挂载偏好GET，已保存10分钟、菜谱15分钟时，在GET释放前提交快速做；断言请求max_minutes=null、响应有效10、无候选，释放GET后输入10且仍无候选，再推荐仍无候选。另验慢GET期间手填35→快速做20→GET返回仍20→清冰箱35→默认10；保存偏好/库存/用餐不变，页面异常0。支持F6_PREVIEW_URL，直接复用同一回归检查真实预览。

验证（针对性，无全套/压力重跑）：
1. `npm --prefix frontend run build`：TypeScript/Vite通过，产物 `index-BmG-28ji.js`，CSS仍 `index-BqZ64srH.css`。
2. frontend目录执行 `node --test --test-concurrency=1 --test-timeout=180000 e2e/recommendation-preferences-race.test.mjs e2e/recommendation-scenarios.test.mjs`：本地夹具 **2/2通过**（新竞态＋原F6主流程）。
3. 部署到 **http://127.0.0.1:18088** 后，设置F6_PREVIEW_URL为该地址执行同一命令：真实预览 **2/2通过**。本轮新增两个一次性验证账号，保留数据。页面HTML实载 `index-BmG-28ji.js`；live/ready均200；api/web/db healthy。

部署使用既有专属项目：`docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait web`。Compose连带重建依赖api/migrate（无后端源码改动），migrate退出0，无新增迁移，现有库/卷未清空。登录方式与F6交接相同。

模型调用0次；18080未动，未提交推送，未改旧评测证据。本轮只完成修复和开发验证，主审查结论待复查；F7未开始。


### F6 R1 主审查结论（2026-09-22）

**APPROVED：F6通过，可以开始F7。** 本轮仅复查上次CHANGES_REQUESTED的时间基线加载竞态及受影响路径。按用户要求在同一任务切换主审查角色，不宣称另一个独立agent审查。

- 代码复核：未知基线保留null，不再伪造20分钟；服务端先读用户保存时间，再做quick的min(时间,20)，与§8.1一致。手动基线优先于异步返回的偏好。
- 真实18088定向复跑 `F6_PREVIEW_URL=http://127.0.0.1:18088 node --test --test-timeout=180000 e2e/recommendation-preferences-race.test.mjs`：**1/1通过**。门控GET期间已保存10分钟，实际POST为null、响应有效10且15分钟菜被排除；释放GET后显示10且无旧候选。手填35→快速做20→偏好落地仍20→清冰箱35→默认10同样通过；偏好/库存/用餐未被推荐修改，页面异常0。
- 页面HTML实载 `index-BmG-28ji.js`，live/ready均200；沿用R1已通过的原F6主流程验证，不重复全套或压力测试。

上次唯一阻塞已闭合，无新增阻塞发现。本轮未改业务代码、未重部署、模型调用0次、18080未动、未提交推送。F7可开始，但本次复审未启动F7。


## F7 多菜合并采购（2026-09-23，开发 agent）

**READY_FOR_REVIEW。** 基线 HEAD `3ca1976` ＋ F1～F6 未提交工作树；依据F6 R1 APPROVED开工。未提交推送，F8未开始，APPROVED留待主审查填写。

实现：
- 新 combined_shopping.py 与 POST /api/v1/shopping/combined-preview、/combined。1～10个不同菜谱，每道人数/版本/可选项独立；复用 selected_lines/required_quantities 和包装报价规则，先合计基础单位需求，再减一次有效库存、整包取整。排除过期/归档批次，返回各菜贡献、有效库存、缺口和来源日期，缺报价/过期报价保持未知，已知成本仅为下界。
- 创建在既有 food.run_operation 用户锁、事务、幂等机制内重算签名；签名覆盖用户、UTC日期、菜谱版本/条件、相关有效批次数量与版本、报价版本/数量/价格/来源/日期和预算。变化返回 COMBINATION_STALE；创建不扣、不预留库存。
- origin.kind=recipe_combination，保留组合条件与预览快照；旧缺kind按single_plan，修正旧create直接origin[plan_id]去重访问。旧单菜不强制勾选。
- 迁移a7c9e2f10463新增独立JSON checked_ingredient_ids，旧行补[]。/shopping/{id}/check带清单版本，勾选不入库；编辑删除项目同步剔除其勾选。组合confirm要求全部已买，沿用整单实际数量/预算/日期校验及原子新增库存；/close标closed，无库存写入，不能再次confirm。
- 新CombinedShoppingPanel：菜谱/推荐卡加入组合，重复加入聚焦人数；切菜谱/采购保留组合，切账号清空；异步预览不会覆盖新条件，网络失败保留同请求键。采购页内保存也触发清单刷新。ShoppingPanel稳定编辑器key，刷新保留未保存量，保存成功才清dirty；中文提示勾选与入库区别、移除不代表满足菜谱、已通过小票入库时关闭。修正同层组件key冲突及手机采购按钮换行。

预览：**http://127.0.0.1:18088**，复用solomeal-features-0921独立库/卷，未清空。最终实载 **index-BQ8Aqfbz.js / index-otwpBaJt.css**，live/ready均200，api/web/db healthy，Alembic **a7c9e2f10463 (head)**。工作树构建；部署命令 `docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait`（前端修正时指定web，Compose仍连带重建依赖）。源18080未更新。
登录：继续使用原预览账号，或“第一次使用？创建账号”。不在文档写密码。本次两次真实验证新增两个一次性账号，各保留两菜、一报价和一张已完成组合清单。

试用（5步）：
1. 我的菜谱 → 两道菜各点“加入采购组合”，上方改人数/可选配料。
2. “计算采购”，核对总需、有效库存、缺口、贡献与包装估价；可设置组合预算。
3. “保存组合采购清单”，到报价与采购下方看草稿；保存不入库。
4. 勾选全部已买，核对实际数量、成本、日期，保存修改；不买项目可移除并保存。已用小票入库则点“已通过其他方式入库，关闭清单”。
5. “核对并入库” → “确认已购买并整单入库”，才增加库存；完成清单不可再确认。

验证：
- 后端新6个不同用例全部通过，既有购物9通过/3个MySQL专属跳过，共 **15个不同用例通过/3跳过**。覆盖鸡蛋5-3=2、kg/l归一与可选项、过期库存排除、整包只算一次、未知/超预算、库存/报价/菜谱变化失效、隔离与重复菜拒绝、创建/确认重放和同键异请求冲突、未全勾拒绝、移除未买项、关闭不写库存、组合存在时旧单菜创建/确认。
- backend命令 `.venv/Scripts/python.exe -m pytest tests/test_combined_shopping.py tests/test_shopping.py -q -p no:cacheprovider --basetemp=.tmp-f7-targeted`。首轮新增6项均因测试种子幂等键少于8字符失败，旧9过/3跳；第一次修正写入被沙箱拒绝，未生效重跑仍失败。授权修正后新5过/1败：旧单菜测试误选库存已够的第一道，改成仍缺米的第二道，仅复跑该用例1/1通过。以上按不同用例计，不称首轮全绿。
- ruff服务/schema/model/迁移/新测试通过；API沿用现有FastAPI Depends默认参数风格，`ruff check --ignore B008 backend/app/api/shopping.py`通过，导入已排序。初次未忽略B008的命令报告既有及新增Depends风格提示，不称该命令全绿。
- 前端 **59/59单测**、TypeScript/Vite构建通过。
- `node --test --test-timeout=180000 e2e/combined-shopping.test.mjs`最终夹具 **1/1通过**；设置 `F7_PREVIEW_URL=http://127.0.0.1:18088` 同脚本最终真实MySQL预览 **1/1通过**。覆盖选两菜、重复加入不多行、5-3=2/1包6个6元、在采购页保存立即显示、已买刷新持久化且库存不变、未保存数量刷新保留、修改保存后确认、同键重放仅加一次（3→9、2个批次）、用餐0、页面异常0、390px无横向溢出、组合篮恰1块且保存后清空。
- 首轮浏览器check()即时断言与服务端成功后才选中的受控框不匹配，改为click→等/check返回200→刷新断言已选。业务断言未放宽。首版真实流程通过但截图发现同层key冲突残留旧组合篮、手机按钮竖排；修复并补唯一篮子/清空断言后，夹具和真实页面各复验1/1通过。
- 桌面/手机截图 `frontend/.tmp-e2e/f7-desktop.png`、`f7-mobile.png`（gitignored）；桌面初版已查看，最终手机修复后再次查看，确认残留与挤压消除。

模型真实调用 **0次**；18080未动、预览卷未清空、旧评测证据未改、未提交推送。未跑旧全套/stress/远程CI；不宣称旧30秒首导航问题解决。边界：组合篮为会话草稿，刷新需重新选菜；只整单确认，最后一项不买可取消/关闭整单；最多100种采购食材，超限需减少菜谱。**F8未开始，请主审查按§9审查F7。**


### F7 主审查结论（2026-09-23）

**CHANGES_REQUESTED。F8不得开始。** 用户要求本任务执行主审查；同一任务参与过F7开发，不宣称另一个独立agent审查。本轮未改应用代码、未重部署。

阻塞 **[P2] 保存响应丢失后切页重试会重复创建组合清单**：`frontend/src/CombinedShoppingPanel.tsx:11` 将幂等键仅保存在组件本地ref，`:19` 保存时按该ref选键；`frontend/src/main.tsx:115` 在离开菜谱/采购页时卸载组件，而basket仍保存在App。故网络失败后用户切到库存再返回，仍看到原组合，却已丢失原操作键，重试POST以新键创建第二张同签名草稿。两张草稿分别可确认，放大重复采购/入库风险。不能用全局按组合签名永久去重代替操作级恢复，因为用户以后仍可有意再次购买相同组合。

真实18088复现（实载index-BQ8Aqfbz.js）：
1. 创建一次性复核账号、一种鸡蛋和一道需2蛋的菜；加入组合并计算。
2. 浏览器拦截POST /shopping/combined，route.fetch让真实后端完成201后abort丢弃返回；页面显示“无法连接服务器，请检查网络后重试”。API确认已存在1张草稿。
3. 切“食材库存”再回“我的菜谱”，篮中仍1道菜；重新计算并保存。
4. 第二次请求幂等键与第一次不同；API现在有2张清单，origin.signature完全相同，库存仍[]。

复现脚本 `frontend/.tmp-e2e/f7-review-lost-response.mjs`（gitignored）；实测输出 `lost_response_status=201, lists_after_loss=1, lists_after_retry=2, keys_changed=true, same_origin_signature=true, inventory=[]`。本次新增复核账号保留两张draft，无入库。

修复要求：未决创建操作的键和请求需与会话组合草稿一起跨面板挂载保存；成功或显式放弃后再结束该逻辑操作，切账号清理。补“服务端已提交但响应丢失→切其他tab→回来重试”的浏览器回归，断言仍只有1张清单。对同一面板直接重试与正常新建也作必要对照。

其他已核对：§9的按基础单位聚合、有效库存扣一次、整包报价、签名重算、用户隔离、独立勾选、全部已买后整单确认、关闭无库存写入和旧single_plan兼容有实现。后端F7专项复跑 **6/6通过**；真实18088既有完整F7浏览器用例 **1/1通过**。这些用例没有覆盖卸载后的未知结果恢复，因此不能据其批准。live/ready均200，页面产物核对一致。

模型调用0；源18080未动、无提交推送、未改旧证据；未重复全套或压力测试。当前F7结论为CHANGES_REQUESTED，只针对上述重试缺口修复复验后再交审，F8不开始。

### F7 R1 修复与主审查结论（2026-09-23）

**APPROVED：F7通过，可以开始F8。** 本轮修复并复审上次唯一阻塞；同一任务参与过开发，仍不称为独立 agent 审查。

- 未决的组合创建请求已从 `CombinedShoppingPanel` 的组件级 ref 移到 `main.tsx` 会话级状态/ref。请求 body 与 Idempotency-Key 一起保留，直到服务端明确成功或明确的 4xx 拒绝；网络错误、响应丢失、切换到库存/采购页、组件卸载后重试沿用完全相同的请求和键。成功后清理组合草稿与未决操作；切换账号清理全部组合状态。未决时锁定组合编辑，避免把未知结果改成另一笔请求。
- 新增 `frontend/e2e/combined-shopping-retry.test.mjs`，覆盖同页重试、切到其他 tab 后重试、请求仍未返回时切页、重试遇到429后再恢复、成功后可新建相同组合、切账号不泄漏待处理操作。每次服务端已提交但首个响应被丢弃，最终只有一张清单且重试请求 body/key 与首请求相同。
- 本地前端构建通过；F7 原主流程与新增重试回归 **2/2通过**。真实 `F7_PREVIEW_URL=http://127.0.0.1:18088`：重试回归 **1/1通过**，原主流程 **1/1通过**；该次真实重试回归曾因预览 auth 桶达到 5次/分钟返回429而等待限流恢复，未修改限流配置，恢复后通过。
- 最终预览实载 `index-BXfFSkOj.js` / `index-otwpBaJt.css`，live/ready均200，api/web/db healthy，迁移仍 `a7c9e2f10463 (head)`。模型0次，18080未动，预览卷未清空，未提交推送。F8可开始。


## F8 今天首页（2026-09-23，开发 agent）

**READY_FOR_REVIEW。** 基线 HEAD `3ca1976` ＋ F1～F7 未提交工作树；依据F7 R1 APPROVED开工。未提交推送，F9未开始，APPROVED留待主审查填写。

实现：
- 登录后默认进入「今天」（`frontend/src/main.tsx:48`），主导航新增「今天」并保留助手/库存/菜谱/发现/采购/小票/记录/偏好全部入口；其余面板契约未改。
- 新只读聚合 `backend/app/services/home.py` ＋ 端点 `GET /api/v1/home`（可选 `?sections=...`）与 `GET /api/v1/home/{section}`（`backend/app/api/home.py`，`backend/app/main.py:72` 注册）。四块各自返回 `{status:"ok",data}` 或 `{status:"error",error:{code:"HOME_SECTION_FAILED"}}`；某块异常只回滚该块会话后继续算其余块，前端「重试这一栏」只打单块端点。无新迁移（`a7c9e2f10463` 仍是 head）、无新写路径。
- 优先处理：未归档、`quantity>0`、有到期日且 ≤ UTC今天+3天的批次，按 `expires_on`→食材名→批次id 排序取5条；`expired_count/expiring_count/total_count` 用 SQL COUNT 覆盖全部命中行（不受显示5条限制），过期项标「已过期，需检查」。
- 今天推荐：直接调用已审查的 `planning.recommend`（默认场景＋当前偏好），不写第二套算法；卡片复用 `RecommendationPanel`，场景按钮/个人时间/中文原因/开始做饭/换一道/收藏/保存方案全部沿用现有实现，仍由面板 `slice(0,3)` 限三道；聚合附带 `favorites` 使收藏按钮显示真实状态。
- 待采购：只读 `status=="draft"` 清单，`pending_count` 按 `checked_ingredient_ids` 逐条判定，`list_count/pending_total` 覆盖该用户全部草稿（跨分页），最多显示3张，点击进「报价与采购」；不凭空生成缺口。
- 最近做过：SQL COUNT 全部 `completed` 记录＋最近5条，`cooked_on` 取 Asia/Shanghai 日历日；`retracted` 不计数也不显示；`actual_minutes` 为空显示「未记录用时」不按0计。点击跳「用餐记录」并聚焦该条，用既有 `DurationEditor` 改用时。
- 时间口径：有效性按 UTC 日（`as_of`），页面「今天」按 Asia/Shanghai（`display_date`，固定+08:00偏移，与 personalization 同法，不依赖可选 tzdata）。
- 前端 `HomePanel.tsx`＋`homeText.ts`：中文标题/空态/加载/错误/成功提示、逐块重试；`key={'home:'+token}` 使切账号重挂载并丢弃在途响应；`edited` ref ＋「刷新今天」只请求三块只读数据（`READ_ONLY_SECTIONS`），不覆盖用户已改的推荐条件；空账户提供添加库存/去发现菜谱/录入菜谱/导入示例菜谱四个入口，示例只在用户点击后写菜谱，不动库存与用餐记录。

预览：**http://127.0.0.1:18088**（同一 `solomeal-features-0921` 项目与卷，未清空）。最终实载 **index-BGww4npC.js / index-COYO-iN5.css**，`/live` 与 `/ready` 均200，api/web/db 三容器 healthy，容器内 `alembic current` → `a7c9e2f10463 (head)`。部署：`docker compose --env-file D:/SoloMeal-Acceptance/features-0921-01/preview.env -p solomeal-features-0921 up -d --build --wait`（窄屏样式修正后仅 `--build --wait web`）。源18080未动。

登录：沿用原预览账号，或「第一次使用？创建账号」。本轮真实验证新增一次性账号并保留其数据。

试用（5步）：
1. 注册/登录后停在「今天做点什么」：四块分别显示，任一模块读失败时其余照常，可单独「重试这一栏」。预期不产生任何写请求。
2. 「优先处理」列出三天内到期与已过期批次并给出总数；点「去库存处理」到库存页调整数量或归档，回首页点「刷新今天」后计数更新。
3. 「今天推荐」显示至多3道与理由，可换场景/换一道/收藏/开始做饭；点「刷新今天」预期推荐条件与结果保持不变（提示「推荐条件保持不变」）。
4. 「待采购」显示未处理清单与待买项，点击进入「报价与采购」勾选并整单入库；首页本身不改变清单状态。
5. 「最近做过」显示最近5条完成记录（无用时写「未记录用时」），点击某条跳到「用餐记录」并聚焦，改实际用时应提示「用时已保存，库存未改变」且库存数量不变。

验证（针对性，无旧全套/压力/远程CI）：
- 后端 `tests/test_home.py` **10个用例全通过**：UTC与Shanghai日界、空账户四块、窗口/排序/状态/计数与5条截断、150批次＋120清单＋120记录的跨分页聚合（含第101条之后）、retracted 排除、过期库存不进推荐、单块失败＋局部重试＋未知块404、`sections` 参数与422、只读（六类GET逐字节不变）与用户隔离、未登录401。命令 `backend/.venv/Scripts/python.exe -m pytest tests/test_home.py -p no:cacheprovider --basetemp=.tmp-f8-targeted`。
- 定向5模块（home/planning/shopping/combined_shopping/identity）**37通过/3 MySQL跳过**；全量后端 **645通过/16跳过/0失败/0错误，9分49秒**。如实记录：第一次全量运行报 18 errors，全部是 `tests/test_agent.py` 的 tmpdir setup 失败（`WinError 32/183`），原因是我自己并发跑了两次全量并共用 `--basetemp=.tmp-f8-full`；改为单跑＋新 basetemp 后 0 错误，未改任何测试或应用代码。
- ruff：`app/services/home.py app/api/home.py app/main.py tests/test_home.py` 中仅 `app/api/home.py` 报既有 FastAPI `Depends` 默认参数风格 B008，`ruff check --ignore B008 app/api/home.py` 通过（与F7同口径，不称未加 ignore 的命令全绿）。
- 前端 `npm test` **68/68**（含新增 `tests/home-text.test.mjs`）、`tsc --noEmit`＋Vite 构建通过。
- 浏览器：新增 `e2e/today-home.test.mjs`（登录→今天首页→收藏/换一道→开始做饭计时确认→最近做过跳历史改用时→刷新今天→390px→切账号→空账户导入示例，断言库存/清单/用餐与页面异常0）与 `e2e/home-race.test.mjs`（聚合直接带出结果且挂载期无 POST、换「快速做」后「刷新今天」不覆盖场景且只发 `GET /home`、max_minutes 仍20、浏览刷新不产生用餐记录与扣库存）。本地夹具全量 `node --test --test-concurrency=1 --test-timeout=180000 e2e/*.test.mjs` **38/38通过**；真实预览 `F8_PREVIEW_URL=http://127.0.0.1:18088` 两条各 **1/1通过**（首跑 `home-race` 因预览 auth 桶5次/分钟返回429致验证登录失败，等待限流窗后复跑通过，未改限流配置与断言）。
- 因默认落地页改为「今天」，四处既有 e2e 需先切到目标面板：`lifecycle`/`pagination` 增加 `useTab(page,'食材库存')`，`mobile.test.mjs` 的 TABS 增加「今天」「发现菜谱」，`planning-boundaries.test.mjs` 改按现文案断言。断言未放宽、应用代码未为测试让步。
- 桌面与390px截图 `frontend/.tmp-e2e/f8-desktop.png`、`f8-mobile.png`、`f8-empty-start.png`（gitignored）已逐张查看：首版390px推荐卡按钮被挤成竖排两字，补 `@media(max-width:640px){.recommendation-card .row>button{flex:1 1 130px}}` 后重建重部署并复查消除，无横向溢出。

模型真实调用 **0次**（夹具为脚本响应；`/home` 与预览验证均只读既有服务）。18080未动、预览卷未清空、旧评测证据未改、未提交推送；未跑旧185留出/9轮stress/远程CI，不宣称旧30秒首导航根因已解决。

已知边界（非阻塞）：
1. 待采购块在服务端读取该用户全部 draft 行后再取前3与合计，草稿极多时成本随行数线性增长，未加分页上限。
2. 「今天推荐」在每次首页挂载都会跑一次 planner（纯数据库计算、不发模型）；「刷新今天」刻意不重跑，因此推荐结果需用户显式「生成本餐推荐/重新推荐」才更新。
3. `emptyAccount` 依据 App 级菜谱/批次缓存判断：若这些列表尚未加载而 `/home` 已返回数据，「先把厨房装起来」可能与下方有数据区块同屏（本轮夹具用 API 侧通道写入时可见），不影响任何数据。
4. 到期日仍是用户记录，页面脚注已写明只用于提醒、不是食品安全结论；过期批次仍保留在库存页，只是不参与推荐与扣减。

**F9未开始。** 请主审查 agent 按 §10 审查 F8。审查结论：（留空，由主审查 agent 填写）

### F8 主审查结论（2026-09-23）

**CHANGES_REQUESTED。F9不得开始。** 本轮审查未改应用代码、未重部署。

阻塞 **[P2] 首次聚合请求失败后，首页刷新无法恢复**：`frontend/src/HomePanel.tsx:72` 的初次请求 catch 仅设置提示，保留 `home=null`；缺失 section 被渲染为「正在读取…」，没有单栏重试入口。点击「刷新今天」即使成功，`:34` 的 `setHome(old=>old?...:old)` 仍返回 null，`:52` 又排除推荐块，所以四栏都无法恢复，却显示「今天的数据已更新」。用户必须切页重进或整页刷新才能重新初始化。

真实18088复现：浏览器仅拦截首次 `GET /api/v1/home` 并 abort；注册一次性空账号后出现网络错误；解除故障后点击「刷新今天」，真实聚合返回200，页面显示更新成功，但四栏仍全为「正在读取…」、单栏重试按钮0个、日期仍为省略号。复现脚本 `frontend/.tmp-e2e/f8-review-initial-failure.mjs`（gitignored）；输出 `refresh_status=200, loading_blocks_after_success=4, retry_buttons=0`。仅创建空账号，无库存/菜谱/采购/用餐写入。

修复要求：首次聚合失败应进入可见错误和可重试状态；成功重试须能初始化首页元数据及四块内容，不能在数据未恢复时提示成功。保持既有「已编辑推荐条件不被刷新覆盖」保护。补浏览器回归覆盖首次网络失败（或整个请求5xx）→恢复网络→用户重试→四栏可用，并保留原场景保护回归；在真实18088定向复验后再交审。

本轮独立执行：后端 home 专项10/10通过；两条既有F8夹具流程2/2通过；TypeScript/Vite构建通过，产物仍 `index-BGww4npC.js` / `index-COYO-iN5.css`。ruff未忽略B008时仅报告4处FastAPI Depends默认参数风格，沿用开发记录口径，不列为新阻塞。预览HTML实载同一产物，`/live`、`/health/ready` 均200。上述既有通过用例没有覆盖首次整请求失败恢复，因此不能据其批准。

导入示例后推荐不会自动更新已有明确边界，用户可显式生成本餐推荐，本次不据此阻塞。模型调用0；源18080未动、预览库未清空、未提交推送、未重跑全量/旧压力测试。

### F8 R1 修复与主审查结论（2026-09-23）

**APPROVED：F8通过。** 上次唯一阻塞的首次聚合失败恢复已修复并复审。本次开发与主审查由同一任务完成，不称独立 agent 审查。F9是增强项，按计划等待用户决定是否执行。

- `HomePanel.tsx` 首次 `/home` 请求失败时保存错误状态，四栏不再无限显示「正在读取…」，首页显示「重试首页」。重试请求完整聚合，成功后一次性初始化日期和四栏；只有真实成功才显示更新提示。已有首页数据时，「刷新今天」仍只重读优先处理、待采购、最近做过三块，不覆盖用户调整的推荐条件。
- 全聚合读取用递增请求序号保护：用户发起重试后，较早请求即使晚返回也不能覆盖新结果或重新写入旧错误。切页卸载时序号失效。
- 新增 `frontend/e2e/home-load-retry.test.mjs`，注入首次 `/api/v1/home` 断连，断言四栏错误、完整重试后四栏恢复、只发两次GET且库存/用餐无写入。既有 `home-race.test.mjs` 真实预览复跑时发现测试把库存列表首项固定当鸡蛋，MySQL实际先返回挂面150克；断言改按 `ingredient_id` 定位鸡蛋，业务代码与预期数量5未改。
- 修复后本地 TypeScript/Vite 构建通过，产物 `index-B6aBJSX8.js` / `index-COYO-iN5.css`；三条F8定向夹具流程 **3/3通过**。真实18088：首次断连恢复 **1/1通过**，既有推荐场景保护 **1/1通过**。初次同批真实场景保护用例因上述测试顺序假设失败，改正断言后单独复跑通过；不把首轮写成全绿。
- 预览HTML实载同一产物，`/live` 与 `/health/ready` 均200，api/web/db healthy，迁移 `a7c9e2f10463 (head)`。复用独立预览项目与卷；源18080未动、模型调用0、未提交推送。没有重跑无关的后端全套、旧压力或远程CI。


## 2026-09-23：使用入口与 GitHub 同步

用户选择继续使用 http://127.0.0.1:18088，复用 `solomeal-features-0921` 及现有数据。F1～F8 代码、6 个数据库迁移、前后端测试与阶段记录本次统一纳入版本控制；F9 暂缓。历史“未提交推送”属于各阶段当时状态，远程提交与 CI 结果以仓库 Actions 为准。

本轮同步前已有 F8 全量后端 645 通过／16 MySQL 跳过、浏览器夹具 38/38 与 F8 R1 定向回归记录；本轮再核对前端单测、构建、Git 提交钩子，并由 GitHub CI 验证最终提交。新增模型调用 0。
