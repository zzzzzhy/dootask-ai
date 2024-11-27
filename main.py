from flask import Flask, request, jsonify, Response, stream_with_context
from utils import get_model_instance, call_request
import json
import os

app = Flask(__name__)

# 用于存储上下文的字典
context_storage = {}

# 用于存数输入的字典
input_storage = {}

# 全局变量设置
PORT = int(os.environ.get('PORT', 5001))

# 处理聊天请求
@app.route('/chat', methods=['GET'])
def chat():
    # 优先从 header 获取配置，如果不存在则从 GET 参数获取
    text = request.args.get('text') or request.form.get('text')
    token = request.args.get('token') or request.form.get('token')
    dialog_id = int(request.args.get('dialog_id') or request.form.get('dialog_id') or 0)
    dialog_type = request.args.get('dialog_type') or request.form.get('dialog_type')
    msg_id = int(request.args.get('msg_id') or request.form.get('msg_id') or 0)
    msg_uid = int(request.args.get('msg_uid') or request.form.get('msg_uid') or 0)
    mention = int(request.args.get('mention') or request.form.get('mention') or 0)
    bot_uid = int(request.args.get('bot_uid') or request.form.get('bot_uid') or 0)
    version = request.args.get('version') or request.form.get('version')
    extras = request.args.get('extras') or request.form.get('extras') or '{}'
    
    # 检查必要参数是否为空
    if not all([text, token, dialog_id, msg_uid, bot_uid, version]):
        return jsonify({"code": 400, "error": "Parameter error"})

    # 解析 extras 参数
    try:
        extras_json = json.loads(extras)
        model_type = extras_json.get('model_type', 'openai')
        model_name = extras_json.get('model_name', 'gpt-3.5-turbo')
        server_url = extras_json.get('server_url')
        api_key = extras_json.get('api_key')
        agency = extras_json.get('agency')
    except json.JSONDecodeError:
        return jsonify({"code": 400, "error": "Invalid extras parameter"})

    # 检查 extras 解析后的必要参数是否为空
    if not all([model_type, model_name, server_url, api_key]):
        return jsonify({"code": 400, "error": "Parameter error in extras"})

    # 如果是群聊，reply_id（回复消息） 为 msg_id
    reply_id = '0'
    if dialog_type == 'group':
        reply_id = msg_id

    # 创建消息
    send_id = call_request(
        server_url=server_url,
        version=version,
        token=token,
        action='sendtext',

        data={
            "dialog_id": dialog_id,
            "reply_id": reply_id,
            "text": '...',
            "text_type": "md",
            "silence": "yes"
        }
    )
    if not send_id:
        return jsonify({"code": 400, "error": "Send message failed"})

    # 发送 stream 地址（异步）
    asyncio.create_task(
        call_request(
            server_url=server_url,
            version=version,
            token=token,
            action='stream',

            data={
                "dialog_id": dialog_id,
                "userid": msg_uid,
                "stream_url": "/ai/stream/" + send_id
            }
        )
    )

    # 定义清空上下文的命令列表
    clear_commands = [":clear", ":reset", ":restart", ":new", ":清空上下文", ":重置上下文", ":重启", ":重启对话"]

    # 定义上下文键
    context_key = f"{dialog_id}_{msg_uid}"
    
    # 检查是否是清空上下文的命令
    if text in clear_commands:
        if context_key in context_storage:
            del context_storage[context_key]
        # 调用回调
        call_request(
            server_url=server_url,
            version=version,
            token=token,
            action='sendtext',

            data={
                "update_id": send_id,
                "update_mark": "no",
                "dialog_id": dialog_id,
                "text": "Operation Successful",
                "text_type": "md",
                "silence": "yes"
            }
        )
        return jsonify({"code": 200, "data": {"id": send_id}})

    # 获取对应的模型实例
    try:
        model = get_model_instance(model_type, model_name, api_key)
    except Exception as e:
        error_message = str(e)
        call_request(
            server_url=server_url,
            version=version,
            token=token,
            action='sendtext',

            data={
                "update_id": send_id,
                "update_mark": "no",
                "dialog_id": dialog_id,
                "text": error_message,
                "text_type": "md",
                "silence": "yes"
            }
        )
        return jsonify({"code": 500, "error": error_message})

    # 从上下文存储中获取上下文
    context = context_storage.get(context_key, "") if context_key else ""

    # 将用户输入与上下文结合
    full_input = f"{context}\n{text}" if context else text

    # 将 full_input 根据 send_id 保存起来
    input_storage[send_id] = {
        "model": model,
        "agency": agency,
        "context_key": context_key,
        "full_input": full_input,
        "status": "processing"
    }

    # 返回消息 ID
    return jsonify({"code": 200, "data": {"id": send_id}})

# 处理流式响应
@app.route('/stream/<msg_id>', methods=['GET'])
def stream(msg_id):
    # 检查 msg_id 是否在 input_storage 中
    if msg_id not in input_storage:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: Invalid msg_id\n\n",
            mimetype='text/event-stream'
        )

    # 获取对应的参数
    model = input_storage[msg_id]["model"]
    model_type = model.model_type
    model_name = model.name
    agency = input_storage[msg_id]["agency"]
    context_key = input_storage[msg_id]["context_key"]
    full_input = input_storage[msg_id]["full_input"]

    # 设置代理
    if agency:
        os.environ['http_proxy'] = agency
        os.environ['https_proxy'] = agency

    def generate():
        full_response = ""
        try:
            # 根据不同的模型类型处理流式响应
            if model_type in ["openai", "claude", "gemini"]:
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        full_response += chunk.content
                        yield f"id: {msg_id}\nevent: append\ndata: {chunk.content}\n\n"
            elif model_type == "zhipu":
                response = model.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": full_input}],
                    stream=True
                )
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
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
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
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
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "llama":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "cohere":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "eleutherai":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            elif model_type == "mistral":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"

            # 更新状态
            input_storage[msg_id]["status"] = "completed"

            # 更新上下文
            context_storage[context_key] = f"{full_input}\n{full_response}"

        except Exception as e:
            yield f"id: {msg_id}\nevent: error\ndata: {str(e)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

# 读取 swagger.yaml 文件
@app.route('/swagger.yaml')
def swagger():
    return app.send_static_file('swagger.yaml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
