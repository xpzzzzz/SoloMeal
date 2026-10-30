# SoloMeal · Agent 主动性 M1 实施计划（交给 Codex 执行）

> **使用方式**：把本文件放到仓库根目录（`docs/proactivity-m1-plan.md`），按 Task 顺序执行。
> 每个 Task 末尾都有「验收」，跑通再进下一个；不要跨 Task 合并提交。
> **代码与注释用英文，文档与提交信息用中文**（与仓库现有风格一致）。

---

## 0. 目标与非目标

### 0.1 一句话目标

在用户**没有打开页面**的情况下，系统仍然能发现「该做什么」，并在用户回来时把**已经准备好的、带解释的、一键可闭环的提案**送到眼前。

### 0.2 本阶段做（MVP，可面试演示）

| 能力 | 说明 |
|---|---|
| 触发层 | 纯规则计算两类信号：**临期可消耗**、**采购草稿滞留**（不调用模型） |
| 决策层 | 每日上限、静默时段、连续忽略自动抑制、优先级排序 |
| 投递层 | `proactive_item` 收件箱 + `GET /proactivity/inbox` + 首页卡片 |
| 闭环 | 卡片上的「就做这个」跳转既有方案流程；「不是这个」记一次忽略 |
| 可测 | 假时钟注入；`POST /internal/tick` 可手动触发；dev-only「时间旅行」按钮 |
| 可解释 | 每条都带 `why`（为什么是现在）与 `suppress_hint`（以后别推这类） |

### 0.3 本阶段明确**不做**

- ❌ 不接入模型做「是否打扰」的门控（不可测、成本不可控）
- ❌ 不引入 APScheduler / Celery / Redis（用「tick 接口 + 外部 cron」或手动触发）
- ❌ 不做微信/短信/WebPush 推送（Web 应用拿不到，且放大打扰成本）
- ❌ 不做 LLM 生成的每日简报（留到 M3）
- ❌ 不修改 `services/agent.py` 的状态机语义、不改 `home.py` 的现有行为

### 0.4 完成定义（DoD）

1. `POST /internal/tick` 能在一次调用内为用户生成至多 `daily_limit` 条 `pending` 条目；
2. 重复 tick 不产生重复条目（唯一键拦截）；
3. 首页在无用户操作的情况下就能看到卡片（刷新页面即出现，不需要点任何按钮）；
4. 「就做这个」能进入既有方案流程并最终完成一次库存扣减；
5. 「忽略」三次后，同类信号 7 天内不再产生；
6. 后端新增测试全绿，原有回归不减少；`ruff check` 通过；
7. `docs/proactivity.md` 存在，含架构图、信号表、指标定义、demo 脚本。

---

## 1. 设计摘要

```
[触发层 collect()]  纯函数 / 只读 DB / 无模型
   信号源A: 批次将在 0~1 天内到期 且 有菜谱可用它
   信号源B: 采购草稿 draft 超过 48h 且仍有未勾选项
        ↓  Signal(kind, subject_key, priority, title, body, why, payload, expires_at)
[决策层 select()]   纯函数 / 无 DB 写入
   静默时段 → 每日上限 → 连续忽略抑制 → 排序
        ↓  选中的 0~N 条
[落库 record()]     写 proactive_item（唯一键去重，失败即跳过）
        ↓
[投递层 inbox()]    GET /proactivity/inbox → 首页卡片
        ↓  接受 / 忽略
[闭环]              复用既有 plan / shopping 流程；接受只做标记，不直接写业务
```

**关键判断（写进文档，面试要讲）**：

1. **"什么时候说"是规则，"说什么"可以是模型。** 模型不参与门控，所以行为可测试、成本可预测。
2. **接受动作不直接写业务数据。** 卡片只返回 `action`，由前端调用既有 `POST /plans`、`POST /shopping` 等接口；这样快照校验、幂等、`PLAN_STALE` 全部继续生效，不需要新增一条写入路径。
3. **重复 tick 靠唯一键而不是锁来防重。** 多 worker 并发时，第二次插入触发唯一约束，捕获后跳过即可（比租约简单且不会漏跑）。

