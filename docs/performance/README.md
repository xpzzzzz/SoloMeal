# SoloMeal M1 可重复性能诊断工具

这些工具只用于独立 Web 应用的性能基线，不修改 `backend/app`、原插件、事务规则或安全校验。阶段顺序与停止规则见 [增强计划](../backend-engineering-enhancement-plan-v1.0.md)。所有模型路径关闭；OCR/Celery/RabbitMQ 不在 M1 实现。

M5兼容性收口：构建显式选择API目标，RabbitMQ/Worker在性能overlay中为未启用profile，OCR开关强制关闭并纳入隔离检查。后续使用当前源码重跑得到的是当前实现指标；复现原M1基线需要相同的优化前源码或当时记录的API镜像ID，不能把当前优化后的重跑称为原基线。原M1/M2镜像与卷保留在本机，运行元数据保存各自源码摘要和镜像ID。

## 组成与隔离

- `run_m1.py`：新建环境、诊断、单次负载，拒绝已有项目/私有目录/结果目录。项目名称只能为 `solomeal-perf-m1-*`。
- `compose.override.yaml`：叠加原 Compose，新库 `solomeal_perf_m1`、独立命名卷、模型开关/密钥关闭；原 API 和 Nginx 保持业务配置。API/数据库各2CPU和1GiB，Locust为1CPU和512MiB，API仍单个Uvicorn进程、池5+10。
- `seed_data.py`：固定种子、显式基准日期，5用户×3规模，包含食材/别名、偏好、菜谱、库存、历史、反馈、报价和采购；拒绝非空库。历史是只读快照夹具，不是做饭/撤销的写入验收夹具。
- `locustfile.py`：五个认证只读端点，轮询循环，think time 50～100ms；直接使用合成测试会话，真实执行服务端认证，不把注册/登录混入负载。
- `instrumented_app.py`：独立 diagnostic 服务的 SQLAlchemy 事件与连接池计时。压力 API 使用原始工厂，不加载诊断 wrapper。
- `request_probe.py` / `sql_profile.py`：单请求与并发探针、实际 SELECT 的 MySQL EXPLAIN/EXPLAIN ANALYZE、服务函数 cProfile。
- `checkpoint.py`：数据量验证及负载前后15张表语义摘要对照，密码/会话摘要/会话过期时间不纳入公开摘要。
- `resource_sampler.py`：只采样该测试项目容器，约5～7秒一次；不声称抓住所有瞬时峰值。
- `summarize.py`：从原始 CSV/JSON/JSONL 离线重算样本数、错误、RPS与分位数。
- `test_sandbox_tools.py`：拒绝开发库、试用项目和模型配置的专项保护测试。

数据库密码与会话 Token 只放在用户指定的仓库外私有目录。输出只含合成数据、脱敏 SQL、请求指标与必要元数据；工具不打印私有 env 或 Token。不要把运行目录放进镜像/公开日志，原图与用户业务数据不参与本测试。

## 新建与运行

在仓库根目录使用 Python3.13 和 Docker。示例私有/结果目录必须不存在；端口由脚本先检查，再由 Compose 绑定。API和web仅回环开放，数据库不映射宿主机端口。

```text
python -B docs/performance/run_m1.py setup --project solomeal-perf-m1-example01 --private-dir D:/SoloMeal-Private/perf-example01 --run-dir D:/Code/meal-manager/docs/performance/results/example01
python -B docs/performance/run_m1.py diagnose --state D:/SoloMeal-Private/perf-example01/state.json
python -B docs/performance/run_m1.py load --state D:/SoloMeal-Private/perf-example01/state.json --scale 100 --users 5 --seconds 45 --entry api --run api-r100-u5-a
python -B docs/performance/run_matrix.py --state D:/SoloMeal-Private/perf-example01/state.json --seconds 45
python -B docs/performance/summarize.py docs/performance/results/example01
```

单次 `load` 的 `--mode 0/1/2/3/4` 分别只测库存/菜谱/首页/推荐/历史；默认 mixed 五项循环。`--entry nginx` 使用未改限流的 Nginx。运行名称必须唯一，已有结果不能覆盖。正式矩阵中500规模的20用户有明确跳过记录；这是依据本轮实测7.3秒串行耗时设定的边界，不是通用容量标准。

初次工具镜像只用 Locust2.46.7 解析依赖，本轮实际安装后已将37个包完整冻结到 `tools-requirements.lock`。基础 Python 与 MySQL 镜像有 digest；API使用当前工作区构建独立 tag，源文件与实际镜像ID保存在结果元数据。具体 tag 不能替代镜像ID。工具安装/建库/数据生成不计入负载时长。

若初次安装或环境就绪失败，保留私有日志、已生成 state 和原有证据；查明原因后可用 `finish-setup --state ...` 完成尚未种数据的同一新环境。它仍会拒绝覆盖夹具或已有数据，不自动清库。首轮健康检查库名与工具构建时限问题的实际记录见 M1 报告。

## 诊断与数据校验命令

下面 `COMPOSE` 表示由 `context(state.json)` 生成的、包含两个配置文件和明确测试项目名的命令前缀。不要改成不带项目名的裸 Compose：

```text
COMPOSE exec -T diagnostic python /perf/checkpoint.py --name before
COMPOSE exec -T diagnostic python /perf/sql_profile.py
python -B docs/performance/run_m1.py diagnose --state PRIVATE/state.json --scale 100 --concurrency 20 --prefix parallel
COMPOSE exec -T diagnostic python /perf/checkpoint.py --name after
COMPOSE stop
```

实际 CLI 前缀可由 `run_m1.context()` 在本地构造，包含私有 env 路径但不需要输出其内容。`checkpoint` 和 profile 的证据文件用排他创建，重跑应使用新运行目录/项目。SQL探针可追加 JSONL，但用不同 prefix 区分试次，不能覆盖失败。

停止只停止本次项目，保留数据卷和结果；不要操作18080/18088或历史项目，不执行 `down -v`。本轮基线见 [M1报告](m1-baseline-1014.md)；用户最新授权在阶段验证和报告完成后依序推进至M5或额度耗尽。

## 指标口径

1. 所有用户生成完成后预热5秒，保留 warmup 原始样本；随后重置 Locust 统计。跨越预热边界的在途请求按完成时所在阶段计数。
2. 计划测量45秒，结束最多等待60秒完成当前请求；报告以实际 measured window（包括排空尾部）计算完成请求RPS，同时保留计划时长和进程墙钟。若客户端超时或未排空，必须单独说明。
3. CSV保存每次完成请求的原始 response_ms。报告P50/P95采用 nearest-rank；Locust自身的直方图分位数也保留，但不混为精确原始分位数。失败样本包含在分位数中，429较快不能被解释为服务变快。
4. Nginx返回429和业务错误均保留，Locust错误退出码不改成成功；同样保留首页HTTP200但某栏失败的情况。
5. SQL计数含认证SELECT，不含驱动 pre-ping/连接设置；游标时间含网络、驱动与缓冲读取，不是纯MySQL执行时间。真正服务器执行时间另看 EXPLAIN ANALYZE。
6. 连接池 acquire 时间包括取池连接、等待与新建连接；不是纯排队时长。checkout→checkin为持有时长。30秒无SQL的503与其他证据结合判断池耗尽。
7. cProfile测服务函数，含工具开销；不能将其时长直接当原始API耗时，累计时间有调用嵌套，不能把各函数累计时间相加。
8. 45秒测试、5个租户、最多500菜谱、第一页列表及混合循环是范围限制。小样本的P95只能作为观测值；不外推生产吞吐量、网络尾部或更大数据规模。
