# 调试批次预登记与配置审计

2026-09-10。新增 `backend/scripts/cohort_agent.py`，仅离线读写JSON，无模型/数据库调用。当前范围为全部20调试场景、3模式、各3次，共180个位置；留出执行器及评分尚未适配，不读取留出内容用于调参。A014仍失败，本段没有创建正式运行批次或冻结生产配置。

register读取显式config文件，要求试次根目录不存在且位于仓库外；独占创建manifest，输出其SHA256。清单固定场景/模式/重复号/目录，绑定原数据、协议及两份勘误哈希和登记时间，不启动试次、不创建试次目录。audit必须提供登记时独立保存的manifest哈希，拒绝配置/清单替换、删位置、旧数据与旧试次混入。

审计逐项检查attempt中的commit/源码/prompt/SYSTEM/schema/协议选择/预算/30秒时限/确认范围；各请求核对模型、传输版本、采样值、thinking及预算/时限。直接模型无工具，按实际native文本传输校验，不强称与Agent的JSON工具协议相同；固定流程不允许模型调用。核对请求序列、8次上限、结果配对、report身份和调用元数据一致性，附各文件哈希，意外新增目录单独列出。

结果保留not_started、incomplete、failed、awaiting_review、invalid_evidence；未启动同样保留在180分母中。工具客观通过只进入awaiting_review，不自动认定任务成功。success_rate=null、P8 gate=incomplete；此工具不替代review_agent.py语义/人工评审，也未实现三模式门槛统计、P95或完整留出评分。

使用（在backend目录；先完成A014闭环和配置决策）：

```powershell
.venv/Scripts/python.exe scripts/cohort_agent.py register --config CONFIG.json --trial-root D:/SoloMeal-Acceptance/NEW-COHORT --output MANIFEST.json
# 独立保存上一步输出的SHA256；执行器输出到manifest指定目录。
.venv/Scripts/python.exe scripts/cohort_agent.py audit --manifest MANIFEST.json --manifest-sha256 SAVED_SHA256 --output AUDIT-NEW.json
```

config必须恰有attempt、model两节，必需键由脚本ATTEMPT_KEYS/MODEL_KEYS定义。字段应来自将运行版本的源码/提示/schema和明确选定的模型配置；不得照抄旧试次并声称冻结了当前源码。SHA应在执行前独立保存，工具不提供密码签名或防篡改存储。审计是事后检查，不是执行器的运行前拦截；自动执行/中断恢复联动仍待接入。

本段测试覆盖180未启动、三模式失败、缺请求结果/孤立结果、配置不一致、旧试次、report不一致、清单篡改、不可覆盖、未完成/意外目录及仅等待评审的客观通过。初轮11失败/21通过因测试临时目录位于真实仓库保护范围，修正测试独立仓库边界，生产限制未放宽。最终结果见STATUS第46节。

新增真实聊天/视觉0；旧失败和freeze保留，未改业务服务、.env、开发库、根data、前端、迁移或原插件，无提交推送。