---

## 2. 数据模型

新增**两张表**，都不改现有表。

### 2.1 `proactive_item`（收件箱 / 审计）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | Integer FK(users.id) index | |
| `kind` | String(32) | `expiring_batch` / `shopping_stale` |
| `subject_key` | String(128) | `batch:{id}` / `shopping:{id}` |
| `dedupe_key` | String(200) **unique(user_id, dedupe_key)** | `f"{kind}:{subject_key}:{bucket}"`，`bucket` 为 `YYYY-MM-DD` |
| `priority` | SmallInteger | 越大越靠前：过期 100 / 今天到期 90 / 明天到期 80 / 草稿滞留 50 |
| `title` | String(200) | 例：`菠菜 300g 明天到期` |
| `body` | String(500) | 例：`今晚做「菠菜炒蛋」正好用完` |
| `why` | String(300) | 例：`临期 1 天 · 本周还没用过它 · 3 道菜谱可用` |
| `payload` | JSON | 结构化证据与动作参数（见 2.3） |
| `snapshot_version` | Integer | 接受时用于校验新鲜度（批次 version / 清单 version） |
| `status` | String(16) | `pending` / `accepted` / `dismissed` / `expired` / `suppressed` |
| `created_at` | DateTime(UTC) | tick 时刻 |
| `delivered_at` | DateTime(UTC) nullable | 首次被读到的时间（可空，M1 可只写 created_at） |
| `resolved_at` | DateTime(UTC) nullable | 接受/忽略/过期时间 |
| `expires_at` | DateTime(UTC) nullable | 过期后不再展示 |
| `version` | Integer default 0 | 与仓库其它表一致的乐观并发列 |

索引：`(user_id, status, priority desc, created_at desc)`。

### 2.2 `proactive_setting`

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `user_id` | PK, FK | | 一用户一行 |
| `enabled` | Boolean | true | 总开关 |
| `daily_limit` | SmallInteger | 1 | 每天最多几条（1~3） |
| `quiet_start` | String(5) | `"22:00"` | 静默开始 |
| `quiet_end` | String(5) | `"08:00"` | 静默结束 |
| `snooze_until` | DateTime nullable | null | 「七天后再提醒」 |
| `updated_at` / `version` | | | 乐观并发 |

> 时区固定 `Asia/Shanghai`，复用 `services/home.py` 里已定义的 `SHANGHAI`（不要引入 `zoneinfo`/`tzdata`，仓库的注释解释了原因）。

### 2.3 `payload` 约定

```jsonc
// expiring_batch
{
  "kind": "expiring_batch",
  "batch_id": 12, "ingredient_id": 5, "ingredient_name": "菠菜",
  "quantity": "300", "unit": "g", "expires_on": "2026-10-31", "days_left": 1,
  "recipe_id": 8, "recipe_name": "菠菜炒蛋", "recipe_minutes": 15
}

// shopping_stale
{
  "kind": "shopping_stale",
  "shopping_id": 3, "recipe_name": "番茄意面",
  "items_count": 5, "pending_count": 2, "created_at": "2026-10-27T18:00:00Z"
}
```

`action` 由后端生成，前端只做分发（不要在前端拼业务参数）：

```jsonc
{ "type": "open_plan_flow", "recipe_id": 8, "prefill": { "servings": 1 } }
{ "type": "open_shopping", "shopping_id": 3 }
```

---

## 3. 后端文件清单

### 3.1 新建

