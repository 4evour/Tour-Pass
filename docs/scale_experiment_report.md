# Tour Pass Scale Experiment

真实 POI 数据用于观察项目在真实地点清单上的规划热路径表现；若通勤边包含 geo_estimated，仍不代表真实路网或生产压测。

## 运行口径

- 命令：`node scripts/scale_experiment.js --dataset real --pois output\amap-changsha\pois.json --edges output\amap-changsha\edges.json --sizes 100,200,500 --iterations 5`
- 数据集：`real`
- 缓存模式：`auto`
- LLM：`LLM_DISABLED=1`，不包含外部 LLM 网络延迟。
- 数据：`output\amap-changsha\pois.json` 与 `output\amap-changsha\edges.json` 通过 `TOURPASS_POIS_PATH` / `TOURPASS_EDGES_PATH` 注入服务。
- 目标：验证最短路缓存、候选池裁剪和评分复用后的本地趋势；失败会记录为失败数，不包装成成功性能。
- 环境：platform=win32-x64, node=v24.15.0, cpu=AMD Ryzen 9 7945HX with Radeon Graphics

| POI | Edges | amap edge ratio | cache mode | startup | distance cache entries | iterations | failures | avg | p95 | p99 | max | note |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | 106 | 85.8% | all_pairs | 0 ms | 10000 | 5 | 0 | 4.9 ms | 6.5 ms | 6.5 ms | 6.5 ms | ok |
| 200 | 391 | 87.0% | all_pairs | 18 ms | 40000 | 5 | 0 | 5.2 ms | 6.3 ms | 6.3 ms | 6.3 ms | ok |
| 500 | 1937 | 88.1% | all_pairs | 339 ms | 250000 | 5 | 0 | 128.0 ms | 128.9 ms | 128.9 ms | 128.9 ms | ok |

## 解释边界

- 默认长沙样例仍是演示数据；synthetic 结果只说明本地算法趋势和瓶颈。
- 500 POI 若出现失败或秒级耗时，应按瓶颈解释，不能写成生产实时能力。真实数据若边来源包含 geo_estimated，也不能等同真实路网。
- SQLite、HTTP 线程池和背压不参与证明大规模路线质量，只用于本地服务可复盘和稳定性演示。
