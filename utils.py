from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from zhipuai import ZhipuAI
from dashscope import Generation
import erniebot
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
            return ZhipuAI(api_key=api_key)
        elif model_type == "qwen":
            import dashscope
            dashscope.api_key = api_key
            return Generation
        elif model_type == "wenxin":
            erniebot.api_type = 'aistudio'
            erniebot.access_token = api_key
            return erniebot.ChatCompletion
        elif model_type == "llama":
            return ChatLlama(
                model_name=model_name,
                api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "cohere":
            return ChatCohere(
                model_name=model_name,
                api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "eleutherai":
            return ChatGPTNeoX(
                model_name=model_name,
                api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        elif model_type == "mistral":
            return ChatMistral(
                model_name=model_name,
                api_key=api_key,
                temperature=0.7,
                streaming=True
            )
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
    except Exception as e:
        raise RuntimeError(f"Failed to create model instance: {str(e)}")

def callback_status(server_url, version, token, update_id, dialog_id, text, update_mark='no', text_type='md', silence='yes'):
    """
    回调状态到指定服务器
    """
    if not server_url or not server_url.startswith(('http://', 'https://')):
        return
    
    try:
        headers = {
            'version': version,
            'token': token
        }
        
        data = {
            'update_id': update_id,
            'update_mark': update_mark,
            'dialog_id': dialog_id,
            'text': text,
            'text_type': text_type,
            'silence': silence
        }
        
        requests.post(server_url, headers=headers, json=data, timeout=15)
    except Exception:
        pass  # 忽略回调错误
