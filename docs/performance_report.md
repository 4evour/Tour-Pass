# Tour Pass 性能基准报告

- 运行时间：2026-05-19T10:52:20.414Z
- 样本数：4 次，预热：1 次，并发：2
- 服务地址：http://127.0.0.1:8095

| 场景 | avg | p50 | p95 | min | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| GET /health | 1.0 ms | 0.9 ms | 1.2 ms | 0.8 ms | 1.2 ms |
| GET /route/shortest cold | 1.1 ms | 1.0 ms | 1.4 ms | 0.9 ms | 1.4 ms |
| GET /route/shortest hot | 0.6 ms | 0.6 ms | 0.7 ms | 0.6 ms | 0.7 ms |
| GET /poi/search hot | 0.8 ms | 0.7 ms | 0.9 ms | 0.6 ms | 0.9 ms |
| POST /trip/plan sequential | 3.9 ms | 3.6 ms | 4.8 ms | 3.6 ms | 4.8 ms |
| POST /trip/plan concurrent x2 | 4.0 ms | 3.8 ms | 4.8 ms | 3.6 ms | 4.8 ms |
| POST /trip/jobs end-to-end | 453.9 ms | 434.8 ms | 502.0 ms | 433.9 ms | 502.0 ms |

## 服务端指标快照

```json
{
  "cache": {
    "entries": 4,
    "evictions": 0,
    "hit_rate": 0.8333333333333334,
    "hits": 20,
    "misses": 4
  },
  "in_flight_requests": 1,
  "jobs": {
    "CANCELLED": 0,
    "FAILED": 0,
    "QUEUED": 0,
    "RUNNING": 0,
    "SUCCEEDED": 4,
    "queue_depth": 0,
    "total": 4
  },
  "routes": {
    "GET /health": {
      "avg_ms": 0,
      "count": 6,
      "p95_ms": 0
    },
    "GET /poi/search": {
      "avg_ms": 0,
      "count": 5,
      "p95_ms": 0
    },
    "GET /route/shortest": {
      "avg_ms": 0,
      "count": 10,
      "p95_ms": 0
    },
    "GET /trip/jobs/{id}": {
      "avg_ms": 0.48484848484848486,
      "count": 33,
      "p95_ms": 4
    },
    "POST /trip/jobs": {
      "avg_ms": 0,
      "count": 4,
      "p95_ms": 0
    },
    "POST /trip/plan": {
      "avg_ms": 52.55555555555556,
      "count": 9,
      "p95_ms": 455
    }
  },
  "runtime": {
    "max_body_bytes": 65536,
    "max_queue": 64,
    "workers": 8
  },
  "status_codes": {
    "200": 63,
    "202": 4
  },
  "total_requests": 68
}
```

## 说明

- 基准脚本会启动本地服务，强制 `LLM_DISABLED=1`，避免远程 LLM 网络波动污染结果。
- 冷缓存场景使用首次请求，热缓存场景复用相同查询并检查服务端缓存命中。
- 并发场景用于验证线程池下的吞吐和 p95 延迟，异步任务场景用于验证规划任务削峰链路。
