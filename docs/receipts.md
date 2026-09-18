# 小票草稿与确认（P7 第三段，2026-09-08）

最新（2026-09-09）：P7指定配置验收完成，receipt-v5明确固定包装总量和名称/规格分离；可选SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING=false用于支持该扩展的Qwen，未配置默认不发送。三张真实票据字段及真实页面入库/重试通过；完整证据和仍存在的合成名称差异见[最终验收](validation/receipt-v5-acceptance-0909.md)。下文早期“尚待实测”为历史记录。

2026-09-09补充：解析失败现有脱敏分类日志（小票UUID/category/提供方HTTP状态），字段验收报告同样记录 diagnostic。receipt-v2 明确整行包装总量和约重未知规则；用户可人工接受估计值，提示效果尚未真实验证。规则与本轮验证见[离线收尾](validation/receipt-diagnostics-0909.md)。此前三票真实闭环已通过，但识别整体未通过，历史状态以[真实报告](validation/receipt-vision-real-0908.md)为准。

当前提供私有上传、鉴权原图访问、结构化解析接口与可编辑草稿。确认前不写库存；确认后整单创建库存批次与事件，不创建采购清单或报价。视觉适配已实现，需本地显式配置和启用；页面在未配置时提供手工补录，已配置时提供发送前确认。真实模型效果尚待实测；脚本解析器只在隔离测试中注入，不通过正式用户参数选择。

## API

均需 Bearer 登录，身份从服务端会话获得。写端点需要 Idempotency-Key；编辑/解析还需要 expected_version。

| 请求 | 行为 |
|---|---|
| POST /api/v1/receipts | 原始 PNG/JPEG 请求体，Content-Type 对应图片；返回草稿和本用户 duplicate_of 提示 |
| GET /api/v1/receipts/capabilities | 返回是否已启用视觉与用户24小时配额，不返回模型配置/密钥 |
| GET /api/v1/receipts | 当前用户的小票记录 |
| GET /api/v1/receipts/{id} | 读取已保存草稿及原始结构化解析结果 |
| GET /api/v1/receipts/{id}/file | 鉴权原图，attachment、no-store、nosniff；前端通过会话校验后生成临时 Blob URL |
| POST /api/v1/receipts/{id}/edit | expected_version + draft，整份保存修正；可以保存未补齐的条目 |
| POST /api/v1/receipts/{id}/confirm | expected_version；只确认已保存版本，整单入库后 completed |
| POST /api/v1/receipts/{id}/cancel | expected_version；取消后 cancelled，不入库 |
| POST /api/v1/receipts/{id}/parse | expected_version；受控解析适配器输出校验后保存，失败保留手工入口 |

草稿包含 purchased_on 和 items；条目包含 name、quantity、unit、amount（人民币本项金额）、ingredient_id、uncertain、excluded、expires_on、expiry_source、location。数量/单位/金额未知保存 null，数量或单位未知强制 uncertain=true。金额与数量用经过 Decimal 校验的字符串存入 JSON。购买日期不用于推断到期日期。

解析器仅收到图片字节与类型，不接收数据库、用户身份或工具；输出拒绝额外字段、不合法数值和超出100行的内容。适配器超时默认30秒，失败只保存 failed 状态，不保存异常原文。成功解析按本用户名称/别名匹配食材，原始 parsed 与可编辑 draft 分开保存，页面只按文本渲染名称。

解析先在用户锁与operations内提交parsing请求记录及parse_started_at，再释放事务调用适配器；同键在途重试返回已保存parsing，已完成返回原结果；异键重复不调用模型。每份小票仅允许一次尝试，用户过去24小时默认最多10次、同一时刻仅一个在途请求；失败与中断也计入配额。120秒后在途记录视为失败，重试可落库失败终态但不重新调用；未重试时GET显示失败，仍可手工编辑。此机制跨进程依靠MySQL用户锁，不依赖内存信号量。它限制调用次数，不等于金额硬预算或全服务全局限流。

完成时再次取用户锁与版本检查：若人工编辑/确认/取消已发生，记录discarded并返回409，不覆盖修正。原始parsed保留合法模型输出，人工draft强制每行uncertain=true。仅未编辑版本1且未尝试的小票可识别；失败后手工补录，新上传的独立草稿仍受用户配额。

## 私有文件与边界

- 默认目录 backend/private_uploads，已 gitignore；可通过 SOLOMEAL_RECEIPT_STORAGE_DIR 指定绝对私有目录。目录不挂载为静态资源，不保存原始文件名。UUID文件键和SHA256不返回客户端。
- 流式累计最多5 MiB，类型/文件头一致，并用锁定Pillow12.3.0执行verify和load完整解码；限制2000万像素、单边12000，拒绝动画/多帧、损坏和解压炸弹。解析发送前再次检查，兼容历史上传记录。完整解码不是通用恶意文件扫描，真实中文票据效果仍须验收。
- 获取原图先检查owner，读出后校验长度与摘要。跨用户请求返回404，未登录401；文件丢失/损坏返回脱敏503。浏览器退出登录后迟到图片不能进入新会话。
- 文件写入后数据库失败会清理本次新文件；进程在文件与数据库提交之间崩溃仍可能留下孤儿文件。清理策略、联合备份恢复、生产配额与分页仍待后续交付，不能把本段当成生产上传验收。
- 同用户同哈希提示重复，但允许独立草稿；不同用户不会互相得到提示。duplicate_of 目前仅上传响应提供。最终防重复入库依靠第二段的import终态与operations幂等，不依靠哈希唯一约束。

## 确认事务

确认请求不携带新草稿，只接受 expected_version。非排除行必须已核对、匹配本用户食材且明确数量/单位；先完整验证全部行，再在同一个 food.run_operation 用户锁与事务内调用 add_batch(operation=op)。质量、体积和计数不能互换，piece 必须为整数；kg/l 换算为库存 g/ml。至少包含一行，重复食材行各自创建批次。金额可以未知，不用于报价或预算。

到期日期必须与 user/package/estimate 来源一起填写；日期未知时来源必须 unknown，不根据购买日期推断。位置默认 fridge，可由用户更改；旧草稿缺少新增字段时使用 unknown/空日期/fridge 默认值。草稿允许日期尚未补齐，确认时严格验证。

确认后保存 completed、递增版本以及 result（operation_id、原始行号和批次结果）；取消为 cancelled。终态不可编辑、解析或重新确认；同键同参数重试返回原结果，异键重复确认返回409，旧版本也返回409。用户内文件哈希仅提示重复，新上传产生的不同草稿仍可独立确认，不能声称阻止了同图重新上传后的业务重复。

第二行失败时整单批次、事件、operation、结果和状态全部回滚。确认使用追加迁移0a23c671de89的nullable result列，保留既有小票记录。前端先保存再进入二次确认；未核对/未保存禁用确认，丢失响应时保留原幂等键，刷新恢复服务端终态。

视觉适配沿用配置的Chat Completions端点，仅发送系统抽取提示、schema和图片数据，不提供工具/DB/owner；禁止重定向，不自动重试，最多4000输出token、256KiB响应、默认30秒总超时，拒绝截断/refusal/tool_calls/多余字段。未配置时不发外部请求；选择自动识别前页面提示图片发送和费用。协议参考与真实验收入口见[真实视觉验收](validation/receipt-vision-acceptance.md)。

追加迁移1b34d782ef90保存parse_started_at/parse_finished_at及用户时间索引，不增加表。真实模型和授权中文票据仍为P7最后验收缺口；采购方案预算与报价继续独立。
