# 个人知识库问答 + 联网查证 Agent

这是一个本地优先的知识库问答系统，支持上传文档、自动切片、向量检索、分类管理和联网查证。项目分为后端 Python FastAPI 服务和前端 Vue3 管理界面，适合做个人知识库、资料问答和轻量 RAG 原型。

## 核心能力

- 上传 PDF、Word、Excel、CSV、Markdown、纯文本等文件。
- 自动解析、分块、向量化，并保存到本地索引。
- 支持文档列表、分类管理、重命名、删除。
- 问答时优先检索本地知识库，置信度不足或问题带时效性时可自动走联网搜索补充证据。
- 默认使用本地抽取式回答，不依赖外部模型也能完成开发和测试。
- 前端提供登录、上传、提问、结果、引用来源和错误状态展示。

## 技术栈

- 后端：Python + FastAPI
- 前端：Vue3 + Vite + TypeScript + Element Plus
- 存储：本地 JSON 索引文件 + 本地上传目录

## 项目结构

```text
knowledge_agent/   后端核心逻辑
frontend/          Vue3 前端
tests/             单元测试
examples/          示例文档与评测数据
data/              运行时数据目录
```

## 本地运行

### 1. 后端

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn knowledge_agent.api:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器默认运行在 `http://127.0.0.1:5173`，并通过 Vite 代理把 `/api` 转发到后端 `http://127.0.0.1:8000`。

## 使用流程

1. 打开前端页面并登录或注册本地账号。
2. 在“知识库管理”里上传文档并选择分类。
3. 在“问答”页面输入问题。
4. 查看答案、引用来源、置信度和是否走了联网查证。

## 主要接口

### 认证

- `POST /auth/register`：注册本地账号
- `POST /auth/login`：登录并获取 token
- `GET /auth/me`：获取当前用户信息
- `POST /auth/logout`：退出登录

### 知识库

- `POST /upload`：上传文件并入库
- `GET /documents`：查看已入库文档
- `DELETE /documents/{document_id}`：删除文档
- `PUT /documents/{document_id}`：修改文档名称和分类
- `GET /categories`：获取分类列表
- `POST /categories`：新增分类
- `PUT /categories/{category_name}`：重命名分类
- `DELETE /categories/{category_name}`：删除分类

### 问答

- `POST /query`：同步问答
- `POST /query/stream`：SSE 流式问答

### 健康检查

- `GET /health`：健康检查和当前 chunk 数量

## 环境变量

`.env.example` 已提供完整样例，常用项如下：

```bash
KNOWLEDGE_AGENT_DATA_DIR=data
KNOWLEDGE_AGENT_UPLOAD_DIR=data/uploads
KNOWLEDGE_AGENT_INDEX_PATH=data/index/store.json
KNOWLEDGE_AGENT_USERS_PATH=data/auth/users.json
CHUNK_SIZE=900
CHUNK_OVERLAP=120
TOP_K=5
CONFIDENCE_THRESHOLD=0.72
LLM_PROVIDER=local
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=
LLM_TEMPERATURE=0.2
LLM_TIMEOUT_SECONDS=20
SEARCH_ENDPOINT=
SEARCH_API_KEY=
SEARCH_TIMEOUT_SECONDS=8
```

## 联网搜索配置

默认情况下，联网搜索是空实现。若要接入自己的搜索服务，可以配置：

```bash
export SEARCH_ENDPOINT="https://your-search-service.example/search"
export SEARCH_API_KEY="optional-token"
```

接口会以 `GET ?q=...` 方式调用，返回格式支持两种：

```json
{"results":[{"title":"...","url":"https://...","snippet":"..."}]}
```

或：

```json
[{"title":"...","url":"https://...","snippet":"..."}]
```

## LLM 配置

默认使用本地抽取式回答生成器。如果你有自己的 LLM 网关，可以配置：

```bash
export LLM_PROVIDER="http"
export LLM_ENDPOINT="https://your-llm-gateway.example/answer"
export LLM_API_KEY="optional-token"
```

请求格式为 `{"query":"...","contexts":[...]}`，返回格式为 `{"answer":"..."}`。

## 测试

后端单测：

```bash
.venv/bin/python -m unittest
```

前端构建：

```bash
cd frontend
npm run build
```

## 示例与评测

```bash
python3 -m knowledge_agent.cli upload examples/rag_intro.txt
python3 scripts/evaluate.py examples/eval_cases.csv
```

## 说明

- 本项目以本地知识库为中心，联网能力作为补充，不是纯搜索问答。
- 运行数据默认保存在 `data/` 下，属于本地状态，不建议提交到仓库。
- 后续如果要接更强的 embedding 或 LLM，只需要替换对应 provider，主流程可以保持不变。
