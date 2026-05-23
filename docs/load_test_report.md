# Tour Pass Load Test Report

本报告使用本地 HTTP 压测脚本生成，用于工程回归和面试展示；不代表生产 SLA。

## 运行口径

- URL：`http://127.0.0.1:8103/health`
- 方法：`GET`
- 并发：`100`
- 持续时间：`30s`
- 运行环境变量：`LLM_DISABLED=1 TOURPASS_DB_DISABLED=1 TOURPASS_WORKERS=32 TOURPASS_MAX_QUEUE=4096 TOURPASS_MAX_IN_FLIGHT=4096`
- 客户端：`node v24.15.0 win32/x64 http/https keep-alive`
- 推荐环境：`LLM_DISABLED=1`，默认长沙样例数据；如要测试 HTTP 承载上限，应显式记录 worker、队列和 in-flight 参数。
- 缓存口径：按被测 URL 决定；`/health` 不代表规划热路径，`/trip/plan` 应说明是否复用相同请求。

## 结果

| requests | errors | error rate | QPS | avg | p50 | p95 | p99 | max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 155035 | 35 | 0.02% | 3876.12 | 22.54 ms | 4.74 ms | 19.03 ms | 1116.23 ms | 10015.92 ms |

## 状态码

- `0`: 35
- `200`: 155000

## 边界说明

- 这是本地或容器环境压测，不包含真实用户网络、真实地图 API 或外部 LLM 延迟。
- 如果状态码 `0` 或错误率偏高，优先按客户端连接失败/短连接压力/本机资源限制处理，并在 Docker/Linux 环境复测后再对外展示。
- 若测试 `/trip/plan`，需要区分热缓存、冷缓存和绕过缓存。
- `cpp-httplib` 在本项目中用于演示级 HTTP 承载，不作为生产级网关能力包装。
