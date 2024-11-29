from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import (
    ChatZhipuAI,
    ChatTongyi,
    QianfanChatEndpoint,
    ChatCohere
)
from .request import Request
from .redis import RedisManager
import requests
import os
import time

def get_model_instance(model_type, model_name, api_key, agency=None, streaming=True):
    """根据模型类型返回对应的模型实例"""

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
        "zhipu": (ChatZhipuAI, None),
        "qwen": (ChatTongyi, None),
        "wenxin": (QianfanChatEndpoint, None),
        "cohere": (ChatCohere, None),
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

        common_params = {
            "model": model_name,
            "temperature": 0.7,
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
                if data and data.get("status") == "processing":
                    if current_time - data.get("created_at", 0) > 60:
                        # 超时处理
                        data["status"] = "finished"
                        data["response"] = "Request timeout. Please try again."
                        redis_manager.set_input(key_id, data)
                        request_client = Request(data["server_url"], data["version"], data["token"], data["dialog_id"])
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
