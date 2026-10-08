# Eddie 个人 fork 说明

本仓库是 [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) 的个人 fork，只跑 **Python 单模块 server**（不部署 manager-api / manager-web / MySQL / Redis）。

## 分支模型

| 分支 | 用途 |
| --- | --- |
| `main` | 跟踪上游，保持干净，不往这里堆个人改动 |
| `eddie` | 长期定制分支，**唯一会部署到主机的分支** |
| `cursor/*` 等功能分支 | 从 `eddie` 拉出，PR **只合进 `eddie`** |

不要向 `main` 提功能 PR，也不要向上游 `xinnan-tech/xiaozhi-esp32-server` 开 PR。

功能改动尽量放在新文件里，对上游文件只做小范围、带 `Eddie-fork` 注释的修改，方便以后把上游合进 `eddie`。

## 同步上游

在 fork 上增加（只需一次）：

```bash
git remote add upstream https://github.com/xinnan-tech/xiaozhi-esp32-server.git
```

之后：

```bash
git fetch upstream
git checkout main
git merge --ff-only upstream/main
git push origin main

git checkout eddie
git merge main
# 如有冲突，优先保留 eddie 上带 Eddie-fork 注释的局部改动
git push origin eddie
```

`eddie` 有 GitHub Actions 部署。合并 `main` 进 `eddie` 并 push 后会构建新镜像并发布到主机，请确认本次合并是你想部署的内容。

## OTA 白名单（安全）

上游单模块 OTA（`POST /xiaozhi/ota/`）在 `server.auth.enabled=true` 时，会给**任意**来访设备签发可用的 WebSocket HMAC token。WebSocket 侧的 `allowed_devices` 只表示「白名单设备可以不带 token」，**不会拒绝**外人拿着 OTA 签发的 token 连上来。

### 新配置项

```yaml
server:
  auth:
    restrict_ota_to_allowed_devices: true
```

- **配置键：** `server.auth.restrict_ota_to_allowed_devices`
- **缺省 / `false`：** 与上游一致
- **`true`：** OTA POST 对不在 `server.auth.allowed_devices` 里的设备返回 **HTTP 403** `{"success":false,"message":"device not allowed"}`，并打 warning 日志；不返回 websocket / MQTT 凭证，也不走后续固件 URL 下发

请写在主机运行时配置 `data/.config.yaml`（不要提交真实设备 ID 或密钥）：

```yaml
server:
  auth:
    enabled: true
    allowed_devices:
      - "你的设备MAC"
    restrict_ota_to_allowed_devices: true
```

仓库里的 `main/xiaozhi-server/config.yaml` 只文档化该键，默认仍是 `false`。

设备 ID 按**精确字符串**匹配（大小写敏感），需与设备 OTA 请求头 `device-id` 以及现有 `allowed_devices` 条目一致。

### 其它签发路径

| 路径 | 是否受该开关约束 | 说明 |
| --- | --- | --- |
| OTA WebSocket 分支 `token` | 是 | 本开关的主要目标 |
| OTA MQTT 分支 `password` | 是 | 同一 POST，拒绝发生在签发之前。本 fork 的单模块部署未配 `mqtt_gateway` |
| Vision `AuthToken`（`core/providers/tools/device_mcp/mcp_handler.py`） | 间接 | 只在设备已经通过 WebSocket 连上之后才签发，外人拿不到 OTA token 就走不到这里 |
| `GET /xiaozhi/ota/` | 否 | 健康检查用，不含 token |
| `GET /xiaozhi/ota/download/{filename}` | 否 | 知道文件名仍可下固件；本开关不改变这一点 |
| Vision `client_id=web_test_client` | 否 | 上游测试后门，与 OTA 无关 |

### 上线后如何自测

在主机上（不要把真实 MAC 写进仓库）：

```bash
# 陌生人：应 403，body 里没有 websocket/token
curl -sS -D- -o /tmp/ota-stranger.json \
  -H 'device-id: 00:00:00:00:00:01' \
  -H 'client-id: stranger' \
  -X POST http://127.0.0.1:8003/xiaozhi/ota/ \
  --data '{}'
grep -E '403|device not allowed' /tmp/ota-stranger.json /dev/stdin || true

# 白名单设备：应 200，且带 websocket 配置
curl -sS -D- \
  -H 'device-id: 你的设备MAC' \
  -H 'client-id: your-client' \
  -X POST http://127.0.0.1:8003/xiaozhi/ota/ \
  --data '{}'
```

开关未打开时，陌生人 POST 仍会 200 并带 token（上游行为）。

## 豆包流式 ASR 新控制台 API Key

上游 `doubao_stream`（`ASR.DoubaoStreamASRV2`）只用旧控制台的 `X-Api-App-Key` / `X-Api-Access-Key`。新版语音控制台只发一张 API Key，握手头必须是 `X-Api-Key`（另加 `X-Api-Resource-Id`、`X-Api-Connect-Id`）。

