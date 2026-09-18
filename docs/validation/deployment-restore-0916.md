# P9本地部署、联合备份恢复与安卓试用准备

2026-09-16，第80节。按NEXT_SESSION第79节推进不依赖真人评分的P9工作。用户已指定安卓手机；实际设备测试和清晰度评分尚未执行。新模型请求0，累计聊天1663/视觉30。原留出48/60、holdout_gate=failed、P5/P8未完成保留。

## 已交付

- compose.yaml：独立MySQL、一次性Alembic迁移、非root API及Nginx前端；数据库健康后迁移，迁移成功后API，API就绪后Web。MySQL无宿主机端口，Web默认127.0.0.1:18080。
- 两个多阶段/独立Dockerfile、固定基础镜像digest、.dockerignore排除私有环境和数据；前后端lock文件在Linux镜像内成功安装，前端tsc/Vite构建通过。API实际UID10001，镜像内无/app/.env。
- deploy/manage.py：新建随机凭据文件、停写联合备份、仅空环境恢复。SQL及UUID图片tar的SHA256与schema版本写入manifest；失败不生成成功manifest，备份结束恢复原先运行的服务。
- backend/scripts/archive_uploads.py：只导入平铺UUID普通文件，拒绝路径穿越、软硬链接、目录、重复名和超大单文件；所有成员头在首次写入前检查。恢复部分失败不自动删除数据，目标保持停止，需另选新项目排查。
- deploy/demo.py：仅回环地址可创建新合成账号，用真实HTTP验证库存/做饭/撤销/手工小票及模型关闭降级；恢复后核对快照、图片和幂等重放。
- 部署说明deploy/README.md、docs/android-trial.md、四轮human-clarity-packet-0916.md与android-trial-form.json。表单全部人类评分/真机结果为null，不代填。

## 实际执行

Docker Engine29.6.1、Compose5.1.4可用。原solomeal-dev-mysql初始停止，未启动、未连接；MySQL80和其他项目容器未操作。新项目solomeal-acceptance-0916a/b使用各自命名卷、私有随机凭据和端口18080/18081。源服务、恢复服务均从各自空数据库/上传卷启动；这不是另一台全新物理主机验收。

1. 从固定Python3.13、Node24、Nginx及既有MySQL8.0镜像digest构建；空数据库迁移完成，db/api/web健康。
2. 源环境HTTP创建合成账号，录入300克米、菜谱；做饭扣80克到220、撤销恢复300。上传合成1像素PNG，手工填写2个鸡蛋并确认入库。视觉关闭，未外发图片。
3. Agent关闭时请求正确变为MODEL_NOT_CONFIGURED，页面显示尚未配置；普通手工功能仍可用，新增真实模型调用0。
4. 停止源web/api写入，导出数据库SQL及私有图片tar，写manifest，然后恢复源服务。
5. 在第二个全新Compose项目仅启动空MySQL，校验备份并导入数据库和图片；确认迁移版本后启动应用，健康检查通过。
6. 原合成凭据可在恢复环境登录；全部演示业务API快照、旧Agent状态与图片SHA256一致。重放原做饭和撤销幂等键返回既有结果，库存不重复增减。
7. 两库21张表的行数/内容SHA256一致（含alembic_version，排除验证登录新增的auth_sessions）。并非只比较库存总数。
8. 对运行中的恢复目标再次发起恢复被拒；停止应用后，对已非空的目标数据库恢复也被拒。没有覆盖目标数据，随后停止恢复项目。

私有证据D:/SoloMeal-Acceptance/p9-deployment-0916-01，含build/start日志、backup/{database.sql,uploads.tar,manifest.json}、合成凭据、API快照、表摘要、截图与拒绝记录。不要提交该目录。仓库同名JSON保存24份非凭据证据哈希及源码/镜像指纹，不复制备份原文或凭据。

## 验证结果

- Windows保护测试12通过；相同12项在Linux应用镜像内通过，不合计为24个不同用例。覆盖图片字节往返、拒绝覆盖、非法tar、重复成员、凭据文件拒绝覆盖、项目边界、校验失败前不操作Docker、非空/运行中拒绝和备份失败恢复服务。
- Linux依赖安装和前端构建通过；源与恢复服务各一次Chromium390×844窄屏冒烟通过，库存、撤销历史、小票页和模型关闭错误页均可读取，无页面异常/横向溢出。恢复库存截图目视核对。该浏览器为模拟移动设备，不是安卓真机。
- 改动Python文件ruff F/B/I通过；git diff --check通过。两项既有依赖弃用警告保留；Linux测试另有nonroot无法创建/app/.pytest_cache警告，不影响12项通过，未更改应用目录权限。
- 没有运行完整后端、正式工程60场景、完整前端E2E、远程CI或真实模型；没有提交/推送。数据库恢复是真实MySQL容器行为，不用SQLite替代。

## 当前运行状态

源项目solomeal-acceptance-0916a的db/api/web保持健康，Web仅本机http://127.0.0.1:18080。私有demo/credentials.json为合成试用账号。恢复项目solomeal-acceptance-0916b已停止，卷保留；原开发数据库仍停止。没有创建后台定时任务或更改防火墙。

app/scripts源码a602c174cc366cbc870b0af51c5a05e8436b7491504865016e750fcfdd562c93（66文件）；相对第79节新增私有文件归档脚本，生产服务/SYSTEM/工具schema和冻结评测JSON未改。部署和宿主机工具在各自目录独立留哈希。

## 阶段结论与下一步

P9-01部署骨架/健康检查/关闭模型降级和P9-02演示/联合备份恢复已实现并完成本地容器验收，P9整体保持进行中。尚欠公网HTTPS与访问策略、生产限流/分页、容器内真实模型路径、恢复中断/磁盘不足等故障演练、全新物理主机、完整文档/三分钟演示及发布准备，不因本次恢复通过删减。

下一步由用户在安卓设备执行试用并提交真实评分；USB reverse步骤和故障连接注意事项见docs/android-trial.md。仅知道设备平台不等于已收到设备实测。独立可推进P9恢复失败演练、生产运行边界及交付材料；真人清晰度与真机弱网保持null，不由Codex模拟结果替代。
