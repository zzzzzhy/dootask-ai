from flask import Flask, request, jsonify, Response, stream_with_context
from langchain_core.messages import HumanMessage
from utils import get_model_instance
from request import Request
import json
import os
import time
import random
import string
import threading

app = Flask(__name__)

# 用于存储上下文的字典
CONTEXT_STORAGE = {}

# 用于存数输入的字典
INPUT_STORAGE = {}

# 服务启动端口
SERVER_PORT = int(os.environ.get('PORT', 5001))

# 清空上下文的命令
CLEAR_COMMANDS = [":clear", ":reset", ":restart", ":new", ":清空上下文", ":重置上下文", ":重启", ":重启对话"]

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

    # 创建请求客户端
    request_client = Request(server_url, version, token, dialog_id)

    # 创建消息
    send_id = request_client.call({
        "reply_id": reply_id,
        "text": '...',
        "text_type": "md",
        "silence": "yes"
    })
    if not send_id:
        return jsonify({"code": 400, "error": "Send message failed"})

    # 定义上下文键
    context_key = f"{dialog_id}_{msg_uid}"

    # 生成随机16位字符串
    stream_key = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 检查是否是清空上下文的命令
    if text in CLEAR_COMMANDS:
        if context_key in CONTEXT_STORAGE:
            del CONTEXT_STORAGE[context_key]
        # 调用回调
        request_client.call({
            "update_id": send_id,
            "update_mark": "no",
            "text": "Operation Successful",
            "text_type": "md",
            "silence": "yes"
        })
        return jsonify({"code": 200, "data": {"id": send_id, "key": stream_key}})

    # 设置代理
    if agency:
        os.environ['HTTP_PROXY'] = agency
        os.environ['HTTPS_PROXY'] = agency

    # 获取对应的模型实例
    try:
        model = get_model_instance(model_type, model_name, api_key)
    except Exception as e:
        error_message = str(e)
        # 调用回调
        request_client.call({
            "update_id": send_id,
            "update_mark": "no",
            "text": error_message,
            "text_type": "md",
            "silence": "yes"
        })
        return jsonify({"code": 500, "error": error_message})

    # 还原代理
    if agency:
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)

    # 从上下文存储中获取上下文
    context = CONTEXT_STORAGE.get(context_key, "") if context_key else ""

    # 将用户输入与上下文结合
    full_input = f"{context}\n{text}" if context else text

    # 将输入存储到 INPUT_STORAGE
    INPUT_STORAGE[send_id] = {
        "model": model,
        "model_type": model_type,
        "model_name": model_name,
        "context_key": context_key,
        "full_input": full_input,
        "request_client": request_client,
        "stream_key": stream_key,
        
        "status": "processing",
        "created_at": int(time.time()),
        "response": ""
    }

    # 通知 stream 地址
    request_client.call({
        "userid": msg_uid,
        "stream_url": f"/ai/stream/{send_id}/{stream_key}",
    }, action='stream')

    # 创建超时检查函数
    def check_timeout():
        time.sleep(60)  # 等待1分钟
        if send_id in INPUT_STORAGE and INPUT_STORAGE[send_id]["status"] == "processing":
            # 如果1分钟后状态还是processing，更新消息
            INPUT_STORAGE[send_id]["request_client"].call({
                "update_id": send_id,
                "update_mark": "no",
                "text": "Request timeout. Please try again.",
                "text_type": "md",
                "silence": "yes"
            })
            # 更新状态
            INPUT_STORAGE[send_id]["status"] = "finished"
            INPUT_STORAGE[send_id]["response"] = "Request timeout. Please try again."

    # 启动超时检查线程
    threading.Thread(target=check_timeout, daemon=True).start()

    # 清理超过10分钟的数据
    current_time = int(time.time())
    expired_ids = [
        msg_id for msg_id, data in INPUT_STORAGE.items()
        if current_time - data["created_at"] > 600  # 10分钟 = 600秒
    ]
    for msg_id in expired_ids:
        del INPUT_STORAGE[msg_id]

    # 返回成功响应
    return jsonify({"code": 200, "data": {"id": send_id, "key": stream_key}})

# 处理流式响应
@app.route('/stream/<msg_id>/<stream_key>', methods=['GET'])
def stream(msg_id, stream_key):
    # 将 msg_id 转换为整数类型
    try:
        msg_id = int(msg_id)
    except ValueError:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: Invalid msg id format\n\n",
            mimetype='text/event-stream'
        )

    # 检查 msg_id 是否在 INPUT_STORAGE 中
    if msg_id not in INPUT_STORAGE:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: Invalid msg id\n\n",
            mimetype='text/event-stream'
        )

    # 获取对应的参数
    data = INPUT_STORAGE[msg_id]
    model, model_type, model_name, context_key, full_input, request_client = (
        data["model"], data["model_type"], data["model_name"], data["context_key"], data["full_input"], data["request_client"]
    )

    # 检查 stream_key 是否正确
    if stream_key != data["stream_key"]:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: Invalid key\n\n",
            mimetype='text/event-stream'
        )

    # 如果 status 为 finished，直接返回
    if data["status"] == "finished":
        return Response(
            f"id: {msg_id}\nevent: replace\ndata: {data['response']}\n\n",
            mimetype='text/event-stream'
        )

    # 判断如果超过 180 秒，直接返回
    if time.time() - data["created_at"] > 180:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: Timeout\n\n",
            mimetype='text/event-stream'
        )

    # 根据不同的模型类型处理流式响应
    def generate():
        full_response = ""
        try:
            # Openai、Claude、Gemini
            if model_type in ["openai", "claude", "gemini"]:
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        full_response += chunk.content
                        yield f"id: {msg_id}\nevent: append\ndata: {chunk.content}\n\n"
            # 智谱AI
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
            # 通义千问
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
            # 文心一言
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
            # LLaMA
            elif model_type == "llama":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            # Cohere
            elif model_type == "cohere":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            # EleutherAI
            elif model_type == "eleutherai":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"
            # Mistral AI
            elif model_type == "mistral":
                for chunk in model.stream([HumanMessage(content=full_input)]):
                    if chunk.content:
                        content = chunk.content
                        full_response += content
                        yield f"id: {msg_id}\nevent: append\ndata: {content}\n\n"

            # 更新状态、上下文
            INPUT_STORAGE[msg_id]["status"] = "finished"
            INPUT_STORAGE[msg_id]["response"] = full_response
            CONTEXT_STORAGE[context_key] = f"{full_input}\n{full_response}"

            # 更新完整消息
            request_client.call({
                "update_id": msg_id,
                "update_mark": "no",
                "text": full_response,
                "text_type": "md",
                "silence": "yes"
            })

        except Exception as e:
            yield f"id: {msg_id}\nevent: error\ndata: {str(e)}\n\n"

    # 返回流式响应
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

# 读取 swagger.yaml 文件
@app.route('/swagger.yaml')
def swagger():
    return app.send_static_file('swagger.yaml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=SERVER_PORT)
