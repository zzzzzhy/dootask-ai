from flask import Flask, request, jsonify, Response, stream_with_context
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from zhipuai import ZhipuAI
from dashscope import Generation
from erniebot import ChatCompletion
from langchain_core.messages import HumanMessage
import json
import os

app = Flask(__name__)

# 用于存储上下文的字典
context_storage = {}

# 全局变量设置
PORT = int(os.environ.get('PORT', 5001))

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
            return Generation(api_key=api_key)
        elif model_type == "wenxin":
            ChatCompletion.api_key = api_key
            return ChatCompletion
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

@app.route('/', methods=['GET'])
def chat():
    # 从请求中获取参数
    model_type = request.args.get('model_type', 'openai')  # 默认使用 openai
    model_name = request.args.get('model')
    user_input = request.args.get('input')
    message_id = request.args.get('id', '0')
    content_id = request.args.get('content_id')

    # 优先从 header 获取配置，如果不存在则从 GET 参数获取
    api_key = request.headers.get('Authorization') or request.args.get('ak')
    if not api_key:
        return jsonify({"error": "API key is required"}), 401

    # 优先从 header 获取代理，如果不存在则从 GET 参数获取
    proxy = request.headers.get('Agent') or request.args.get('agent')
    if proxy:
        os.environ['HTTPS_PROXY'] = proxy
        os.environ['HTTP_PROXY'] = proxy

    try:
        # 获取对应的模型实例
        model = get_model_instance(model_type, model_name, api_key)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # 从上下文存储中获取上下文，仅当 content_id 存在时
    context = context_storage.get(content_id, "") if content_id else ""

    # 将用户输入与上下文结合
    full_input = f"{context}\n{user_input}" if context else user_input

    def generate():
        full_response = ""
        try:
            # 根据不同的模型类型处理流式响应
            if model_type in ["openai", "claude", "gemini"]:
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        full_response += chunk.content
                        yield f"id: {message_id}\nevent: append\ndata: {chunk.content}\n\n"
            elif model_type == "zhipu":
                response = model.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": full_input}],
                    stream=True
                )
                for chunk in response:
                    if chunk.choices[0].delta.content:  # 修正访问方式
                        content = chunk.choices[0].delta.content  # 修正访问方式
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "qwen":
                response = model.call(
                    model=model_name,
                    messages=[{"role": "user", "content": full_input}],
                    stream=True
                )
                for chunk in response:
                    if chunk.output and chunk.output.text:
                        content = chunk.output.text
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "wenxin":
                response = model.create(
                    model=model_name,
                    messages=[{"role": "user", "content": full_input}],
                    stream=True
                )
                for chunk in response:
                    if chunk.get('result'):
                        content = chunk.get('result', '')
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "llama":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "cohere":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "eleutherai":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "mistral":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {message_id}\nevent: append\ndata: {content}\n\n"

            # 仅当 content_id 存在时才更新上下文
            if content_id:
                context_storage[content_id] = f"{full_input}\n{full_response}"

        except Exception as e:
            yield f"id: {message_id}\nevent: error\ndata: {str(e)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
