# Tour Pass 性能基准报告

- 运行时间：2026-05-15T15:05:23.844Z
- 样本数：20 次，预热：3 次
- 服务地址：http://127.0.0.1:8092

| 接口 | avg | p50 | p95 | min | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| GET /health | 0.6 ms | 0.6 ms | 0.9 ms | 0.4 ms | 1.0 ms |
| GET /route/shortest | 0.5 ms | 0.5 ms | 0.7 ms | 0.4 ms | 0.8 ms |
| GET /poi/search | 0.7 ms | 0.7 ms | 1.1 ms | 0.6 ms | 1.1 ms |
| POST /trip/plan | 418.3 ms | 414.2 ms | 436.7 ms | 407.3 ms | 454.8 ms |

## 说明

- 基准脚本会启动本地服务，强制 `LLM_DISABLED=1`，避免远程 LLM 网络波动污染结果。
- 当前数据集为演示样例规模，结果主要用于防止算法和 API 响应时间出现明显回退。
- 面试展示时可结合 Beam Search、BM25 检索和 API 冒烟测试说明工程质量门禁。
