# A014 schema 空白单变量诊断

2026-09-11，执行前登记 a014-schema-whitespace-v1。依据 NEXT_SESSION、STATUS 第50节继续；持续模型外发和私有证据授权有效。

离线重建第45节失败首请求，messages/tools/wire 三哈希全部匹配。正文10448字符，其中工具schema8400字符。仅将工具schema的JSON分隔空格移除后，schema7694、正文9742字符，减少706字符（正文6.76%）。字符不等于token；没有足够证据将超时归因为输入长度。首请求尚无工具结果，不能靠删减结果解决这次失败。

唯一变量是工具schema序列化空白。解析后完整schema一致，协议说明、SYSTEM v8、结构化条件、用户合成消息逐字保持。保留所有8工具、类型/null/默认值/约束及确认语义；不改生产协议、.env、预算3000、时限30秒、模型qwen3.8-flash，thinking不发送，采样仍提供方默认。

最多一次请求至既有DashScope，不执行工具、不访问业务库、不健康探针、不重试。原目录保留，新私有目录 D:/SoloMeal-Acceptance/p8-A014-schema-whitespace-v1-0911-01。发送前落盘源报告/脚本/传输哈希与分析，响应留私有目录。判断是否返回recommend_meal并人工核对参数；即使通过也只代表首请求诊断，不代表最终回答或完整任务成功。失败则停止这条试次，不能继续上调或用旧final拼接成功。

backend目录执行：

```powershell
.venv/Scripts/python.exe scripts/probe_a014_compact.py --source D:/SoloMeal-Acceptance/p8-A014-chat-budget-v1-0910-01 --output D:/SoloMeal-Acceptance/p8-A014-schema-whitespace-v1-0911-01 --send-model
```

不加--send-model仅离线打印分析，不读取模型配置、不创建输出。完整真实统一配置仍待回答闭环后另行冻结。P8/P5未完成，门槛和留出不变。

## 实际结果

一次请求31.081943秒timeout，未返回HTTP状态/usage，未选择工具；脚本退出0仅表示诊断证据写完，不表示模型通过。无工具或业务执行，task_success=null。原始五个JSON完整保留，脱敏指标与哈希见[p8-a014-compact-0911.json](p8-a014-compact-0911.json)。未观察到响应，不能确定是提供方排队、推理、网络还是其他延迟；本次精简未解决超时，也不能推断它普遍无效。

本段真实聊天1、视觉0，token与费用未知；累计124已知聊天请求，另1个预算关机无返回尝试、30视觉。失败后没有重跑、增加等待或预算；生产协议仍v2，没有将试验序列化应用到业务。

18项探针测试通过（compact 7、timeout 5、final-budget 6），ruff通过，2个既有弃用警告。验证完整schema/其他消息不变、三个输入哈希和原参数拒绝漂移、成功/空正文/超时/HTTP失败均最多一次、旧文件不覆盖。未运行完整backend/MySQL/浏览器/远程CI/真人，不改开发库/根data/.env/前端/迁移/原插件，无提交推送。

下一步重新选择有证据支撑的延迟诊断变量：先离线汇总历史请求按首请求/最终请求的输入规模、输出/reasoning用量与超时分布，未知保持未知；必要时核对提供方当前聊天参数支持后，单独登记显式关闭thinking的聊天对照（尚未实现/发送，不沿用视觉参数）。不要继续微调空白或盲目重跑。完整A014回答、统一配置/三模式重复/留出仍待完成；单探针不进入正式cohort成绩。