| 文件 | 职责 |
|---|---|
| `backend/app/models/proactivity.py` | `ProactiveItem`、`ProactiveSetting` ORM |
| `backend/app/services/proactivity.py` | **纯函数**：`collect()` / `select()` / `build_actions()` |
| `backend/app/services/proactivity_store.py` | 落库、去重、过期、状态流转、抑制判定（唯一允许写 DB 的地方） |
| `backend/app/schemas/proactivity.py` | Pydantic：`InboxOut`、`ItemOut`、`SettingsIn/Out`、`TickResult` |
| `backend/app/api/proactivity.py` | 4 个路由（见 4） |
| `backend/app/api/internal.py` | `POST /internal/tick`（独立 router，避免与业务路由混鉴权） |
| `backend/app/commands/tick.py` | CLI：`python -m app.commands.tick`（仿 `commands/reconcile_memory.py`） |
| `backend/migrations/versions/<rev>_proactivity.py` | 建两张表 |
| `backend/tests/test_proactivity_signals.py` | 纯函数测试（无 DB 也能跑主体） |
| `backend/tests/test_proactivity_api.py` | 路由 + 状态流转 + 抑制 |
| `backend/tests/test_proactivity_tick.py` | tick 幂等 / 上限 / 静默 |
| `docs/proactivity.md` | 设计文档（中文） |

### 3.2 修改（最小化）

| 文件 | 改动 |
|---|---|
| `backend/app/main.py` | `include_router(proactivity_router)`、`include_router(internal_router)`；`app.state` 增加 `proactivity_clock`（可注入的时钟） |
| `backend/app/core/config.py` | 新增 `tick_token: SecretStr \| None`、`demo_mode: bool = False` |
| `frontend/src/pages/Home*` | 顶部挂载 `<ProactiveCard/>`（沿用现有区块容器与错误边界风格） |

**不要改**：`services/home.py`（如需复用临期查询，在 `proactivity.py` 内自己写一段只读 SQL，允许少量重复，换来零回归风险）、`services/agent.py`、`services/planning.py`。

---

## 4. API 契约

所有业务路由挂在 `/api/v1` 下；鉴权依赖**沿用 `api/home.py` 里同一个依赖**（执行前先打开该文件确认名字，不要自造）。

### 4.1 `GET /api/v1/proactivity/inbox`

```jsonc
200
{
  "items": [
    {
      "id": 41, "kind": "expiring_batch", "priority": 80,
      "title": "菠菜 300g 明天到期",
      "body": "今晚做「菠菜炒蛋」正好用完",
      "why": "临期 1 天 · 本周还没用过它 · 3 道菜谱可用",
      "payload": { "...": "见 2.3" },
      "action": { "type": "open_plan_flow", "recipe_id": 8, "prefill": { "servings": 1 } },
      "created_at": "2026-10-30T10:00:00Z",
      "expires_at": "2026-10-31T15:59:59Z",
      "version": 0
    }
  ],
  "meta": {
    "as_of": "2026-10-30", "display_date": "2026-10-30",
    "enabled": true, "daily_limit": 1, "used_today": 1,
    "quiet_hours": { "start": "22:00", "end": "08:00" },
    "suppressed_kinds": ["shopping_stale"],
    "pending_total": 1
  }
}
```

### 4.2 `POST /api/v1/proactivity/items/{id}/dismiss`

- Header：`Idempotency-Key`（必需，沿用现有校验）
- Body：`{ "reason": "not_useful" }`（可选，枚举 `not_useful|too_often|already_done`）
- 200：`{ "item": { ...同 ItemOut..., "status": "dismissed" } }`
- 404：跨用户或不存在；409：状态已是终态

### 4.3 `POST /api/v1/proactivity/items/{id}/accept`

- Header：`Idempotency-Key`
- Body：`{ "expected_version": 0 }`
- 200：`{ "item": { ..., "status": "accepted" }, "action": { "type": "open_plan_flow", ... } }`
- 409 `PROACTIVE_STALE`：`snapshot_version` 与当前批次/清单版本不一致（说明库存已变），前端应刷新并提示「情况有变，重新算一遍」
- **语义**：只标记状态，不写任何业务数据

