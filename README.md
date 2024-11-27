# DooTask AI

DooTask AI 是一个灵活的 AI 对话服务，支持多种 AI 模型，提供统一的 API 接口。

## 功能特点

### 支持的 AI 模型

1. **OpenAI GPT** (model_type: openai)
   - model_name: gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-3.5-turbo, gpt-3.5-turbo-16k, gpt-3.5-turbo-0125, gpt-3.5-turbo-1106
   - 特点：强大的通用语言理解和生成能力

2. **Anthropic Claude** (model_type: claude)
   - model_name: claude-3-opus-20240229, claude-3-sonnet-20240229, claude-2.1, claude-2.0
   - 特点：注重安全性和可控性的对话模型

3. **Google Gemini** (model_type: gemini)
   - model_name: gemini-pro, gemini-pro-vision
   - 特点：支持多模态输入的新一代 AI 模型

4. **智谱 AI** (model_type: zhipu)
   - model_name: glm-4, glm-4v, glm-3-turbo
   - 特点：专注中文处理的大语言模型

5. **通义千问** (model_type: qwen)
   - model_name: qwen-turbo, qwen-plus, qwen-max, qwen-max-longcontext
   - 特点：阿里巴巴开发的多语言模型

6. **百度文心一言** (model_type: wenxin)
   - model_name: ernie-bot-4, ernie-bot-8k, ernie-bot-turbo, ernie-bot
   - 特点：擅长中文理解和生成的模型

7. **Meta LLaMA** (model_type: llama)
   - model_name: llama-2-7b, llama-2-13b, llama-2-70b
   - 特点：Meta开发的开源语言模型，适用于多种NLP任务

8. **Cohere** (model_type: cohere)
   - model_name: command-r
   - 特点：适用于文本生成、分类和搜索等任务

9. **EleutherAI** (model_type: eleutherai)
   - model_name: gpt-neo, gpt-j, gpt-neox
   - 特点：开源语言模型，提供与OpenAI GPT相似的功能

10. **Mistral** (model_type: mistral)
    - model_name: mistral-7b, mistral-mixtral
    - 特点：高效语言模型，适用于多种生成和理解任务

### 核心功能

- 统一的 API 接口
  - RESTful API 设计
  - 流式响应支持（Server-Sent Events）
  - 完整的错误处理

- 自动化管理
  - 自动超时检测（1分钟）
  - 自动数据清理（10分钟）
  - 内存优化管理

## 快速开始

### 环境要求

- Python 3.8+
- Flask
- LangChain
- Requests

### 安装

1. 克隆仓库：
```bash
git clone [repository-url]
cd dootask-ai
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 启动服务：
```bash
python main.py
```

默认服务端口为 5001，可通过环境变量 PORT 修改。

## API 使用

### 发起对话

```http
GET /chat?text=hello&token=xxx&dialog_id=123&msg_uid=456&bot_uid=789&version=1.0&extras={"model_type":"openai","model_name":"gpt-3.5-turbo","server_url":"https://api.example.com","api_key":"your-api-key"}
```

参数说明：
- `text`: 对话内容
- `token`: 认证令牌
- `dialog_id`: 对话ID
- `msg_uid`: 消息用户ID
- `bot_uid`: 机器人用户ID
- `version`: API版本
- `extras`: 额外参数（JSON字符串）
  - `model_type`: 模型类型
  - `model_name`: 模型名称
  - `server_url`: 服务器地址
  - `api_key`: API密钥
  - `agency`: 代理服务器（可选）

### 获取响应流

```http
GET /stream/{msg_id}/{stream_key}
```

响应格式（SSE）：
```
id: {msg_id}
event: append/replace/error
data: {content}
```

事件类型：
- `append`: 追加新内容
- `replace`: 替换全部内容
- `error`: 错误信息

## 开发说明

### 目录结构

```
dootask-ai/
├── main.py          # 主程序入口
├── request.py       # 请求处理类
├── utils.py         # 工具函数
├── static/          # 静态文件
│   └── swagger.yaml # API文档
└── requirements.txt # 项目依赖
```

### 核心组件

1. Request 类（request.py）
   - 处理与服务器的通信
   - 支持不同的请求动作（sendtext/stream）
   - 自动处理超时和错误

2. 超时管理
   - 后台线程自动检查超时请求
   - 自动清理过期数据
   - 资源优化管理

3. 流式响应
   - 支持 SSE（Server-Sent Events）
   - 实时响应更新
   - 完整的错误处理

## 注意事项

1. API 密钥安全
   - 不要在代码中硬编码 API 密钥
   - 使用环境变量或配置文件管理敏感信息

2. 代理设置
   - 可通过 extras.agency 参数设置代理
   - 支持 HTTP 和 HTTPS 代理

3. 错误处理
   - 所有请求都有适当的错误处理
   - 超时自动处理
   - 详细的错误信息返回

## API 文档

API 文档采用 OpenAPI (Swagger) 规范，可以通过以下方式查看：

1. 直接查看 YAML 文件：
```
http://localhost:5001/swagger.yaml
```

2. 使用 Swagger UI（推荐）：
   - 访问 [Swagger Editor](https://editor.swagger.io/)
   - 将 http://localhost:5001/swagger.yaml 的内容复制到编辑器中
   - 或者直接导入 URL：File -> Import URL -> 输入 http://localhost:5001/swagger.yaml

这样你可以：
- 查看所有 API 端点的详细说明
- 了解请求和响应的数据结构
- 直接在线测试 API 接口

## 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。