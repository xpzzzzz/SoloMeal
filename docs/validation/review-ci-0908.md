# 2026-09-08 接手审阅与浏览器 CI

本轮范围：核对交接/PLAN/STATUS/架构、最新前端与 E2E 实现，推进 P6 CI 接入。不是逐行全仓审计。未提交/推送、未运行远程工作流。

## 发现和修复

| 发现 | 影响与修复 |
|---|---|
| 偏好中文逗号未拆分 | 两件厨具或两种忌口被保存成一个名称，影响约束；main.tsx 两字段统一支持中英文逗号，移动回归检查服务端数组 |
| 工具执行断言与自身比较 | 该断言无法发现重复记录；严格断言只有一条 get_inventory，另有服务端 events 数量/step 断言 |
| 固定报价日期 | 30天后变成过期报价，整包装场景失效；改为运行当天，保质日期相对当天计算 |
| 固定800/1000ms等待 | CI慢时可能保存未完成即切页；改等PUT成功响应 |
| 默认Windows解释器/启动失败不清理 | Linux不能直接启动，失败可能残留；选择平台venv/PATH/覆盖变量，处理spawn/提前退出/超时并清理专用目录 |
| 文档漂移 | README多处“最新迁移”和未实现列表互相矛盾，PLAN声称LangGraph但代码无依赖；更新当前事实，补ADR-007与P7分段顺序 |

## CI 配置

.github/workflows/tests.yml 新增 browser-e2e：Ubuntu、Python3.13、Node24；安装 requirements.lock、npm ci、锁定Playwright对应Chromium与系统依赖；npm run e2e 自动构建，单并发、每文件180秒超时、job限15分钟。原frontend job也明确Node24。

所有动作固定SHA，setup-node v4.4.0通过 git ls-remote 核验为 49933ea5288caeca8642d1e84afbd3f7d6820020；新job加入ci-complete。测试只用临时SQLite/脚本模型，不用开发库或模型密钥。远程运行尚未发生，配置不等于Linux验收通过。

## 本地结果

Windows、本机现有venv与node_modules；无依赖重装。

| 检查 | 结果 |
|---|---|
| frontend: npm test | 15通过，9.26秒 |
| frontend: npm run e2e | 10通过，58.77秒：8浏览器业务+2夹具失败生命周期 |
| tsc/Vite（随E2E） | 通过，index-Boj7DWkk.js |
| backend: .venv/Scripts/python.exe -m pytest --basetemp=.tmp-review-0908-pytest -q | 退出0；81项中72通过/9跳过；MySQL专属跳过，2条既有弃用警告 |
| 原插件 test_unit.py | 372检查通过，0失败（新增动作使SHA检查计数增加） |
| 原插件 test_integration.py | 298检查通过，0失败 |
| 文档/差异检查 | git diff --check、文档空白与AGENTS/CLAUDE入口一致性通过 |
| 夹具清理 | 无本轮browser_fixture进程、无db-*临时数据库目录；根data/不存在 |

pytest采用配置-q加命令-q，首次终端省略总数；collect-only单独确认81项，执行输出9项skip。没有重复运行来改变结论。

未重跑MySQL/mypy/coverage；未检查真实模型效果或真机；移动为Chromium触摸/键盘仿真。新增E2E测试均保留可重放，截图在被忽略的frontend/.tmp-e2e。

## 后续

P7按私有上传/草稿、确认事务、真实视觉解析三段推进；未知数量和单位保持未知，确认前由用户补齐。远程CI、真实模型与正式评测继续单独记录，不将脚本模型测试计入AI效果。
