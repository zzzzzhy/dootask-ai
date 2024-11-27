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

def call_request(server_url, version, token, action, data):
    """
    发送请求到服务器
    """
    if not server_url or not server_url.startswith(('http://', 'https://')):
        return
    
    if action == "stream":
        call_url = server_url + "/api/dialog/msg/stream"
    else:
        call_url = server_url + "/api/dialog/msg/sendtext"

    try:
        headers = {
            'version': version,
            'token': token
        }
        
        response = requests.post(call_url, headers=headers, json=data, timeout=15)
        response_json = response.json()
        return response_json.get('data', {}).get('id')
    except Exception:
        pass