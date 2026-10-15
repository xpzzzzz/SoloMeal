# SoloMeal 单机部署与联合恢复

本目录交付本机Docker Compose部署、模型关闭降级、合成演示和数据库/私有小票联合备份恢复。2026-09-17补充Nginx请求限流、列表分页和容器模型配置验证；安卓五项单人试用反馈已收录。公网TLS、受控弱网和新物理主机验收仍未完成。不要将本地通过称为生产上线。三分钟演示、技术问答与新主机清单见[交付手册](../docs/delivery.md)。

依赖：Docker Engine/Compose，以及运行管理脚本的Python 3.12+；demo.py另需httpx（项目backend/.venv已安装）。宿主机不需要安装MySQL。数据库仅在Compose网络内可访问，没有宿主机3306映射。不会使用原有MySQL80或solomeal-dev-mysql。

## 启动空环境

在仓库根目录执行，下面路径与项目名是示例，可改为自己的私有目录和独立项目名。管理脚本仅接受solomeal-前缀且拒绝保留的solomeal-dev/solomeal-test；不要复用开发库名称或已有别人的Compose项目。

```powershell
backend/.venv/Scripts/python.exe deploy/manage.py init --env-file D:/SoloMeal-Private/demo.env --port 18080
docker compose --env-file D:/SoloMeal-Private/demo.env -p solomeal-demo up -d --build --wait --wait-timeout 180
```

init只创建新文件，不覆盖；随机数据库密码不打印。不要提交env文件、credentials.json或备份。Linux可把解释器换为backend/.venv/bin/python，私有路径替换为本人目录。当前基础镜像固定到实际拉取的digest，应用包按两个lock文件安装。