### 4.4 `GET` / `PATCH /api/v1/proactivity/settings`

`PATCH` body：`{ "expected_version": 0, "enabled": true, "daily_limit": 1, "quiet_start": "22:00", "quiet_end": "08:00", "snooze_until": null }`，需 `Idempotency-Key`；返回同样结构 + `version`。

### 4.5 `POST /internal/tick`（不在 `/api/v1`）

- Header：`X-Internal-Token: <settings.tick_token>`；未配置 token 时该路由返回 404（生产默认关闭）
- Body：`{}`；可选 `{ "user_id": 7 }` 只跑一个用户（测试/演示用）
- 200：`{ "users": 3, "created": 2, "expired": 1, "suppressed": 1 }`
- 语义：先 `expire_overdue()`，再对每个用户 `collect → select → record`

### 4.6 `POST /api/v1/proactivity/simulate`（`demo_mode` 才注册）

- Body：`{ "days": 1 }`，把 `app.state.proactivity_clock` 向前推 N 天（仅影响本进程、本用户后续计算）
- 用途：面试现场「⏩ 推进 1 天」按钮，不必等定时器

---

## 5. 核心算法（伪代码，直接翻译成 Python）

```python
# services/proactivity.py  —— 纯函数，不写 DB

def collect(db, user_id: int, now: datetime) -> list[Signal]:
    """两类信号，全部只读。now 必须是 UTC aware。"""
    today = shanghai_day(now)          # 复用 home.shanghai_day
    signals = []
    signals += _expiring(db, user_id, today, now)   # 0~1 天内到期
    signals += _shopping_stale(db, user_id, now)    # draft 且 pending>0 且超 48h
    return signals


def select(signals, ctx) -> list[Signal]:
    """ctx: enabled / daily_limit / used_today / quiet / snoozed / suppressed_kinds"""
    if not ctx.enabled or ctx.snoozed_until and now < ctx.snoozed_until:
        return []
    if in_quiet_hours(now, ctx.quiet_start, ctx.quiet_end):
        return []
    room = max(0, ctx.daily_limit - ctx.used_today)
    if room == 0:
        return []
    cand = [s for s in signals if s.kind not in ctx.suppressed_kinds]
    cand.sort(key=lambda s: (-s.priority, s.expires_at or MAX))
    return cand[:room]
```

关键细节（务必照做）：

- `in_quiet_hours` 支持跨午夜窗口（22:00–08:00）：`start > end` 时用 `h >= start or h < end`。
- 抑制判定：取该用户该 `kind` **最近 3 条 status == dismissed**，若这 3 条连续，则 `now - last.resolved_at < 7 days` 时加入 `suppressed_kinds`。
- `friendly` 文案（`title`/`body`/`why`）在这一层生成，**必须全部来自 DB 事实**，不允许模型臆造。
- 数量格式化复用 `services/quantities.py`，不要自己拼单位。

---

## 6. 前端

目录：`frontend/src/features/proactivity/`

| 文件 | 内容 |
|---|---|
| `api.ts` | `getInbox()` / `dismiss(id, reason)` / `accept(id, version)` / `patchSettings()` |
| `useInbox.ts` | 拉取、乐观更新、失败回滚；沿用现有请求 hook 的登录代次隔离写法 |
| `ProactiveCard.tsx` | 单条卡片：标题、正文、`why` 折叠行、两个按钮（就做这个 / 不是这个） |
| `ProactiveInbox.tsx` | 最多 1 条 + 「还有 N 条」展开；空态不占位（不要留空白卡片） |
| `WhyRow.tsx` | 小字「为什么是现在」+ tooltip；右侧「以后别推这类」→ `dismiss(reason=too_often)` |

样式与交互要求：

