# Tour Pass 性能回归基准报告

- 运行时间：2026-05-22T11:17:27.788Z
- 单轮持续时间：1s，预热请求：0，并发梯度：1, 2
- 服务地址：http://127.0.0.1:8130

> 这份报告用于本地性能回归检查，不代表生产压测。当前默认数据是长沙样例图，不包含真实地图 API、数据库 IO、外部 LLM 网络延迟或真实用户流量。

| 场景 | 并发 | 成功数 | 吞吐量 | 错误率 | avg | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET /health | 1 | 1139 | 1138.86/s | 0.00% | 0.9 ms | 0.8 ms | 1.2 ms | 1.8 ms | 3.8 ms |
| GET /route/shortest hot-cache | 1 | 1395 | 1394.07/s | 0.00% | 0.7 ms | 0.7 ms | 0.9 ms | 1.2 ms | 6.3 ms |
| GET /route/shortest cold-cache | 1 | 1369 | 1368.99/s | 0.00% | 0.7 ms | 0.7 ms | 0.9 ms | 1.2 ms | 6.3 ms |
| GET /poi/search hot-cache | 1 | 1006 | 1005.73/s | 0.00% | 1.0 ms | 0.9 ms | 1.4 ms | 1.7 ms | 6.7 ms |
| GET /poi/search cold-cache | 1 | 1071 | 1070.15/s | 0.00% | 0.9 ms | 0.9 ms | 1.3 ms | 1.7 ms | 6.6 ms |
| POST /trip/plan hot-cache | 1 | 198 | 197.18/s | 0.00% | 5.1 ms | 4.7 ms | 5.8 ms | 17.9 ms | 37.8 ms |
| POST /trip/plan cold-cache | 1 | 201 | 200.35/s | 0.00% | 5.0 ms | 4.7 ms | 5.5 ms | 12.1 ms | 33.6 ms |
| POST /trip/plan bypass-cache | 1 | 29 | 28.82/s | 0.00% | 34.7 ms | 33.0 ms | 40.7 ms | 62.5 ms | 62.5 ms |
| POST /trip/jobs end-to-end | 1 | 2 | 15.84/s | 0.00% | 63.1 ms | 61.0 ms | 65.2 ms | 65.2 ms | 65.2 ms |
| GET /health | 2 | 3227 | 3226.50/s | 0.00% | 0.6 ms | 0.6 ms | 0.8 ms | 1.4 ms | 5.5 ms |
| GET /route/shortest hot-cache | 2 | 5295 | 5293.83/s | 0.00% | 0.4 ms | 0.3 ms | 0.6 ms | 1.1 ms | 18.7 ms |
| GET /route/shortest cold-cache | 2 | 5462 | 5461.09/s | 0.00% | 0.4 ms | 0.3 ms | 0.5 ms | 1.0 ms | 8.2 ms |
| GET /poi/search hot-cache | 2 | 4065 | 4063.87/s | 0.00% | 0.5 ms | 0.4 ms | 0.7 ms | 1.0 ms | 7.3 ms |
| GET /poi/search cold-cache | 2 | 3977 | 3975.68/s | 0.00% | 0.5 ms | 0.5 ms | 0.7 ms | 1.0 ms | 6.4 ms |
| POST /trip/plan hot-cache | 2 | 522 | 521.16/s | 0.00% | 3.8 ms | 3.6 ms | 5.0 ms | 6.7 ms | 11.6 ms |
| POST /trip/plan cold-cache | 2 | 494 | 492.83/s | 0.00% | 4.1 ms | 3.7 ms | 5.2 ms | 6.6 ms | 34.0 ms |
| POST /trip/plan bypass-cache | 2 | 60 | 59.18/s | 0.00% | 33.6 ms | 33.1 ms | 37.3 ms | 38.6 ms | 38.6 ms |
| POST /trip/jobs end-to-end | 2 | 2 | 15.44/s | 0.00% | 98.2 ms | 67.0 ms | 129.3 ms | 129.3 ms | 129.3 ms |

## 服务端指标快照

```json
{
  "cache": {
    "entries": 64,
    "evictions": 34,
    "hit_rate": 0.9959831371301304,
    "hits": 25043,
    "misses": 101
  },
  "db": {
    "enabled": true,
    "path": "storage/tourpass.sqlite",
    "write_count": 1518,
    "write_failures": 0
  },
  "in_flight_requests": 1,
  "jobs": {
    "CANCELLED": 0,
    "FAILED": 0,
    "QUEUED": 0,
    "RUNNING": 0,
    "SUCCEEDED": 4,
    "avg_execution_ms": 31,
    "avg_queue_wait_ms": 7.5,
    "completed_jobs": 4,
    "failed_jobs": 0,
    "queue_depth": 0,
    "total": 4,
    "worker_count": 1
  },
  "max_in_flight": 32,
  "rejected_requests": 0,
  "routes": {
    "GET /health": {
      "avg_ms": 0,
      "count": 4367,
      "p95_ms": 0
    },
    "GET /poi/search": {
      "avg_ms": 0.00009882399446585631,
      "count": 10119,
      "p95_ms": 0
    },
    "GET /route/shortest": {
      "avg_ms": 0,
      "count": 13521,
      "p95_ms": 0
    },
    "GET /trip/jobs/{id}": {
      "avg_ms": 3,
      "count": 9,
      "p95_ms": 8
    },
    "POST /benchmark/runs": {
      "avg_ms": 0,
      "count": 1,
      "p95_ms": 0
    },
    "POST /trip/jobs": {
      "avg_ms": 0,
      "count": 4,
      "p95_ms": 0
    },
    "POST /trip/plan": {
      "avg_ms": 4.320478723404255,
      "count": 1504,
      "p95_ms": 33
    }
  },
  "runtime": {
    "job_workers": 1,
    "max_body_bytes": 65536,
    "max_in_flight": 32,
    "max_queue": 64,
    "workers": 8
  },
  "status_codes": {
    "200": 29520,
    "201": 1,
    "202": 4
  },
  "total_requests": 29526
}
```

## 口径说明

- `LLM_DISABLED=1`：基准只测结构化算法规划和本地模板兜底，不测外部 LLM 网络延迟。
- `cold-cache` 场景使用一次性固定 benchmark nonce 观察首轮未命中后的表现；`hot-cache` 场景复用固定请求；`bypass-cache` 场景为每次请求注入 benchmark nonce，三者必须分开解读。
- `/trip/jobs` 端到端耗时包含提交、排队、执行和轮询等待，适合观察削峰链路，不等同于分布式任务调度。
- 若要做生产压测，应使用 wrk/JMeter/k6、至少 1 分钟持续时长、真实请求分布、P95/P99、吞吐量和错误率。
