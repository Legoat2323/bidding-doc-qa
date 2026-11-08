# 部署说明

三种部署方式，按场景选。

## 方式一：本机直接跑（开发用）

```powershell
cd courses\docqa
$env:PYTHONPATH = "..\libs"
D:\Anaconda3\envs\agent-rag\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

或者用脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_api.ps1
```

打开 http://127.0.0.1:8000

---

## 方式二：Docker（推荐，一条命令）

要求：装了 Docker Desktop。

```bash
# 1. 准备环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

# 2. 把知识库文档放进 chroma/knowledge/
mkdir -p chroma/knowledge
# 放入你的 pdf / docx

# 3. 起服务
docker compose up -d --build

# 4. 看日志
docker compose logs -f

# 5. 停止
docker compose down
```

访问 http://127.0.0.1:8000

**为什么用 compose 而不是裸 docker run**：
- 知识库目录挂载到宿主机（`./chroma`），容器重建不丢索引
- `.env` 用 `env_file` 注入，不写进镜像
- `restart: unless-stopped` 挂了自动重启

---

## 方式三：部署到云服务器（对外可访问）

### 3.1 买服务器

最省事的两个选择：

| 平台 | 配置 | 大概价格 |
|---|---|---|
| 腾讯云 轻量应用服务器 | 2 核 2G，学生机 | 约 10 元/月（需学生认证） |
| 阿里云 轻量应用服务器 | 2 核 2G | 约 24 元/月起 |

**2 核 2G 够用**，因为这个服务本身很轻——重活在百炼的 API 上，本地只有检索。

### 3.2 装环境

```bash
# 登录服务器后
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# 装 compose 插件
apt install -y docker-compose-plugin
```

### 3.3 上传代码

```bash
# 在你本机执行
scp -r courses/docqa root@你的服务器IP:/opt/

# 或者服务器上直接 clone
git clone https://gitee.com/legoat/bidding-doc-qa.git /opt/docqa
```

### 3.4 配密钥并启动

```bash
cd /opt/docqa
cp .env.example .env
vim .env          # 填 DASHSCOPE_API_KEY
mkdir -p chroma/knowledge logs
# 用 scp 把招标文件传上去：scp 招标文件正文22.pdf root@IP:/opt/docqa/chroma/knowledge/

docker compose up -d --build
```

### 3.5 开放端口

云服务器控制台的**安全组**里放行 8000 端口（这一步最容易忘，忘了就是访问不了）。

然后访问 `http://你的公网IP:8000`。

### 3.6 加域名和 HTTPS（可选）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;      # 以后加流式输出时必需
        proxy_read_timeout 300s;  # 模型生成慢，别 60 秒就断
    }
}
```

证书用 certbot 一条命令搞定：

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

---

## 上线前一定要改的三件事

| 项 | 为什么 |
|---|---|
| `.env` 里设置 `API_KEY` | 否则任何人都能调你的接口，烧你的 token |
| `server_port` 不要用默认 | 或者至少加个反代 + 限流 |
| 限制上传大小 | 现在 `/upload` 没有大小限制，被人传个 1G 文件会打满磁盘 |

## 常见问题

**启动很慢（30 秒以上）**

正常。启动时要给知识库建索引，896 个切片要调用嵌入模型。

**`/health` 返回 `{"status": "loading"}`**

还在初始化。等一会儿再请求。

**部署后访问不了**

按顺序检查：容器是否在跑（`docker compose ps`）→ 端口是否监听（`ss -tlnp | grep 8000`）
→ 安全组是否放行 → 服务器防火墙（`ufw status`）。

**内存吃紧**

2G 机器跑 896 个切片的 Chroma + BM25 索引大约占 1.2G。如果吃紧，
可以在 `knowledge.py` 里关掉 BM25（只用向量召回），或者把知识库拆小。