启动顺序是数据库健康→一次性迁移成功→API就绪→Web。依赖条件采用[Docker Compose官方启动顺序说明](https://docs.docker.com/compose/how-tos/startup-order/)。api使用非root用户，uploads命名卷与数据库命名卷随项目隔离；web只挂载前端产物，不能静态读取私有图片。API和健康检查由Nginx同源代理，SSE关闭代理缓冲。

默认访问http://127.0.0.1:18080，仅本机开放。默认Agent与视觉均关闭，库存/菜谱/手工小票/做饭/撤销仍可用。模型关闭时Agent返回MODEL_NOT_CONFIGURED，不发送真实模型请求。

需要模型时在私有env中设置SOLOMEAL_AGENT_ENABLED、SOLOMEAL_MODEL_BASE_URL、SOLOMEAL_MODEL_NAME、SOLOMEAL_MODEL_API_KEY和SOLOMEAL_MODEL_TOOL_PROTOCOL，再重新创建api服务。视觉另用SOLOMEAL_RECEIPT_VISION_ENABLED开启。Compose现在直接传递以下参数，api与migrate保持一致：

| 参数 | 默认/范围 | 含义 |
| --- | --- | --- |
| SOLOMEAL_MODEL_ENABLE_THINKING | omit / true / false | 聊天提供方扩展；omit不发送字段 |
| SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING | omit / true / false | 视觉扩展，与聊天独立 |
| SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS | 1500 / 1～3000 | 聊天输出预算，聊天时限仍30秒 |
| SOLOMEAL_RECEIPT_PARSE_DAILY_LIMIT | 10 / 1～100 | 每用户每日视觉解析次数 |
| SOLOMEAL_RECEIPT_PARSER_TIMEOUT_SECONDS | 30 / (0,60] | 视觉解析超时秒数 |

thinking不配置等同omit，显式空字符串无效；数字参数显式空值或越界启动报错。既往Qwen验收使用json协议、聊天3000和两个thinking=false，复现时须明确配置，不能只填模型名。此次验证包括禁网容器配置加载与HTTP替身，不包含新真实模型调用。密钥不进入前端，不打印完整compose config或容器环境。

## 后端增强：RabbitMQ、CPU OCR与任务恢复（2026-10-15）

正式Compose新增单节点RabbitMQ和Celery Worker。API与迁移使用`deploy/backend.Dockerfile`的`api`目标；Worker使用`worker`目标，独立安装[锁定的CPU依赖](../backend/requirements-ocr.lock)，API中不安装Paddle。当前完整推理验证平台为Linux x86_64/Python3.13 CPU；Windows开发使用Docker Linux Worker，原生Windows仅检查wheel/依赖解析。未要求GPU，未验证ARM。

首次`up --build`会构建全部常驻服务，Worker OCR包及系统库需要下载；为Worker预留2 CPU/2GiB是本轮验证资源，不是任何机器上的最低保证。数据库/RabbitMQ只在项目网络内通信，无宿主机端口。API写uploads，Worker只读uploads与ocr_models；消息仅含任务UUID，业务状态和私有OCR证据保存在MySQL。

初始化现在额外生成独立`RABBITMQ_PASSWORD`，默认关闭OCR/视觉，默认模式`vlm_only`。已有env如未来启用新Compose，应先在仓库外补生成的十六进制MQ密码，切勿输出完整配置或复制真实模型密钥到报告。更改开关后需同时重新创建api/worker。

启用CPU OCR前，先在私有env设置`SOLOMEAL_RECEIPT_OCR_ENABLED=true`，可显式选择`SOLOMEAL_RECEIPT_RECOGNITION_MODE=ocr_only`或`hybrid`。使用相同env/项目执行一次权重准备：

```powershell
docker compose --env-file D:/SoloMeal-Private/demo.env -p solomeal-demo build api worker web
docker compose --env-file D:/SoloMeal-Private/demo.env -p solomeal-demo --profile ocr-setup run --rm --no-deps ocr-models
docker compose --env-file D:/SoloMeal-Private/demo.env -p solomeal-demo up -d --no-build --wait --wait-timeout 240
docker compose --env-file D:/SoloMeal-Private/demo.env -p solomeal-demo exec -T worker python -m app.jobs.ocr_models --check
```

准备命令仅从[PaddleOCR官方文档](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)所列BOS地址下载PP-OCRv5_mobile_det/rec，每个模型3份文件按[固定SHA256](../backend/app/services/ocr_models_manifest.json)核验后才发布目录。权重由项目命名卷持久化，不需要开发机缓存；模型卷是公开模型缓存，不含用户图片，可由固定来源重新生成。已有损坏/未知目录不会被自动覆盖，应另建模型卷排查。运行时Worker只读取，不在识别请求中下载权重。

| 配置 | 默认 | 行为 |
| --- | --- | --- |
| `SOLOMEAL_RECEIPT_OCR_ENABLED` | false | 显式开启本地OCR |
| `SOLOMEAL_RECEIPT_RECOGNITION_MODE` | vlm_only | 三模式之一，受理时固定到任务 |
| `SOLOMEAL_RECEIPT_OCR_MIN_CONFIDENCE` | 0.85 | 仅作为按需辅助的信号，不能据此猜数量 |
| `SOLOMEAL_RECEIPT_OCR_MODEL_DIR` | Compose固定为/var/lib/solomeal/ocr-models | 本地固定权重目录 |

OCR缺依赖/权重或运行失败时，hybrid在视觉已配置的情况下使用原视觉链路；ocr_only明确失败以保证本地模式不外传。视觉未配置且OCR有效但有歧义时，保留未知供人工核对；OCR与视觉均不可用时任务明确failed，手动编辑仍可用。所有模式都只生成草稿，未经用户逐项核对及整单确认不能写库存。

API202受理，任务/outbox与原幂等操作一起提交，outbox监管进程向durable quorum队列发布并等待确认。Celery采用prefork、late ack、prefetch1和有限重试；执行租约默认120秒、硬上限90秒、总期限900秒、最多3次、重试基准10秒。状态以MySQL为准，消息或发布确认丢失可由outbox重新派发。解析期间不持数据库连接。Worker退出可能使外部解析重执行，不能承诺外部调用恰好一次；RabbitMQ单节点不具备集群HA。

备份现在同时停止当时正在运行的web/api/**worker**，再导出全库与私有图片，完成后仅恢复原运行服务。`receipt_parse_tasks`、识别模式、OCR证据和操作幂等结果都包含在全库备份中。恢复拒绝运行中的Worker；使用同版本镜像在新项目恢复后，先准备公开模型缓存再启动Worker。**Broker卷不作为业务事实备份**：未完成任务由数据库outbox恢复；已过期任务明确结束，不能延长期限伪装仍可执行。维护窗口仍不得从外部启动脚本写库。

CI专用`deploy/ci/compose.yaml`显式加入封闭的合成Mock服务，只用于独立测试项目；不用于用户部署。`deploy/check_async_pipeline.py`以实际MySQL/RabbitMQ/Celery/CPU OCR验证三模式、冲突、失败和人工入库，不连接付费模型。原阶段证据见[M3](../docs/validation/receipt-async/m3-normal-workflow-1015.md)、[M4](../docs/validation/receipt-async/m4-reliability-1015.md)、[M4.5](../docs/validation/ocr/m45-hybrid-1015.md)。

## 请求与列表边界

Nginx按实际连接IP共享限流：所有/api/请求20次/秒、突发80；登录/注册合计5次/分钟、突发10；Agent advance与小票parse合计30次/分钟、突发16。突发为漏桶的额外容忍请求，之后按速率恢复。限流返回HTTP429、JSON错误RATE_LIMITED与Retry-After:60；页面说明等待后重试，不自动重放写操作。健康检查不受这些限流影响。已有SSE连接不因后续请求限流而截断。

这些限制保护Compose的Nginx入口，直接启动Uvicorn没有相同入口保护。API和数据库未映射宿主机端口。默认不信任X-Forwarded-For；同一NAT出口共享额度。若另加可信反向代理，应明确配置可信来源并重新验证，不能直接信任任意客户端头。该机制不替代并发连接上限、按账号总费用配额或公网防护。

GET列表接受limit（默认100，1～200）、offset（默认0，0～100000），非法值返回422，响应仍为数组。覆盖ingredients、inventory、inventory/events、recipes、cooking、plans、plans/{id}/revisions、quotes、shopping、receipts、agent/runs、agent/sessions。过滤与用户身份先应用，稳定排序后在SQL中分页。小于limit表示已到末页，恰好满页时继续读下一页直到不足limit。内部推荐/Agent库存读取保留全量语义，不把第一页当全部库存。

当前前端为保持选择器和汇总完整，顺序读取200条一页，单列表超过10000条明确报错；还不是滚动加载/虚拟列表。跨页期间发生新增、删除或改名时offset不提供一致性快照，应刷新。会话详情中的runs等嵌套集合仍可能增长，服务端推荐也未引入总量限制；这些是后续大数据量边界，不能把本次分页称为所有响应均有固定大小。

可用合成上游复验限流与禁网配置（输出目录必须新建，使用已构建的新镜像）：

```powershell
backend/.venv/Scripts/python.exe deploy/verify_boundaries.py --directory docs/validation/my-new-boundaries-run --api-image solomeal-api:local
```

脚本只创建临时Nginx、合成上游和禁网API容器，完成后清理自己的容器，不连接数据库、不调用模型。初次结果见[P9边界报告](../docs/validation/p9-boundaries-0917.md)。

对已启动的回环部署（先跑demo.py seed），可复验真实堆栈的分页与三类限流桶（合并验收见[P9合并部署报告](../docs/validation/p9-combined-0917.md)）：

```powershell
backend/.venv/Scripts/python.exe deploy/verify_deployment.py checks --url http://127.0.0.1:18082 --evidence D:/SoloMeal-Private/demo-evidence
backend/.venv/Scripts/python.exe deploy/verify_deployment.py auth-flood --url http://127.0.0.1:18082 --evidence D:/SoloMeal-Private/demo-evidence
```

checks模式注册第二个合成账号造205个批次，验证默认页100/分批读全/非法参数422、普通桶与模型桶429契约、健康检查豁免和恢复。auth-flood会耗尽连接地址的登录/注册共享配额，必须最后运行；之后该地址约一分钟内无法登录。证据JSON不含凭据，输出文件拒绝覆盖。

## 合成演示数据

```powershell
backend/.venv/Scripts/python.exe deploy/demo.py seed --url http://127.0.0.1:18080 --evidence D:/SoloMeal-Private/demo-evidence
```

该脚本仅允许回环地址，创建新合成账号；私有credentials.json保存登录信息。演示300克大米、2个鸡蛋、一份做饭及撤销、一张合成1像素小票经手工填写确认入库，另留一条模型关闭失败记录。通过实际HTTP API执行，不访问用户既有账号。旧证据目录拒绝覆盖；不要反复向真实环境制造演示账号。

## 备份

```powershell
backend/.venv/Scripts/python.exe deploy/manage.py backup --project solomeal-demo --env-file D:/SoloMeal-Private/demo.env --directory D:/SoloMeal-Private/backup-001
```

短暂停止该项目正在运行的web/api，取得SQL逻辑备份和私有文件tar，再恢复原先运行的服务；不启动原先已停止的服务。单实例维护窗口内不要另行启动迁移、脚本写入或其他数据库客户端。SQL使用[MySQL mysqldump](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)的single-transaction、hex-blob和utf8mb4；跨数据库与文件的一致性依靠停止应用写入，不只靠SQL事务快照。

manifest.json最后生成，含schema版本和两个文件的SHA256；没有manifest的目录不视为成功备份。备份内容含数据库用户信息及私有图片，应放在访问受限、另有离线副本的位置；脚本未实现加密、远程上传或定期调度。保存对应源码版本和镜像ID，恢复时先使用相同版本，不直接升级到未知版本。

## 恢复到新环境

```powershell
backend/.venv/Scripts/python.exe deploy/manage.py init --env-file D:/SoloMeal-Private/restored.env --port 18081
backend/.venv/Scripts/python.exe deploy/manage.py restore --project solomeal-restored --env-file D:/SoloMeal-Private/restored.env --directory D:/SoloMeal-Private/backup-001
docker compose --env-file D:/SoloMeal-Private/restored.env -p solomeal-restored up -d --wait --wait-timeout 180
backend/.venv/Scripts/python.exe deploy/demo.py verify --url http://127.0.0.1:18081 --evidence D:/SoloMeal-Private/demo-evidence
```

镜像须预先构建（同一Docker主机已有镜像可直接复用；另一主机先build api web）。恢复工具先校验文件哈希，拒绝运行中的应用/迁移、非空数据库和非空上传卷；不删除、不覆盖旧数据。仅允许UUID平铺普通文件，拒绝绝对/父目录路径、软硬链接、目录和重复成员。恢复失败保持目标停止且可检查；不要清理旧环境来凑空库，另选新项目排查。

verify使用原合成账号重新登录，比较全部演示业务快照、旧Agent状态和原图字节，并重放相同做饭/撤销幂等键确认不重复写入。恢复后先核对健康检查、数量、历史和私有图片，再考虑切换访问入口。当前工具不自动替换生产服务。

## 停止与后续

2026-09-17故障演练：22项保护测试在Windows/Linux通过；1MiB临时卷的备份输出、恢复暂存和图片目标写满，以及新MySQL部分导入失败/非空重试拒绝通过。见[故障报告](../docs/validation/p9-fault-0917.md)。manifest现先写pending并flush/fsync，成功后更名；失败目录不可用于恢复。不要编辑manifest或删除部分恢复数据以强行重试，另选新项目。恢复失败时应用保持停止，db可能仍运行供检查；检查后用stop保留卷。主机断电、MySQL数据盘写满尚未演练。

`docker compose --env-file 私有env -p 项目名 stop`只停服务、保留卷；再次up恢复。不要对含用户数据的项目执行down -v。本次验收保留源演示环境18080，恢复环境18081验证后停止，命名卷和证据保留。

安卓试用见[真机步骤](../docs/android-trial.md)，当前默认回环绑定不修改防火墙或开放公网。正式交付还需HTTPS/访问策略、资源与并发配额、大列表及嵌套历史边界、主机断电/MySQL数据盘写满演练、依赖更新与全新主机验收，见PLAN P9及STATUS。本轮边界变更尚未更新源18080的运行服务。

2026-10-15正式干净构建与联合恢复的[实际CI](https://github.com/xpzzzzz/SoloMeal/actions/runs/38676874837)已通过；[26表/图片/未发布任务摘要](../docs/validation/backend-m5-1015-01/ci-r2-pipeline.json)。Nginx通过Docker内置DNS动态解析API，配置重建导致API地址更换后会刷新；部署检查重新读取实时就绪接口，不能仅依赖旧容器缓存的healthy状态。宿主机磁盘及Docker控制超时的保留限制见[最终交付](../docs/backend-engineering-delivery-1015.md)，本轮未替换18080/18088。