- 放在首页「今天」四栏之上，视觉权重高于普通区块（描边 + 1px 高亮），但**不弹窗、不遮罩**；
- 接受后：卡片变灰 0.3s 后移除，并跳转 `/plans/new?recipe_id=...`（复用现有方案创建页）；
- 无条目时整块不渲染（`display:none`，不要留高度）；
- 文案全部中文，与现有 UI 一致。

---

## 7. 测试清单（照抄用例名，逐个实现）

### 7.1 后端纯函数（`test_proactivity_signals.py`）

1. `test_expiring_batch_creates_signal_with_recipe`：批次明到期 + 有菜谱用它 → 1 条，`priority == 80`，`payload.recipe_id` 非空
2. `test_expiring_batch_without_recipe_still_signals`：没有菜谱 → 仍产信号，`body` 走兜底文案
3. `test_batch_expiring_in_three_days_is_ignored`：T+3 → 0 条（明确「不做 3 天提醒」）
4. `test_archived_or_zero_quantity_batch_ignored`
5. `test_shopping_draft_stale_after_48h`：pending>0 且 48h+ → 1 条
6. `test_shopping_draft_with_all_items_checked_ignored`
7. `test_shopping_draft_younger_than_48h_ignored`

### 7.2 决策层（`test_proactivity_tick.py`）

8. `test_daily_limit_one_creates_single_item`
9. `test_second_tick_same_day_creates_nothing`（幂等）
10. `test_tick_inside_quiet_hours_creates_nothing`
11. `test_three_consecutive_dismissals_suppress_kind_for_7_days`
12. `test_mixed_kinds_respect_suppression`
13. `test_dismiss_breaks_suppression_streak`（中间有一次 accepted → 不抑制）
14. `test_overdue_items_marked_expired_on_tick`

### 7.3 API（`test_proactivity_api.py`）

15. `test_inbox_requires_auth`
16. `test_inbox_returns_only_own_items`（跨用户 404/空）
17. `test_accept_marks_accepted_and_returns_action`
18. `test_accept_with_stale_snapshot_returns_409`
19. `test_dismiss_requires_idempotency_key`
20. `test_dismiss_is_idempotent_on_replay`
21. `test_settings_patch_version_conflict_returns_409`
22. `test_tick_requires_internal_token`
23. `test_home_still_returns_four_sections`（回归哨兵）

> 需要真实 MySQL 的用例（唯一索引并发、JSON 列）用现有 `skipif` 机制，标 `mysql` 专属，别在 SQLite 上凑数。

### 7.4 前端

24. `ProactiveCard` 渲染标题/正文/why
25. 点「不是这个」→ 乐观移除 + 失败回滚 + 错误 toast
26. 空态不渲染容器
27. Playwright：造一条临期批次 → tick → 首页见卡片 → 点「就做这个」→ 方案页可见该菜谱

---

## 8. 执行顺序（每个 Task 一次提交）

| Task | 内容 | 预估 | 验收命令 |
|---|---|---|---|
| **T0** | 读 `api/home.py` 确认鉴权依赖名；`alembic heads` 取 `<HEAD_REV>`；确认测试命令（见 `backend/README.md`） | 15m | 把三处结论写进提交信息 |
| **T1** | `models/proactivity.py` + 迁移 | 45m | `alembic upgrade head` 成功；`alembic downgrade -1` 能回滚 |
| **T2** | `services/proactivity.py` 的 `collect()` + 用例 1–7 | 1.5h | 7 个用例绿 |
| **T3** | `select()` + `proactivity_store.py`（record/expire/suppress）+ 用例 8–14 | 2h | 这些用例绿，且 SQLite/MySQL 都跑 |
| **T4** | `api/proactivity.py` + `schemas` + 用例 15–23 | 1.5h | 新用例绿；`ruff check` 干净 |
| **T5** | `api/internal.py` + `commands/tick.py` + token 校验 | 45m | `python -m app.commands.tick` 打印计数；无 token 时 404 |
| **T6** | 前端组件 + 首页挂载 + 用例 24–26 | 2.5h | `npm test` 绿；`npm run build` 通过 |
| **T7** | Playwright 用例 27 + `docs/proactivity.md` + demo 脚本 | 1.5h | `npm run e2e` 绿 |

