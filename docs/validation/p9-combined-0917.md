# P9 新web/api组合独立Compose项目合并部署验收

日期：2026-09-17。对应NEXT_SESSION第84节指定下一步：第84节API禁网配置、Nginx合成限流与页面夹具分别通过，本轮把同一镜像组合放入新独立Compose项目做合并部署验收。不代表P9整体完成，源18080未重部署。

## 对象与项目

- 新项目`solomeal-combined-0917`，绑定127.0.0.1:18082，私有目录D:/SoloMeal-Acceptance/p9-combined-0917-01（env、credentials不公开、不提交）。
- 镜像`solomeal-api:p9-boundaries-0917`（sha256:908cf165568b…，第84节已构建）与新构建`solomeal-web:p9-boundaries-0917`（bc46d5b23f83）。web镜像由同一前端源码与deploy/nginx.conf构建，含分组限流配置。
- 默认模型关闭（Agent/视觉均false，thinking为omit），数据库/上传为该项目独立命名卷。未触碰源solomeal-acceptance-0916a、恢复0916b、故障项目与开发库。

## 结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 启动 | db健康→migrate退出0→api/web健康，/health/ready 200 | ps.txt、migrate-exit.txt |
| 演示业务闭环 | demo.py seed通过：300克大米/2鸡蛋、做饭撤销、1像素小票手工确认入库、模型关闭失败run | seed-checks.json |
| 恢复一致性复核 | demo.py verify两次业务断言全部通过（含幂等重放与原图字节）；第二次仅因restore-checks.json已存在按设计拒绝覆盖而退出非零，非业务失败 | restore-checks.json（首次） |
| 模型关闭降级 | API返回MODEL_NOT_CONFIGURED；助手页显示"需先在后端配置模型"、发送禁用、历史失败run可见 | ui-agent-disabled.txt、seed断言 |
| SQL分页 | 第二合成账号205个批次：默认GET返回100，limit=200分批共读回205；limit=0/201、offset=-1/100001均422 | combined-checks.json |
| 普通请求限流 | 真实Nginx入口150次快速GET：31次429，全部带Retry-After:60与RATE_LIMITED JSON，其余200；期间/health/ready连续200（豁免）；6秒后恢复200 | combined-checks.json |
| 模型路径限流 | 40次advance（不存在的run）：31次429同契约，其余422；证明30r/m桶在合并堆栈生效 | combined-checks.json |
| 认证限流 | 20次快速login：10次429同契约、10次401；5r/m桶生效。按设计最后执行，其后未再登录 | auth-flood-checks.json |
| 浏览器冒烟 | 真实浏览器登录演示账号，库存页显示大米300克/鸡蛋2个，助手页显示关闭状态与历史失败run | ui-inventory.txt、ui-agent-disabled.txt |
| ruff F/B/I | deploy/verify_deployment.py通过 | 脚本sha256 d2e510ee85d9… |

429拒绝数量受请求时序影响，不作为固定性能门槛。本轮IDE浏览器视口隐藏（viewport 0x0），截图不可用，以页面结构快照文字代替图片证据；库存/助手页内容经快照逐字核对。

## 新增工具

deploy/verify_deployment.py：对运行中的回环部署复验分页与三类限流桶。checks模式先跑（登录演示账号、注册第二账号造205批次、普通桶/模型桶压测与健康豁免、6秒恢复），auth-flood模式最后跑（耗尽登录/注册共享配额）。证据JSON不含凭据，输出文件按"x"模式拒绝覆盖。供新主机交付清单复用。

## 状态与限制

- 合并部署验收通过的是"同一镜像组合在真实Compose堆栈中同时生效"：限流契约、分页边界、模型关闭降级、演示业务闭环与浏览器冒烟。第84节的禁网配置与合成上游限流结论不变，本轮不重测。
- 未覆盖：真实模型容器外发（仍只有替身/禁网证据）、429在真实浏览器中的页面提示（第84节为拦截合成）、受控弱网/真实Agent断线、主机断电、MySQL数据盘写满、新物理主机与三分钟录制。P5/P8/P9整体未完成，旧留出48/60与holdout_gate=failed保持。
- 模型请求新增0，累计聊天1663/视觉30不变。无提交推送。
- 项目solomeal-combined-0917已stop、卷与证据保留，可按deploy/README重新up；不执行down -v。源18080验收前后均200健康，未重部署。

## 证据哈希（私有目录D:/SoloMeal-Acceptance/p9-combined-0917-01）

- seed-checks.json e5396323872e…，restore-checks.json 2372d502e953…，before-backup.json 38c7aedee63a…
- combined-checks.json 0836e6623066…，auth-flood-checks.json 7d8cc1b7ff3c…
- ps.txt cb0161b7b14c…，migrate-exit.txt bc5e2aa934b3…
- ui-inventory.txt 93bf5e0bef58…，ui-agent-disabled.txt 7e6da02cddbc…
- combined.env与credentials.json仅存私有目录，不列哈希、不复制。

下一步：按docs/delivery.md预演三分钟演示（可用本项目或新起演示项目），再推进受控弱网/真实Agent断线；新物理主机、主机断电与MySQL数据盘写满另列。旧模型批次不重跑或追加。
