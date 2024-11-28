from flask import Flask, request, jsonify, Response, stream_with_context
from langchain_core.messages import HumanMessage
from helper.utils import get_model_instance
from helper.request import Request
from helper.redis import RedisManager
import json
import os
import time
import random
import string
import threading

app = Flask(__name__)

# 服务启动端口
SERVER_PORT = int(os.environ.get('PORT', 5001))

# 清空上下文的命令
CLEAR_COMMANDS = [":clear", ":reset", ":restart", ":new", ":清空上下文", ":重置上下文", ":重启", ":重启对话"]

# 创建 RedisManager
redis_manager = RedisManager()

# 检查超时的线程函数
def check_timeouts():
    while True:
        try:
            # 使用 RedisManager 扫描所有处理中的请求
            for key_id, data in redis_manager.scan_inputs():
                if data and data.get("status") == "processing":
                    if int(time.time()) - data.get("created_at", 0) > 60:
                        # 超时处理
                        data["status"] = "timeout"
                        redis_manager.set_input(key_id, data)
                        request_client = Request(data["server_url"], data["version"], data["token"], data["dialog_id"])
                        request_client.call({
                            "update_id": key_id,
                            "update_mark": "no",
                            "text": "Request timeout. Please try again.",
                            "text_type": "md",
                            "silence": "yes"
                        })
            
            # 清理超过10分钟的数据
            redis_manager.cleanup_expired_data(600)
                
        except Exception as e:
            print(f"Error in timeout checker: {str(e)}")
        time.sleep(1)

# 启动超时检查线程
threading.Thread(target=check_timeouts, daemon=True, name="timeout_checker").start()

# 处理聊天请求
@app.route('/chat', methods=['POST'])
def chat():
    # 优先从 header 获取配置，如果不存在则从 POST 参数获取
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
        redis_manager.delete_context(context_key)
        # 调用回调
        request_client.call({
            "update_id": send_id,
            "update_mark": "no",
            "text": "已清空上下文",
            "text_type": "md",
            "silence": "yes"
        })
        return jsonify({"code": 0, "msg": "success", "data": None})

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

    # 从 Redis 获取上下文
    context = redis_manager.get_context(context_key)

    # 将用户输入与上下文结合
    full_input = f"{context}\n{text}" if context else text

    # 将输入存储到 Redis
    redis_manager.set_input(send_id, {
        "model": model,
        "model_type": model_type,
        "model_name": model_name,
        "context_key": context_key,
        "full_input": full_input,
        "request_client": request_client,
        "server_url": server_url,
        "version": version,
        "token": token,
        "dialog_id": dialog_id,
        "status": "processing",
        "created_at": int(time.time()),
        "stream_key": stream_key,
    })

    # 通知 stream 地址
    request_client.call({
        "userid": msg_uid,
        "stream_url": f"/ai/stream/{send_id}/{stream_key}",
    }, action='stream')

    # 返回成功响应
    return jsonify({"code": 0, "msg": "success", "data": {"id": send_id, "key": stream_key}})

# 处理流式响应
@app.route('/stream', methods=['GET'])
def stream():
    msg_id = request.args.get('msg_id', '')
    stream_key = request.args.get('stream_key', '')

    if not stream_key:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: No stream key\n\n",
            mimetype='text/event-stream'
        )

    # 检查 msg_id 是否在 Redis 中
    data = redis_manager.get_input(msg_id)
    if not data:
        return Response(
            f"id: {msg_id}\nevent: error\ndata: No such ID\n\n",
            mimetype='text/event-stream'
        )

    # 获取对应的参数
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
            data["status"] = "finished"
            data["response"] = full_response
            redis_manager.set_input(msg_id, data)
            redis_manager.set_context(context_key, f"{full_input}\n{full_response}")

            # 清空 model、request_client 释放内存
            data["model"] = None
            data["request_client"] = None
            redis_manager.set_input(msg_id, data)

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

# 健康检查
@app.route('/health')
def health_check():
    try:
        # 检查 Redis 连接
        redis_manager = RedisManager()
        redis_manager.redis_client.ping()
        return jsonify({"status": "healthy", "redis": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# 读取 swagger.yaml 文件
@app.route('/swagger.yaml')
def swagger():
    return app.send_static_file('swagger.yaml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=SERVER_PORT)
