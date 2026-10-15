# SoloMeal后端工程增强交付说明（2026-10-15，M0～M5完成）

M0 → M1 → M2 → M3 → M4 → M4.5 → M5已依序完成。[草稿PR #3](https://github.com/xpzzzzz/SoloMeal/pull/3)已发布；代码提交03880fc的[实际CI](https://github.com/xpzzzzz/SoloMeal/actions/runs/38676874837)十个作业全部成功，包含正式CPU构建和联合恢复。未合并、未替换原18080/18088，付费模型0次。完整计数见[CI证据](validation/backend-m5-1015-01/ci-r2-complete.json)与[执行记录](backend-engineering-enhancement-progress.md)。

## 新增技术与作用

| 技术 | 业务问题与实际用途 |
| --- | --- |
| Locust、SQLAlchemy事件、MySQL EXPLAIN/ANALYZE | 在隔离合成数据上量取延迟/失败/SQL次数与计划，先找瓶颈再优化 |
| 批量读取、请求内历史权重复用 | 消除逐菜谱两次读取和重复历史权重计算，保留完整响应语义 |
| Celery、RabbitMQ quorum持久队列与发布确认 | HTTP快速受理，独立Worker执行耗时识别，消息只带TaskID |
| MySQL任务/outbox、执行令牌、有限重试/期限 | 持久化待办、恢复未完成任务，拒绝重复/迟到执行结果 |
| PaddleOCR CPU、保守字段规则、按需Vision LLM | 本地文字与位置提取、复用Schema和单位校验；歧义及冲突交给用户核对 |
| Docker多目标镜像、固定依赖及模型SHA256 | OCR仅装Worker，权重独立准备、运行时只读，隔离Windows与Linux的执行差异 |
| pytest、Playwright、GitHub Actions | 规则、真实数据库/消息链路、页面人工确认与持续验证 |

没有引入Redis、Kubernetes、额外异步框架或库存逻辑副本。

## 架构与执行流程

推荐/首页使用原确定性规则和事务；批量查询只减少数据库往返。同一请求的个人权重计算一次，授权、排序、缺料、精度和约束规则继续原语义。

小票上传保存私有图片。parse请求以原幂等键和版本在同一事务写操作、任务及outbox，返回202与TaskID。outbox在短事务间向RabbitMQ发送，Worker用执行令牌领取、释放DB连接，再进行OCR/VLM。完成时重新加锁检查版本、令牌、租约和总期限，合法结果只写可编辑草稿。用户编辑/取消使旧执行权失效；确认入库仍用原整单事务，未确认时没有库存写入。

OCR优先的hybrid先提取文本/置信度/顺序/坐标，再解析明确规格与购买份数。数量约重、范围或包装份数未知时留空；VLM辅助输出同样校验。冲突保存两种解释、保持不确定，不把高置信度或模型数字当作业务事实。三模式和手动能力独立可用，默认vlm_only是兼容选择，合成Mock对照不足以支持改默认或宣称成本下降。

架构图见[README技术闭环](../README.md#35-后端工程增强性能识别与可靠执行)。

## 关键代码

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/food.py`、`planning.py`、`personalization.py` | 批量菜谱视图与请求内复用 |
| `backend/app/services/receipt_jobs.py` | 受理、MySQL outbox、执行领取/提交、重试与废止 |
| `backend/app/jobs/celery_app.py`、`tasks.py`、`outbox.py`、`supervise.py` | 消息配置、Worker与派发进程监管 |
| `backend/app/services/receipt_ocr.py`、`receipt_rules.py`、`receipt_recognition.py` | CPU OCR适配、保守字段规则、三模式与冲突保护 |
| `backend/app/services/receipt_ocr_models.py`、`jobs/ocr_models.py` | 固定公共权重的独立取得与校验 |
| `backend/app/models/receipts.py`及三份新迁移 | 持久任务、微秒时间精度、模式与私有OCR证据 |
| `frontend/src/ReceiptPanel.tsx` | 异步状态、模式选择、输入保护、人工核对 |
| `compose.yaml`、`deploy/backend.Dockerfile`、`deploy/manage.py` | 正式部署与联合备份/恢复保护 |
| `.github/workflows/tests.yml`、`deploy/ci/`、`deploy/check_async_pipeline.py` | 持续验证及封闭Mock集成 |

## 性能实测

500菜谱推荐1029→31条SQL，首页1036→38条；固定时钟27份完整响应一致。相同隔离资源下5并发推荐P95原49702.5ms，优化后两轮4895.3/4884.9ms。100菜谱同场景1435.6/1418.4ms。并发20诊断原有2次503池等待超时，优化后20次均200，未扩池。原始失败和Nginx限流429保留，不用拒绝请求的快速响应证明业务吞吐量。

这些是合成数据、45秒测量窗口和单机资源下的观测值，不能外推生产容量。完整口径、Locust原始CSV/JSON、SQL计划和复算工具见[M1](performance/m1-baseline-1014.md)、[M2](performance/m2-optimization-1014.md)。

## 异步与识别验证

[M3](validation/receipt-async/m3-normal-workflow-1015.md)正常HTTP/MQ/Worker及页面两轮通过，MySQL85/85；[M4](validation/receipt-async/m4-reliability-1015.md)真实Worker SIGKILL、Broker停机、重复投递、双Worker、确认丢失、超时/非法数据、编辑/取消、浏览器丢响应通过。Worker退出确实发生过两次外部Mock执行，明确不承诺外部恰好一次。

[M4.5](validation/ocr/m45-hybrid-1015.md)6份冻结合成票18次模式实测：各9组商品的名称/数量/单位/金额匹配冻结真值，包含未知null。ocr_only的Mock调用0、vlm_only6、hybrid3。VLM是完美Oracle Mock，不能代表真实VLM质量/费用。首张含冷初始化27763.7ms，热OCR约725.8～1462.4ms；Mock仅2.6～3.1ms，不用于真实时延对比。真实MQ/CPU8场景和浏览器2/2通过，冲突数量空、失败明确failed、未确认库存0。

Linux x86_64/Python3.13实际CPU推理已验证，Windows仅wheel/依赖解析通过；原生Windows推理、ARM与GPU未验证。固定两套移动模型，默认关闭OCR、保留vlm_only。复杂长票、倾斜/手写/遮挡及真实用户修正量仍缺可信对照。

## 最终测试、CI与部署

最终[CI](https://github.com/xpzzzzz/SoloMeal/actions/runs/38676874837)在03880fc上十作业全成功：MySQL692通过/0失败（690.15秒），SQLite676通过/16跳过（208.54秒），前端68、浏览器41通过/4实机条件跳过、三个Python版本插件测试、Linux插件378＋300、mypy50文件和覆盖率92%通过；正式CPU镜像、模型关闭核心业务、三模式、异常与联合恢复均通过。四项实机浏览器条件跳过不记通过，较早真实环境记录分别保留。

历史本地证据集中在[验证目录](validation/backend-m5-1015-01/)。本地全量690项时SQLite674通过/16个MySQL专属跳过；前端68单测、构建、浏览器夹具41通过/4实机条件跳过、插件375＋298、工具隔离3项、模型/备份28项及后端F/E9/编译检查通过。Linux目标mypy50文件通过，Windows插件覆盖率91%达到原91%门槛。Windows原生mypy有6个POSIX符号诊断，未将其写成Linux CI失败或修改插件代码规避。

全量MySQL因测试容器缺Git有三项预检失败，补齐后三项复验通过；其后Docker虚拟盘发生I/O错误，完整运行中断，未记为全量通过。已停机保存数据盘/系统盘字节副本、核对摘要；首次复制少量块变化后的重新同步和最终一致性均有记录，原盘未删除或替换。引擎恢复后，原18088三服务healthy、live/ready200且镜像ID不变。该副本不代替业务备份恢复验收。

正式配方首次构建退出0，最终源码缓存构建和空模型卷初始化也完成，但新Worker依赖层检查发现101文件摘要不符及一项包元数据损坏。坏镜像保留；同版本旧兼容镜像17068文件全匹配，以它和当前源码生成有明确标记的本地恢复镜像，实际三模式/冲突/失败6场景、人工确认、采购、做饭与撤销通过。不能把该恢复镜像称作正式配方全新构建验收。

本地未完成项已由全新云端CI补验，不能把本地恢复镜像等同于正式构建。最终本机检查：18088 live/ready各200、原HEAD与索引保留；Docker控制接口仍在5秒读取检查中超时，C盘仅约0.73GiB，不继续大规模写入或执行磁盘清理。M5部署验收以云端干净环境为准，本机磁盘/控制接口修复仍属保留限制。见[已发布范围与授权](backend-engineering-review-1015.md)及[本机状态](validation/backend-m5-1015-01/final-local-state.json)。

本地联合备份另已实际完成：SQL118267字节、私有图片tar102400字节，manifest及摘要匹配；包含12条任务、模式及OCR证据列，版本f1b7d9e31015。备份后原运行writer恢复，再停止本轮验证项目保留卷；未把“已备份”记为“已完成恢复验收”。

集成脚本首轮在采购前创建菜谱时漏传必需source字段，得到422；只补齐合成夹具，未放宽业务Schema。R1完整6识别场景、人工确认、采购、做饭及撤销通过，首次失败日志/数据保留私有目录。

实际联合恢复在新项目恢复26表、7条任务和私有图片，启动Worker前全表摘要相同；空Broker中的未发布任务执行1次后parsed，库存不变、图片字节相同，迁移f1b7d9e31015。见[集成摘要](validation/backend-m5-1015-01/ci-r2-pipeline.json)。

正式构建、权重准备、三模式配置、私有卷、限流及备份/恢复命令见[部署指南](../deploy/README.md)。CI新增`receipt-pipeline`，构建正式CPU Worker，从空模型卷取得固定权重，使用实际MySQL/RabbitMQ/Celery及封闭Mock验证，全部作业进入ci-complete。没有将图片、正文、Token或数据库备份上传到CI产物。

## 能写进简历的三条亮点与追问

1. **定位并消除推荐查询的重复工作**：使用Locust/SQL计数/EXPLAIN定位逐菜谱查询和重复历史计算，批量读取及请求内复用将500菜谱推荐SQL1029降至31；27份完整响应一致，附受控P95对照与限制。
   - 为什么不先扩大连接池？池耗尽是慢请求长期占连接的结果；减少SQL往返与重复计算后先复测，避免用更多连接掩盖瓶颈。
   - 如何证明没有改变结果？同一冻结数据和时钟比较完整响应，并验证重复ID顺序、用户边界和查询次数；不是只比较返回条数。
2. **为小票构建持久异步执行与恢复链路**：Celery/RabbitMQ执行识别，MySQL outbox与原操作同事务，结合有限重试、版本和执行令牌，真实故障验证未出现重复入库或迟到覆盖。
   - 数据库提交但消息没发出去怎么办？outbox还在数据库，派发进程会重试；确认丢失可能重复发送，领取/提交时的令牌和状态防重复应用。
   - 能保证恰好一次吗？不能保证外部OCR/模型只执行一次；保证有效结果提交有边界，库存还须走人工确认与原幂等事务。
3. **实现CPU OCR与按需视觉辅助的人机核对链路**：保留文字/置信度/位置，以原Schema和单位规则解析，三模式可对照，歧义和冲突保留待核对；复用同一Celery任务系统。
   - 高置信度为什么数量仍空？OCR置信度只衡量文字读取，不能证明一盒还是多盒、约重是否实际重量；业务事实需要明确规格/份数或人工确认。
   - 为什么没有宣称省钱或更准确？只有6份合成票且VLM为Oracle Mock；调用选择机制可验证，真实效果和成本需要授权的真实模型与更有代表性的样本。

## 保留边界

单节点Broker非HA；无跨主机生产上线结论；历史浏览器首导航偶发超时根因仍未闭合，不放宽超时或预热掩盖。原P5/P8/P9留出/真人/新物理主机门槛不由本次工程改造自动满足。历史48/60、holdout_gate=failed、真人清晰度null保留。来源与许可证继续[上游说明](upstream.md)及根许可证。
