from flask import Flask, request, jsonify, Response, stream_with_context
from utils import get_model_instance, callback_status
import json
import os

app = Flask(__name__)

# 用于存储上下文的字典
context_storage = {}

# 全局变量设置
PORT = int(os.environ.get('PORT', 5001))

@app.route('/', methods=['GET'])
def chat():
    # 从请求中获取参数
    model_type = request.args.get('model_type', 'openai')
    model_name = request.args.get('model')
    user_input = request.args.get('input')
    dialog_id = request.args.get('dialog_id', '0')
    message_id = request.args.get('message_id', '0')
    content_id = request.args.get('content_id')
    
    # 从 headers 或 query 获取参数
    server_url = request.headers.get('server_url') or request.args.get('server_url')
    version = request.headers.get('version') or request.args.get('version')
    token = request.headers.get('token') or request.args.get('token')
    api_key = request.headers.get('Authorization') or request.args.get('ak')
    proxy = request.headers.get('Agent') or request.args.get('agent')
    
    # 定义清空上下文的命令列表
    clear_commands = [":clear", ":reset", ":restart", ":new", 
                     ":清空上下文", ":重置上下文", ":重启", ":重启对话"]
    
    # 检查是否是清空上下文的命令
    if user_input in clear_commands and content_id:
        if content_id in context_storage:
            del context_storage[content_id]
        # 调用回调
        callback_status(
            server_url=server_url,
            version=version,
            token=token,
            update_id=message_id,
            dialog_id=dialog_id,
            text='Operation Successful'
        )
        return Response(
            f"id: {message_id}\nevent: update\ndata: 上下文已清空\n\n",
            mimetype='text/event-stream'
        )

    # 优先从 header 获取配置，如果不存在则从 GET 参数获取
    if not api_key:
        # 调用回调
        callback_status(
            server_url=server_url,
            version=version,
            token=token,
            update_id=message_id,
            dialog_id=dialog_id,
            text='API key is required'
        )
        return Response(
            f"id: {message_id}\nevent: update\ndata: API key is required\n\n",
            mimetype='text/event-stream'
        )

    # 优先从 header 获取代理，如果不存在则从 GET 参数获取
    if proxy:
        os.environ['HTTPS_PROXY'] = proxy
        os.environ['HTTP_PROXY'] = proxy

    try:
        # 获取对应的模型实例
        model = get_model_instance(model_type, model_name, api_key)
    except Exception as e:
        error_message = str(e)
        # 调用回调
        callback_status(
            server_url=server_url,
            version=version,
            token=token,
            update_id=message_id,
            dialog_id=dialog_id,
            text=error_message,
        )
        return Response(
            f"id: {message_id}\nevent: update\ndata: {error_message}\n\n",
            mimetype='text/event-stream'
        )

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