- **配置键：** `ASR.DoubaoStreamASRV2.api_key`（可选）
- **非空且不是「你的…」占位符：** 走 `X-Api-Key`，请求体不再带 `app.appid` / `app.token`
- **缺省 / 空：** 与上游一致（`appid` + `access_token`）
- 连接日志会脱敏 `X-Api-Key` / `X-Api-Access-Key` / `token`，避免密钥进日志

真实 Key 只写主机 `data/.config.yaml`，不要提交到仓库：

```yaml
ASR:
  DoubaoStreamASRV2:
    type: doubao_stream
    api_key: 你的火山引擎新控制台API Key
    resource_id: volc.seedasr.sauc.duration
```

## CI/CD

工作流：`.github/workflows/eddie-server-deploy.yml`

- **触发：** push 到 `eddie`，或手动 `workflow_dispatch`。指向 `eddie` 的 PR 只跑测试，不构建、不部署。
- **仓库限制：** `jobs` 带 `github.repository == 'EddieIPeace/xiaozhi-esp32-server'`，其它 fork 不会发布。
- **构建：** GitHub-hosted runner 用仓库根目录 `Dockerfile-server` 打 `linux/amd64` 镜像（`FROM ghcr.io/xinnan-tech/xiaozhi-esp32-server:server-base`），推到：
  - `ghcr.io/eddieipeace/xiaozhi-esp32-server:eddie`
  - `ghcr.io/eddieipeace/xiaozhi-esp32-server:sha-<commit>`
- **部署：** SSH 到主机，备份 `/home/ubuntu/xiaozhi-server/docker-compose.yml`，只改第一条 `image:`，`docker compose pull && up -d`。
- **健康检查：** 容器 `xiaozhi-esp32-server` 在跑，且 `http://127.0.0.1:8003/xiaozhi/ota/` 返回 200。失败则恢复备份的 compose 并再次 `up -d`。
- **不会做的事：** 不改端口 / volume、不碰 `data/` 与 `data/.config.yaml`、不碰主机 Caddy（80/443）、不在小主机上编译镜像。

上游自带的 `docker-image.yml` / `build-base-image.yml` 已加上「仅 `xinnan-tech/xiaozhi-esp32-server`」判断，避免本 fork 误发 `server_latest`。`test.yml` 只在 `main` 上跑完整上游套件。

### 必须添加的仓库 Secrets

在 GitHub：`EddieIPeace/xiaozhi-esp32-server` → Settings → Secrets and variables → Actions → New repository secret。

| 名称 | 必填 | 含义 |
| --- | --- | --- |
| `DEPLOY_HOST` | 是 | 主机公网域名或 IP（不要写进仓库文件） |
| `DEPLOY_USER` | 是 | SSH 用户，例如 `ubuntu` |
| `DEPLOY_SSH_KEY` | 是 | 对应公钥已写入主机 `~/.ssh/authorized_keys` 的**私钥**全文（含 BEGIN/END） |
| `DEPLOY_PORT` | 否 | SSH 端口，默认 22 |

不要把主机密码、API Key、`data/.config.yaml` 提交到 git。

工作流权限：仓库 Settings → Actions → General → Workflow permissions 选 **Read and write**（或至少允许本 workflow 的 `packages: write`），否则无法推 GHCR。

### 主机一次性准备

1. 生成一枚**仅用于部署**的 SSH 密钥对，公钥写入 `DEPLOY_USER` 的 `authorized_keys`，私钥放进 `DEPLOY_SSH_KEY`。
2. 该用户能对 docker 免 sudo（在 `docker` 组里）。
3. 部署目录保持为 `/home/ubuntu/xiaozhi-server`（已有 `docker-compose.yml`、`data/`、`models/SenseVoiceSmall/model.pt`）。
4. 主机需能访问 `ghcr.io`（当前上游镜像已从那里拉取过）。
5. 第一次 workflow 成功推送后，GitHub Packages 里的 `xiaozhi-esp32-server` **默认是 private**。工作流会在部署时用短期 `GITHUB_TOKEN` 在主机上 `docker login`。若希望主机平时也能手动 `docker pull`：Package settings → Change visibility → Public。
6. 在 `data/.config.yaml` 打开 `restrict_ota_to_allowed_devices: true` 后重启一次容器（或等下一次部署）。

### 回滚怎么工作

`scripts/eddie-deploy-remote.sh` 在改 compose 之前复制 `docker-compose.yml.bak`。若 pull / up / 健康检查失败，会把 compose 拷回去再 `docker compose up -d`，用主机上仍保留的旧镜像启动。脚本不会 `docker image prune`。

若新版本已经健康上线、需要再退回：把 compose 里的 `image:` 改回上一枚 `sha-...` 或原来的上游标签，然后：

```bash
cd /home/ubuntu/xiaozhi-server
docker compose up -d
```

## 本地跑 fork 测试

```bash
cd main/xiaozhi-server
pip install pytest
pytest -c /dev/null --noconftest -o cache_dir=/tmp/pytest-eddie \
  tests/test_ota_allowlist.py tests/test_doubao_stream_auth.py -q
```
