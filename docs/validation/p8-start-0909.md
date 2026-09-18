# P8首段：场景、门槛和工程运行器

2026-09-09。本轮新增真实模型调用0次；没有修改业务实现、数据库迁移、前端或原插件。P8为IN_PROGRESS。

新增evaluation/版本化清单100项：60已有工程回归、20新合成Agent调试、20新合成留出。逐项预期、夹具数据、三模式比较及限制已定义；后40项未运行。留出是尚未用于模型调试的合成场景，不是独立真实用户数据。首次真实跑分前的阈值及文件哈希已固定，详见[协议](../../evaluation/README.md)。

工程执行命令（仓库根目录）：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/evaluate.py --output docs/validation/p8-engineering-0909-01
```

首轮[原始报告](p8-engineering-0909-01/report.json)、[日志](p8-engineering-0909-01/pytest.log)与JUnit保留。结果61测试实例通过、12实例MySQL专属跳过，112.71秒；按冻结清单归并为53工程场景通过、7跳过、0失败。40个Agent场景为not_run，两个gate均incomplete，token/成本/效果为null。不能把61当60项场景的通过数，也不能把无失败解读为P8通过。

报告按选择器合并参数实例；失败、跳过、缺失均不通过。运行器使用新临时SQLite、拒绝外部DB覆盖、关闭真实模型、禁止覆盖证据目录，先写attempt再测试；子进程异常退出不得通过。记录commit与包含未提交Python应用/测试/脚本的源码哈希，不把当前HEAD当作全部被测代码。首轮之后增加协议哈希及httpx/pytest版本元数据，未覆盖首轮报告；未因元数据变动重跑业务。

最终运行器自测（backend目录）：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_evaluation.py -o addopts='' -p no:cacheprovider --basetemp=.tmp-p8-eval-final-0909 -q
.venv/Scripts/python.exe -m ruff check scripts/evaluate.py tests/test_evaluation.py --select F,B,I
```

6 passed，ruff通过。覆盖文件冻结、60/20/20划分、跳过/缺失/部分参数结果、重复选择器、外部DB和证据覆盖拒绝。首版专项5 passed，新增冻结哈希校验后最终6 passed，不相加。保留两条既有Starlette/httpx/anyio弃用警告。

仅读取本项目Settings的配置布尔值：模型名与密钥存在，聊天Agent关闭、视觉开启；没有输出凭据、改写.env或实际请求模型。聊天适配器丢弃usage且缺独立观测元数据；下一段实现该接口以及三种模式的隔离驱动器，再依协议先调试后运行留出。当前只是评测入口，不能声称真实模型兼容或Agent闭环完成。

本轮未跑MySQL、完整backend、浏览器、远程CI或原插件；相应历史证据仍以原日期为准。未提交/推送，开发库与根data未操作。真实试用、独立小票、完整成本、人工清晰度、P9部署仍未完成。
