# P9备份故障保护与恢复失败演练

2026-09-17，第83节。按NEXT_SESSION及PLAN P9-01/02继续；模型新增0，累计聊天1663/视觉30。旧留出48/60、holdout_gate=failed和P5/P8/P9整体未完成保持。

## 修改与原因

deploy/manage.py原来直接打开manifest.json写入，写盘失败可能留下残缺的最终文件。现先写manifest.json.pending，flush与fsync成功、关闭文件后再更名发布；失败目录无最终manifest，不作为成功备份。残留pending保留供排查。

原stop调用位于try外，部分停止后报错不会执行start恢复。现纳入try/finally，对原先运行的web/api尝试恢复，不启动原先停止的应用。若Docker完全不可用，start仍可能失败，需人工按运行状态排查；未承诺自动灾难恢复。恢复读取manifest时新增schema_revision非空检查，在Docker操作前拒绝缺字段。

## 验证

- Windows与Linux同一组22项保护测试通过（原12项加新增10项，不合计44）。新增覆盖stop/dump/uploads/manifest/fsync失败，成功manifest哈希与未运行服务保持停止，以及数据库导入、图片导入、schema不符时保留部分数据、应用停止及拒绝二次恢复。
- Windows首次22个通过标记后，JUnit文件写入被沙箱拒绝，退出1；获准后使用新临时目录重跑，退出0，见p9-fault-windows-0917.xml。Linux在无网络、只读挂载当前源码的solomeal-api:local临时容器中退出0。两项原有依赖弃用警告保留。
- deploy/manage.py、deploy/fault_drill.py与backend/tests/test_deployment.py的ruff F/B/I通过。

## 实际故障

独立脚本[deploy/fault_drill.py](../../deploy/fault_drill.py)创建新证据目录，旧目录拒绝覆盖。三个Linux临时容器均无网络、只读根文件系统，内存256MiB、1CPU，临时目录16MiB，故障卷1MiB；使用合成2MiB图片数据，未挂载已有数据卷。真实系统返回ENOSPC/errno28：

| 故障 | 验证结果 |
| --- | --- |
| 图片备份输出写满 | 导出抛出ENOSPC，源图片字节不变 |
| 恢复暂存文件写满 | 导入抛出ENOSPC，目标目录仍为空 |
| 图片恢复目标写满 | 保留小于原图片的部分文件；再导入拒绝非空目标 |
| MySQL部分导入后非法SQL | 先创建合成表并插入1行，再报SQL执行失败；仅db运行，无api/web/migrate启动；第二次恢复拒绝非空库，原1行保留 |

结果及三路日志见[p9-fault-0917/results.json](p9-fault-0917/results.json)。SQL和tar均为仓库内新建合成夹具，无用户数据。MySQL使用新Compose项目solomeal-fault-68a00c4361e1，随机凭据保存在宿主临时私有目录，target.json仅记录路径；数据库未映射宿主端口。收尾stop成功，容器Exited(0)，命名卷保留，不清空后重跑。

## 边界与后续

实测的是受限tmpfs写满和MySQL客户端遇到非法SQL，不是宿主磁盘写满、MySQL数据盘写满、kill进程或主机断电。manifest中途写失败/fsync失败及恢复图片失败后的编排路径使用注入测试；真实tmpfs证明底层文件操作失败行为。没有检验掉电后的目录元数据持久性，不能把fsync文件等同于完整电源故障保证。

末次docker ps核对：源solomeal-acceptance-0916a的db/api/web仍健康；原恢复b和solomeal-dev-mysql仍停止；无现有业务数据读写、无源服务重建。没有执行完整后端、前端、浏览器、远程CI或真实模型请求，无提交推送。

下一步生产限流/分页、容器模型配置边界及P9-03演示/技术问答/新主机交付材料。P8原门槛未通过，P9整体不因本子阶段完成而标完成。安卓单人补充反馈按第82节保留，不推断受控弱网或真实Agent断线已验收。