**合计约 8~10 小时**。若只剩 4 小时：做 T1+T2+T3（砍掉 settings 表，`daily_limit` 硬编码为 1，静默时段写死），先从后端把「决策可测」这件事立住——这是面试最值钱的部分。

---

## 9. 风险与对应对策

| 风险 | 对策 |
|---|---|
| 多 worker 并发 tick 重复插入 | `unique(user_id, dedupe_key)` + 捕获 `IntegrityError` 跳过；**不要加锁** |
| 用户改了库存但卡片还在 | `snapshot_version` 在 accept 时校验，冲突返回 409 `PROACTIVE_STALE`，文案「情况有变，重新算一遍」 |
| 静默时段跨午夜写错 | 用例 10 必测 `22:00–08:00` |
| 时区依赖缺失（容器无 tzdata） | 固定 `timezone(timedelta(hours=8))`，复用 `home.SHANGHAI`；**不要 `import zoneinfo`** |
| 卡片造成打扰感 | 默认 `daily_limit=1`；无条目时容器不渲染；「以后别推这类」一键抑制 |
| 演示时等不到定时器 | `demo_mode` 下的「⏩ 推进 1 天」按钮 + `POST /proactivity/simulate` |
| 迁移破坏现有 645 回归 | 只新增表，不改任何现有列；T4 必须跑全量后端测试 |

---

## 10. 给 Codex 的硬性约束

1. **不要新增第三方依赖**（`requirements`/`package.json` 保持不变）。
2. **不要修改** `services/home.py`、`services/agent.py`、`services/planning.py` 的既有函数签名与行为。
3. 所有写接口必须带 `Idempotency-Key` 校验，复用现有实现，不要新写一套。
4. 模型输出与用户输入必须在边界处经 Pydantic 校验；**任何 `title/body/why` 都不得由模型生成**（本阶段零模型）。
5. 所有时间比较用 UTC aware datetime；展示用 `Asia/Shanghai`。
6. 单文件不超过 ~400 行；纯函数与 IO 分层（`proactivity.py` 里不准出现 `db.commit()`）。
7. 每个 Task 结束：`ruff check` + 相关 pytest 通过 + 提交信息写明「验收结果」。
8. 中文文档里的数字（如 48h、7 天、每日 1 条）必须与代码常量一致，抽成模块级常量并注释来源。

---

## 11. 演示脚本（90 秒，写进 docs/proactivity.md 末尾）

1. 打开首页 → 卡片已在：**「菠菜 300g 明天到期 · 今晚做菠菜炒蛋正好用完」**
2. 展开「为什么是现在」→ 临期 1 天 / 本周没用过 / 3 道菜谱可用
3. 点「就做这个」→ 方案页 → 确认做完 → 库存扣减、历史出现（2 次点击闭环）
4. 点「⏩ 推进 1 天」→ 卡片换成「采购清单放了 3 天，还差 2 项」
5. 连点两次「不是这个」→ 第三次点击后卡片消失，收件箱显示 `shopping_stale 已抑制至 11-06`
6. 收尾话术：**「主动性不是多发通知，而是知道自己什么时候不该说话——这套判断是纯规则、可单测、可回放的。」**

---

## 12. 后续（不在本次范围，写进 backlog 即可）

- M2：18:00 预生成方案草稿（`actor=system` 的 run），点开即用
- M3：夜间画像（sleep-time 思路），把 `personal_time` / `personalization` 物化为快照
- M4：学习型时机——用确认时间戳拟合个人活跃时段，替换硬编码窗口
- 渠道：Web Push / 邮件摘要（周日一条替代 7 条）
