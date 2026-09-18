# SoloMeal 数据模型与落地边界

## 已迁移

0001_identity → 9290b526fd6e → 7a48cdc81c59 → bd048bb65ef9 → b04b9448a35e：17业务表，另有alembic_version。

| 表 | 约束/用途 |
|---|---|
| users | UUID、唯一用户名、Argon2摘要 |
| user_preferences | user主键；厨具/忌口JSON、份数、时间 |
| auth_sessions | 令牌摘要主键、用户FK、失效时间；注销删除会话 |
| ingredients | 用户内唯一标准名；规范单位g/ml/piece |
| ingredient_aliases | 用户内唯一别名；ingredient+owner复合FK |
| inventory_batches | 定量Decimal、到期日和来源、存放位置、版本、quantity>=0 |
| operations | 用户+幂等键唯一；类型+参数摘要、成功结果快照 |
| inventory_events | 批次/操作均复合owner FK；实际增减事件 |
| recipes | 名称、来源、份数、时间、厨具、步骤 |
| recipe_ingredients | 定量每项；菜谱/食材owner复合FK；通过optional区分必需/可选 |
| cooking_records | 不可变菜谱快照、份数、完成/撤销状态 |
| cooking_consumptions | 实际批次消耗量，撤销恢复依据 |

上表inventory相关各实体见模型；实际业务表计数由SQLAlchemy元数据验证为准。
每个对象引用都检查owner，关键多租户关系再用复合FK阻止跨用户写入。
单位不能跨质量/体积/个数猜测换算；存储Numeric(14,3)，piece必须整数。
扣减锁批次按id排序，分配按FEFO；先检查全部数量再写，操作结果与事件/扣减同事务。
撤销恢复原实际消耗，不能覆盖其他交易后的库存；重复撤销不会重复加库存。
已过期批次保留但不参与规划/做饭；未知日期可用且FEFO排后，未知不代表保鲜保证。

## 后续设计及实现进度

- 已实现meal_plans与plan_revisions：owner复合FK、plan+version唯一、约束/候选/库存/菜谱/偏好/日期快照。确认在事务内校验并回写cooking_id；历史版本保留。
- shopping_lists/items：plan版本owner FK、需求/缺料/包装采购量、价格来源/观察日期、购买状态；不能将用量成本冒充包装支出。
- receipt_imports/items：owner+用户内内容摘要重复提示、私有路径、解析草稿/修正/确认状态；确认入库复用operations事务幂等；原件内容不作为指令。
- agent_sessions/runs：owner FK、消息/约束、状态、pending_action、恢复游标；工具执行前从session绑定owner，不接受模型提供owner。
- tool_executions：run/owner、工具名、校验后参数、状态、结果/脱敏错误、时间、操作幂等键；SSE事件另有单调序号以便重放。
- ingredients常备标记、recipe_ingredients可选标记待增；常备不是无限数量。

不预建没有服务和验收的空表。meal_plans与确认语义已落地；下一批为Agent与小票。

当前写入采用users行锁作为用户厨房事务边界，随后按id锁批次。MySQL READ COMMITTED在获取用户锁后读取当前数据，避免REPEATABLE READ下预先身份查询建立旧快照。直接绕过服务写数据库不在该一致性契约内。

Agent当前已实现agent_runs/tool_executions，消息以JSON存run，parent_run_id用于受控上下文复制（不单独存字段）；尚未单建agent_sessions。运行租约和幂等确认见agent.md。

agent_run_events以(run_id,seq)作主键，owner复合FK；agent_runs.event_seq递增，事件和状态同事务。迁移为已有run补seq=1初始快照，客户端以runUUID:seq定位重放。

最新迁移92d9cff900d6新增ingredients.is_staple和recipe_ingredients.optional，兼容默认false，表数仍17。

## 2026-09-06 CRUD与会话补充

c730e618af42增加批次archived、菜谱version、库存事件batch_version。归档不改变数量；默认列表排除归档，可include_archived查询，恢复需当前版本。归档批次不允许盘点，先恢复。撤销恢复数量但不解除归档；同批次同秒事件按版本排序，老事件null不能推断先后。菜谱删除仅删除当前菜谱及用量行，用餐/方案JSON历史保留。

da41905c772e新增agent_sessions（18业务表）；run包含session_id+owner复合FK、constraints与context_summary。旧run各自建独立会话，不猜测缺失的旧parent关系。latest_run_id是服务维护的指针，创建后续run需当前会话版本且前一run结束，用户行锁保证竞争互斥。


## 2026-09-07 报价与采购

e821b469a103新增price_quotes与shopping_lists，共20业务表。price_quotes有(user_id,ingredient_id)唯一约束和ingredient+owner复合外键，Numeric(11,3)包装量、Numeric(8,2)金额、CNY币种、来源/观察日期、乐观版本。标准食材单位不可修改，读取时关联单位。

shopping_lists保存owner、version、status、origin不可变方案/报价快照、items经Pydantic校验的Decimal字符串明细、result批次引用与创建时间；用户外键和owner索引。条目未单独建表，不支持直接SQL绕过服务更新JSON；编辑和确认再次验证条目归属。用户锁使同方案版本准备、版本编辑和确认互斥；operation幂等绑定参数，所有批次和库存事件与终态同事务。无新增数据库凭据或外部商品服务。

## 2026-09-08 小票第一段

f912a570bc24新增receipt_imports，共21业务表。保存owner外键、唯一随机file_key、file_hash、media_type、byte_size、version、status=draft、parse_status、parsed与draft JSON、created_at；(user_id,file_hash)普通索引只为用户内重复提示，不能当入库去重约束。items合并存JSON，服务检查可选ingredient_id归属；解析输入不允许携带ingredient_id。修正不改原始parsed，版本编辑复用operations用户锁。无库存写入，确认状态/结果与整单事务在下一段添加。文件内容存私有目录，不在数据库JSON或日志中，详细边界见receipts.md。

小票确认追加迁移0a23c671de89：receipt_imports.result 为 nullable JSON，记录 operation_id 与行号/批次结果；completed/cancelled 为终态，已有记录保留。

P7第三段追加1b34d782ef90：receipt_imports的parse_started_at/parse_finished_at及(user_id,parse_started_at)索引；operations先提交识别准入结果，再在独立事务保存完成结果。每票一次尝试、用户24小时配额和120秒在途窗口跨进程持久化。
