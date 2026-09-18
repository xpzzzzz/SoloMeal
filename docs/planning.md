# 单餐确定性推荐（当前只读）

POST /api/v1/recommendations，Bearer认证，body可为{}。
默认使用个人份数、时间、厨具；请求可显式覆盖前三项。请求忌口与已保存忌口取并集，通过用户内标准名/别名解析，不会自动放宽。

可输入budget（本次补购金额），quotes列表每项包含ingredient_id、package_quantity（规范单位）、package_price、source、observed_on。
整包装数量向上取整；无报价或报价超过30天标unknown/stale，未来日期和重复食材报价拒绝。
当前金额约定人民币元，无实时商品服务；30天是项目可调整策略，不是市场有效期保证。
known_purchase_cost只是已知部分。budget_status为not_requested/unknown/within_estimate，已知部分超预算即拒绝。
within_estimate只表示输入估计下可行；unknown绝不作为预算满足。

库存覆盖与三天内临期覆盖按每种食材需求比例平均，避免把克/毫升/个数相加。score=60*库存覆盖+40*临期覆盖-10*近7天已完成同菜次数。
排序先区分预算未知，再按评分、价格完整性、完整补购成本、recipe_id稳定排序。默认权重如上；请求可配置权重并随方案快照保存，详见下文。
份数缩放和做饭使用相同向上取整规则（个数取整、g/ml至0.001）。不改动库存、不预留、不保存方案。
返回约束、分项评分、缺料、报价来源日期、不可行原因及advisory_only=true。
2026-09-10：每个候选新增required_ingredients，按候选servings输出本次总需求量（仅包含选用食材）。recipe.ingredients仍是recipe.servings份原配方；展示本次用量应使用required_ingredients，不再乘份数。该字段使用做饭共用数量算法，包含piece向上取整及g/ml三位精度。

推荐端点保持只读；可以通过以下方案端点持久化。可选食材与权重配置已实现。报价持久化与采购编辑入库已实现，详见下文；Agent自动重规划仍待验收。


## 方案生命周期（已实现）

- POST /plans：recipe_id+constraints，重新计算规则后保存版本1。
- GET /plans、GET /plans/{id}：当前用户方案及当前版本快照。
- POST /plans/{id}/revisions：recipe_id+constraints+expected_version；只允许pending版本修改，生成不可变新快照并递增版本。
- POST /plans/{id}/confirm：expected_version；显式用户确认做完，按快照份数扣减。写入带Idempotency-Key。

同一key同参数重试返回原结果；不同key不能再次完成已完成方案。库存、日期、偏好、菜谱改变返回409 PLAN_STALE；修订后原版本返回PLAN_CONFLICT。相关批次新增也视作变化，保守要求重新确认。
确认再检查当前别名解析后的忌口，防止别名新增导致快照外约束变化。预算unknown返回BUDGET_UNKNOWN；缺料仍由原库存事务整体拒绝。
撤销用餐保留方案completed以防同方案重扣，用户需新建方案；取消方案和历史版本API/UI已实现，详见下文。

## 2026-09-06 可选配料更新

include_optional默认false，可选项不参与需求、忌口过滤或扣减；true时全部纳入。方案快照保存此选择，确认不得更改。规划与扣减共用quantities.py；常备标记不豁免数量。

## 2026-09-06 生命周期与评分补充

GET /plans/{id}/revisions按版本返回历史；POST /plans/{id}/cancel接受expected_version和幂等key，pending才能取消，取消后不能修订或确认。同键重试返回原结果；不同键取消终态返回PLAN_CONFLICT。取消不改历史版本、不改库存。菜谱删除导致确认返回PLAN_STALE。

PlanningInput.score_weights包含inventory(60)、expiry(40)、repetition(10)、purchase_cost(0)，每项0~100整数且至少一项正数。score=inventory*覆盖率+expiry*临期覆盖-repetition*重复次数-purchase_cost*完整补购估计元数。无完整报价时成本分项为null；启用成本权重后，未知报价排在完整报价之后。硬约束和预算检查不受权重影响。配置保存在方案request和候选，UI可改排序权重；报价持久化见下文。


## 2026-09-07 保存报价与采购（已实现）

GET /quotes查询当前用户报价；POST /quotes接受PriceQuote、currency=CNY与expected_version（新建0，更新当前版本），需要Idempotency-Key。每用户每食材一条当前报价，不保存独立价格历史；单位取标准食材单位，piece包装必须为整数，未来日期拒绝。

PlanningInput.use_saved_quotes默认true；本次quotes逐食材覆盖保存报价，包括过期的显式报价也不自动改用其他价格。false只采用本次报价。超过30天的报价仍显示来源/日期，但不计为有效价格。方案快照及Agent待批准方案冻结当时相关报价，use_saved_quotes=false；已有历史方案也按旧请求解释，不补入后来价格。按当前库存修订会保留原报价；如需最新报价，重新生成推荐并保存新方案，或API修订时显式传use_saved_quotes=true、quotes=[]。

POST /shopping传plan_id+expected_version，从当前pending方案生成草稿；GET /shopping及/{id}恢复当前用户清单。同一方案版本再次准备返回原清单（含取消/完成状态），需要另一笔时先修订方案。

POST /shopping/{id}/edit传expected_version+items完整替换明细；items含ingredient_id、quantity、unit、actual_cost（本项实际总金额或null）、currency=CNY、location、expires_on/expiry_source。可去掉不购买的条目；至少一项，重复食材拒绝。未知日期和来源必须配对。原需求、估价、来源及预算保存在origin，不随编辑变化。

POST /shopping/{id}/confirm和/cancel均传expected_version，所有写接口需Idempotency-Key。确认整单在owner锁+operations事务内复用add_batch，不执行嵌套commit；任意条目失败全回滚。预算存在时未知实际金额或实际合计超预算拒绝；无预算时金额允许未知。确认是用户记录已购，不下单、不向商店付款。实际价格不会自动变成新报价。

采购草稿生成后独立于方案修订/取消；不自动追随缺料变化。采购确认不确认做饭，入库后需更新原方案再做饭。当前清单不能撤销采购；误录库存通过现有盘点操作更正，并保留事件。界面支持预算输入、报价保存、采购编辑和显式整单确认。验证见validation/shopping-0907.md。
