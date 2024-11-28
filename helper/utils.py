from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import QianWen, ErnieBot
from langchain_zhipuai import ChatZhipuAI
from langchain_community.chat_models import ChatCohere
import requests

def get_model_instance(model_type, model_name, api_key):
    """
    根据模型类型返回对应的模型实例
    """
    try:
        if model_type == "openai":
            return ChatOpenAI(
                model_name=model_name,
                openai_api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "claude":
            return ChatAnthropic(
                model=model_name,
                anthropic_api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "gemini":
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "zhipu":
            return ChatZhipuAI(
                api_key=api_key,
                model=model_name,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "qwen":
            return QianWen(
                api_key=api_key,
                model=model_name,
                streaming=True
            )
        elif model_type == "wenxin":
            return ErnieBot(
                api_key=api_key,
                model=model_name,
                streaming=True
            )
        elif model_type == "cohere":
            return ChatCohere(
                model=model_name,
                api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
    except Exception as e:
        raise RuntimeError(f"Failed to create model instance: {str(e)}")
