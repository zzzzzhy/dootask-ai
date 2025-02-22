from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_xai import ChatXAI
from langchain_community.chat_models import (
    ChatZhipuAI,
    ChatTongyi,
    QianfanChatEndpoint,
    ChatCohere
)
from .deepseek import DeepseekChatOpenAI
from .request import Request
from .redis import RedisManager
import os
import time
import json
import re

# 预编译正则表达式
_THINK_START_PATTERN = re.compile(r'<think>\s*')
_THINK_END_PATTERN = re.compile(r'\s*</think>')
_REASONING_PATTERN = re.compile(r'::: reasoning\n.*?:::', re.DOTALL)

def get_model_instance(model_type, model_name, api_key, **kwargs):
    """根据模型类型返回对应的模型实例"""

    base_url = kwargs.get("base_url", None)
    agency = kwargs.get("agency", None)
    temperature = kwargs.get("temperature", 0.7)
    streaming = kwargs.get("streaming", True)

    if model_type == "xai":
        model_type = "grok"

    model_configs = {
        "openai": (ChatOpenAI, {
            "openai_api_key": api_key,
        }),
        "claude": (ChatAnthropic, {
            "anthropic_api_key": api_key,
        }),
        "gemini": (ChatGoogleGenerativeAI, {
            "google_api_key": api_key,
        }),
        "deepseek": (DeepseekChatOpenAI, None),
        "zhipu": (ChatZhipuAI, None),
        "qwen": (ChatTongyi, None),
        "wenxin": (QianfanChatEndpoint, None),
        "cohere": (ChatCohere, None),
        "ollama": (ChatOllama, None),
        "grok": (ChatXAI, None),
    }

    if agency:
        os.environ["https_proxy"] = agency
        os.environ["http_proxy"] = agency

    try:
        model_class, config = model_configs.get(model_type, (None, None))
        if model_class is None:
            raise ValueError(f"Unsupported model type: {model_type}")

        if config is None:
            config = {
                "api_key": api_key,
            }
            if model_type == "wenxin":
                api_key, secret_key = (api_key.split(':') + [None])[:2]
                config.update({"api_key": api_key, "secret_key": secret_key})

        if base_url:
            config.update({"base_url": base_url})

        common_params = {
            "model": model_name,
            "temperature": temperature,
            "streaming": streaming
        }
        config.update(common_params)
        return model_class(**config)
    except Exception as e:
        raise RuntimeError(f"Failed to create model instance: {str(e)}")
    finally:
        if agency:
            os.environ.pop("https_proxy", None)
            os.environ.pop("http_proxy", None)

def check_timeouts():
    redis_manager = RedisManager()
    while True:
        try:
            # 使用 RedisManager 扫描所有处理中的请求
            current_time = int(time.time())
            for key_id, data in redis_manager.scan_inputs():
                if data and data.get("status") == "prepare":
                    if current_time - data.get("created_at", 0) > 60:
                        # 超时处理
                        data["status"] = "finished"
                        data["response"] = "Request timeout. Please try again."
                        redis_manager.set_input(key_id, data)
                        request_client = Request(
                            server_url=data["server_url"],
                            version=data["version"],
                            token=data["token"],
                            dialog_id=data["dialog_id"]
                        )
                        request_client.call({
                            "update_id": key_id,
                            "update_mark": "no",
                            "text": "Request timeout. Please try again.",
                            "text_type": "md",
                            "silence": "yes"
                        })
        except Exception as e:
            print(f"Error in timeout checker: {str(e)}")
        time.sleep(1)

def get_swagger_ui():
    """Return the Swagger UI HTML content."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Swagger UI</title>
        <link rel="stylesheet" type="text/css" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.1.0/swagger-ui.min.css" />
        <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.1.0/swagger-ui-bundle.js"></script>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script>
            window.onload = function() {
                SwaggerUIBundle({
                    url: "/swagger.yaml",
                    dom_id: '#swagger-ui',
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIBundle.SwaggerUIStandalonePreset
                    ],
                    layout: "BaseLayout"
                });
            }
        </script>
    </body>
    </html>
    """

def filter_end_flag(text: str, flag: str) -> str:
    """
    方案1：使用列表遍历的方式（当前实现）
    时间复杂度：O(n)，其中n是flag的长度
    空间复杂度：O(n)，需要存储所有前缀
    """
    if not text or not flag:
        return text
    
    # 替换完整的flag在全文任何地方
    text = text.replace(flag, '')

    # 生成flag的所有可能的前缀（从完整到单个字符）
    flag_variants = [flag[:i] for i in range(len(flag), 4, -1)]
    
    # 检查文本是否以任何变体结尾
    for variant in flag_variants:
        if text.endswith(variant):
            return text[:-len(variant)].rstrip()
    
    return text.rstrip()

def json_content(content):
    return json.dumps({"content": content}, ensure_ascii=False)

def json_success(success):
    return json.dumps({"success": success}, ensure_ascii=False)

def json_error(error):
    return json.dumps({"error": error}, ensure_ascii=False)

def json_empty():
    return json.dumps({})

def context_replace(context):
    # 将 <think>内容</think> 替换为 ::: reasoning 内容 :::
    if '<think' in context or '</think' in context:
        context = _THINK_START_PATTERN.sub('::: reasoning\n', context)
        context = _THINK_END_PATTERN.sub('\n:::', context)
    return context

def context_filter(context):
    # 将 ::: reasoning 内容 ::: 去除
    if "::: reasoning\n" in context:
        context = _REASONING_PATTERN.sub('', context)
    return context