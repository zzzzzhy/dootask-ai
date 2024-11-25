# AI Chat API Service

一个支持多种大语言模型的统一 API 服务，提供流式输出和上下文管理功能。

## 支持的模型

1. **OpenAI GPT**
   - 模型：gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-3.5-turbo, gpt-3.5-turbo-16k, gpt-3.5-turbo-0125, gpt-3.5-turbo-1106
   - 特点：强大的通用语言理解和生成能力

2. **Anthropic Claude**
   - 模型：claude-3-opus-20240229, claude-3-sonnet-20240229, claude-2.1, claude-2.0
   - 特点：注重安全性和可控性的对话模型

3. **Google Gemini**
   - 模型：gemini-pro, gemini-pro-vision
   - 特点：支持多模态输入的新一代 AI 模型

4. **智谱 AI**
   - 模型：glm-4, glm-4v, glm-3-turbo
   - 特点：专注中文处理的大语言模型

5. **通义千问**
   - 模型：qwen-turbo, qwen-plus, qwen-max, qwen-max-longcontext
   - 特点：阿里巴巴开发的多语言模型

6. **百度文心一言**
   - 模型：ernie-bot-4, ernie-bot-8k, ernie-bot-turbo, ernie-bot
   - 特点：擅长中文理解和生成的模型

7. **Meta LLaMA**
   - 模型：llama-2-7b, llama-2-13b, llama-2-70b
   - 特点：Meta开发的开源语言模型，适用于多种NLP任务

8. **Cohere**
   - 模型：command-r
   - 特点：适用于文本生成、分类和搜索等任务

9. **EleutherAI**
   - 模型：gpt-neo, gpt-j, gpt-neox
   - 特点：开源语言模型，提供与OpenAI GPT相似的功能

10. **Mistral**
    - 模型：mistral-7b, mistral-mixtral
    - 特点：高效语言模型，适用于多种生成和理解任务

## API 参数说明

### URL 参数
- `model_type`: 模型类型（必需）
- `model`: 具体的模型名称（必需）
- `input`: 输入内容（必需）
- `id`: 消息ID，默认为'0'（可选）
- `content_id`: 上下文ID，不提供则不保存上下文（可选）
- `ak`: API密钥（如果未在header中提供）
- `agent`: 代理设置（如果未在header中提供）

### Headers
- `Authorization`: API密钥（优先于URL参数ak）
- `Agent`: 代理设置（优先于URL参数agent）

### 返回格式
正常响应:
```
id: <message_id>
event: append
data: <content>
```

错误响应:
```
id: <message_id>
event: error
data: <error_message>
```

## 快速开始

### 安装依赖
```
pip install -r requirements.txt
```

### 运行服务
```
python main.py
```

默认运行在 `http://0.0.0.0:5001`

### API 使用示例
```
curl "http://localhost:5001/?model_type=openai&model=gpt-3.5-turbo&input=Hello&id=123" \
  -H "Authorization: your-api-key"
```

## 开发

### 运行测试
```
python -m unittest test_main.py
```

### 项目结构
```
.
├── main.py           # 主服务文件
├── test_main.py      # 测试文件
├── requirements.txt  # 依赖列表
└── README.md        # 项目文档
```

## 注意事项

1. 请确保在使用前设置正确的 API 密钥
2. 不同模型可能需要不同的 API 密钥
3. 建议在生产环境中使用 HTTPS
4. 注意保护 API 密钥和其他敏感信息

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！