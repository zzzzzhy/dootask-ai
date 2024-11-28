from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import (
    ChatZhipuAI,
    ChatTongyi as QianWen,  # 通义千问
    ErnieBotChat as ErnieBot,  # 文心一言
    ChatCohere
)
import requests
import os

def get_model_instance(model_type, model_name, api_key, agency=None):
    """根据模型类型返回对应的模型实例"""
    # 如果提供了代理，设置环境变量
    if agency:
        os.environ["HTTPS_PROXY"] = agency
        os.environ["HTTP_PROXY"] = agency

    model_configs = {
        "openai": (ChatOpenAI, {
            "openai_api_key": api_key,
            "openai_proxy": agency if agency else None,
        }),
        "claude": (ChatAnthropic, {
            "anthropic_api_key": api_key,
            "anthropic_proxy": agency if agency else None,
        }),
        "gemini": (ChatGoogleGenerativeAI, {
            "google_api_key": api_key,
            "google_proxy": agency if agency else None,
        }),
        "zhipu": (ChatZhipuAI, {
            "api_key": api_key,
            "proxy": agency if agency else None,
        }),
        "qwen": (QianWen, {
            "api_key": api_key,
            "proxy": agency if agency else None,
        }),
        "wenxin": (ErnieBot, {
            "api_key": api_key,
            "proxy": agency if agency else None,
        }),
        "cohere": (ChatCohere, {
            "api_key": api_key,
            "proxy": agency if agency else None,
        }),
    }

    try:
        model_class, config = model_configs.get(model_type, (None, None))
        if model_class is None:
            raise ValueError(f"Unsupported model type: {model_type}")

        common_params = {
            "model": model_name,
            "temperature": 0.7,
            "streaming": True
        }
        config.update(common_params)

        return model_class(**config)
    except Exception as e:
        raise RuntimeError(f"Failed to create model instance: {str(e)}")
    finally:
        # 清理环境变量
        if agency:
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("HTTP_PROXY", None)
