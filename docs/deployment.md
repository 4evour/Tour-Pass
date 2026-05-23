# Tour Pass 部署指南

本文档说明 Tour Pass 的 Docker 化演示部署方式。当前项目定位是 C++ 算法服务作品集和本地/容器演示，不承诺已经上线的生产服务。

## 本地 Docker 运行

构建镜像：

```powershell
docker build -t tour-pass:local .
```

启动容器：

```powershell
docker run --rm -p 8080:8080 `
  -e LLM_DISABLED=1 `
  -e TOURPASS_DB_PATH=/app/storage/tourpass.sqlite `
  tour-pass:local
```

健康检查：

```powershell
curl.exe http://127.0.0.1:8080/health
node scripts/container_smoke.js http://127.0.0.1:8080
```

HTTP 压测示例：

```powershell
$env:LLM_DISABLED="1"
$env:TOURPASS_DB_DISABLED="1"
$env:TOURPASS_WORKERS="32"
$env:TOURPASS_MAX_QUEUE="4096"
$env:TOURPASS_MAX_IN_FLIGHT="4096"
node scripts/load_test.js --url http://127.0.0.1:8080/health --concurrency 100 --duration 30 --report docs/load_test_report.md
powershell -ExecutionPolicy Bypass -File scripts/run_hey.ps1 -Url http://127.0.0.1:8080/health -Concurrency 100 -Duration 30s
```

`scripts/load_test.js` 是无额外依赖的本地回归脚本；`scripts/run_hey.ps1` 仅在本机已安装 `hey` 时运行，否则会提示 `go install github.com/rakyll/hey@latest`。

容器内默认设置：

- `HOST=0.0.0.0`，允许宿主机通过端口映射访问。
- `PORT=8080`。
- `LLM_DISABLED=1`，避免演示部署依赖外部 LLM 密钥。
- `TOURPASS_DB_PATH=/app/storage/tourpass.sqlite`。

## GHCR 镜像

GitHub Actions 在 PR 中构建 Docker 镜像并运行容器冒烟测试；`main` 分支 push 时可推送：

```text
ghcr.io/<owner>/tour-pass:latest
```

拉取并运行：

```powershell
docker pull ghcr.io/<owner>/tour-pass:latest
docker run --rm -p 8080:8080 -e LLM_DISABLED=1 ghcr.io/<owner>/tour-pass:latest
```

## Render / Fly / Railway 部署口径

推荐使用 Dockerfile 部署：

- Build command：由平台自动执行 Docker build。
- Start command：使用镜像默认 `CMD ["/app/tourpass"]`。
- Health check path：`/health`。
- Port：`8080`，或由平台注入 `PORT`。
- Environment：
  - `HOST=0.0.0.0`
  - `LLM_DISABLED=1`
  - `TOURPASS_DB_PATH=/app/storage/tourpass.sqlite`
  - 可选：`TOURPASS_WORKERS`、`TOURPASS_MAX_QUEUE`、`TOURPASS_MAX_IN_FLIGHT`
  - 可选：`TOURPASS_DISTANCE_CACHE_MODE=auto`

如果平台提供持久卷，将 `/app/storage` 挂载为持久目录；否则 SQLite 记录会随容器重启丢失。规划热路径不依赖 SQLite，SQLite 只用于规划历史、异步任务、benchmark 和数据版本复盘。

仓库提供 `render.yaml` 作为 Docker Web Service 草案。除非已经实际创建服务并获得公网 URL，文档和简历中不得声称项目已上线。

## LLM 与密钥

面试演示和公开 Demo 推荐设置：

```text
LLM_DISABLED=1
```

如果要启用远程 LLM，需要配置 OpenAI/DeepSeek 兼容环境变量或挂载 `config/llm.local.json`。不要把真实密钥写入镜像或仓库。

## 边界说明

- Docker 镜像证明服务可构建、可启动、可冒烟，不表示 `cpp-httplib` 是生产级网关。
- 当前数据是长沙样例数据，不代表真实地图、真实拥堵、实时闭馆或真实用户流量。
- SQLite 是本地持久化辅助，不是规划热路径数据库。
- 压测报告必须记录 `LLM_DISABLED`、worker、队列、in-flight、DB 和缓存口径；它只能说明本地/容器环境表现，不是生产 SLA。
- 线上 Demo 如需公开 URL，应单独配置平台账号、域名、日志、限流和持久卷。
