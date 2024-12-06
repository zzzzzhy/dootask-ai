from flask import Flask, request, jsonify, Response, stream_with_context
from helper.utils import get_model_instance, check_timeouts, get_swagger_ui, json_empty, json_error, json_content, filter_end_flag
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

# AI结束对话的标记
END_CONVERSATION_MARK = "<!--::END_CHAT::-->"

# 流式响应超时时间
STREAM_TIMEOUT = 300

# 启动超时检查线程
threading.Thread(target=check_timeouts, daemon=True, name="timeout_checker").start()

# 创建 RedisManager
redis_manager = RedisManager()

# 处理聊天请求
@app.route('/chat', methods=['POST', 'GET'])
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
        system_message = extras_json.get('system_message')
        server_url = extras_json.get('server_url')
        api_key = extras_json.get('api_key')
        agency = extras_json.get('agency')
        before_text = extras_json.get('before_text')
        context_key = extras_json.get('context_key')
        context_limit = int(extras_json.get('context_limit', 0))
    except json.JSONDecodeError:
        return jsonify({"code": 400, "error": "Invalid extras parameter"})

    # 检查 extras 解析后的必要参数是否为空
    if not all([model_type, model_name, server_url, api_key]):
        return jsonify({"code": 400, "error": "Parameter error in extras"})

    # 上下文 before_text 处理
    if not before_text:
        before_text = []
    elif isinstance(before_text, str):
        before_text = [['human', before_text]]
    elif isinstance(before_text, list):
        if before_text and isinstance(before_text[0], str):
            before_text = [['human', text] for text in before_text]

    # 如果是群里的消息
    chat_state_key = ''
    if dialog_type == 'group':
        # 获取用户对话状态
        before_text.append(["human", f"如果你判断用户想要结束对话（比如说再见、谢谢、不打扰了等），请在回复末尾添加标记：{END_CONVERSATION_MARK}"])
        chat_state_key = f"chat_state_{dialog_id}"

        # 如果是@消息，开启对话状态
        if mention:
            redis_manager.set_cache(chat_state_key, "active", ex=86400)
        # 如果没有@且不在对话状态中，不回复
        elif not redis_manager.get_cache(chat_state_key):
            return jsonify({"code": 200, "data": {}})

    # 创建请求客户端
    request_client = Request(server_url, version, token, dialog_id)

    # 获取或初始化上下文
    context_key = f"{dialog_id}_{context_key}" if context_key else f"{dialog_id}"
    
    # 如果是清空上下文的命令
    if text in CLEAR_COMMANDS:
        redis_manager.delete_context(context_key)
        # 调用回调
        request_client.call({
            "notice": "上下文已清空",
            "silence": "yes",
            "source": "ai",
        }, action='notice')
        return jsonify({"code": 200, "data": {}})

    # 创建消息
    send_id = request_client.call({
        "text": '...',
        "text_type": "md",
        "silence": "yes",
        "reply_id": msg_id,
        "reply_check": "yes",
    })
    if not send_id:
        return jsonify({"code": 400, "error": "Send message failed"})

    # 生成随机8位字符串
    stream_key = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 将输入存储到 Redis
    redis_manager.set_input(send_id, {
        "text": text,
        "token": token,
        "dialog_id": dialog_id,
        "version": version,

        "before_text": before_text,
        "chat_state_key": chat_state_key,
    
        "model_type": model_type,
        "model_name": model_name,
        "system_message": system_message,
        "server_url": server_url,
        "api_key": api_key,
        "agency": agency,
        "context_limit": context_limit,

        "context_key": context_key,
        "stream_key": stream_key,
        "created_at": int(time.time()),
        "status": "prepare",
        "response": "",
    })

    # 通知 stream 地址
    request_client.call({
        "userid": msg_uid,
        "stream_url": f"/stream/{send_id}/{stream_key}",
        "source": "ai",
    }, action='stream')

    # 返回成功响应
    return jsonify({"code": 200, "data": {"id": send_id, "key": stream_key}})

# 处理流式响应
@app.route('/stream/<msg_id>/<stream_key>', methods=['GET'])
def stream(msg_id, stream_key):
    if not stream_key:
        return Response(
            f"id: {msg_id}\nevent: done\ndata: {json_error('No key')}\n\n",
            mimetype='text/event-stream'
        )

    # 检查 msg_id 是否在 Redis 中
    data = redis_manager.get_input(msg_id)
    if not data:
        return Response(
            f"id: {msg_id}\nevent: done\ndata: {json_error('No such ID')}\n\n",
            mimetype='text/event-stream'
        )

    # 检查 stream_key 是否正确
    if stream_key != data["stream_key"]:
        return Response(
            f"id: {msg_id}\nevent: done\ndata: {json_error('Invalid key')}\n\n",
            mimetype='text/event-stream'
        )

    # 如果 status 为 finished，直接返回
    if data["status"] == "finished":
        return Response(
            f"id: {msg_id}\nevent: replace\ndata: {json_content(data['response'])}\n\n"
            f"id: {msg_id}\nevent: done\ndata: {json_empty()}\n\n",
            mimetype='text/event-stream'
        )

    def stream_generate(msg_id, msg_key, data, redis_manager):
        # 更新数据状态
        data["status"] = "processing"
        redis_manager.set_input(msg_id, data)

        response = ""
        try:
            # 获取对应的模型实例
            model = get_model_instance(
                model_type=data["model_type"],
                model_name=data["model_name"],
                api_key=data["api_key"],
                agency=data["agency"]
            )

            # 获取上下文
            context = redis_manager.get_context(data["context_key"])

            # 添加系统消息到上下文开始
            if data["system_message"]:
                context.insert(0, ("system", data["system_message"]))

            # 添加 before_text 到上下文
            if data["before_text"]:
                for item in data["before_text"]:
                    context.append(item)

            # 添加用户的新消息
            context.append(("human", data["text"]))
            
            # 开始请求流式响应
            for chunk in model.stream(context):
                if chunk.content:
                    response += chunk.content
                    redis_manager.set_cache(msg_key, filter_end_flag(response, END_CONVERSATION_MARK), ex=STREAM_TIMEOUT)

            # 更新上下文
            redis_manager.extend_contexts(data["context_key"], [
                ("human", data["text"]),
                ("assistant", response)
            ], data["model_type"], data["model_name"], data["context_limit"])

            # 检查是否包含结束对话标记
            if data.get("chat_state_key") and END_CONVERSATION_MARK in response:
                response = filter_end_flag(response, END_CONVERSATION_MARK)
                redis_manager.delete_cache(data["chat_state_key"])
                redis_manager.delete_context(data["context_key"])
            
        except Exception as e:
            # 处理异常
            response = str(e)
            redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)

        # 更新数据状态
        data["status"] = "finished"
        data["response"] = response
        redis_manager.set_input(msg_id, data)

        # 创建请求客户端
        request_client = Request(
            server_url=data["server_url"], 
            version=data["version"], 
            token=data["token"], 
            dialog_id=data["dialog_id"]
        )

        # 更新完整消息
        request_client.call({
            "update_id": msg_id,
            "update_mark": "no",
            "text": response,
            "text_type": "md",
            "silence": "yes"
        })

    def stream_producer():
        # 生成消息 key
        msg_key = f"stream_msg_{msg_id}"
        
        # 如果是第一个请求，启动异步生产者
        if redis_manager.set_cache(msg_key, "", ex=STREAM_TIMEOUT, nx=True):
            threading.Thread(
                target=stream_generate,
                args=(msg_id, msg_key, data, redis_manager),
                daemon=True
            ).start()

        # 所有请求都作为消费者处理
        wait_start = time.time()
        last_response = ""
        while True:
            if time.time() - wait_start > STREAM_TIMEOUT:
                yield f"id: {msg_id}\nevent: replace\ndata: {json_content('Request timeout')}\n\n"
                yield f"id: {msg_id}\nevent: done\ndata: {json_error('Timeout')}\n\n"
                redis_manager.delete_cache(msg_key)
                return

            response = redis_manager.get_cache(msg_key)
            if response:
                if not last_response:
                    yield f"id: {msg_id}\nevent: replace\ndata: {json_content(response)}\n\n"
                else:
                    append_response = response[len(last_response):]
                    if append_response:
                        yield f"id: {msg_id}\nevent: append\ndata: {json_content(append_response)}\n\n"
                last_response = response

                current_data = redis_manager.get_input(msg_id)
                if current_data and current_data["status"] == "finished":
                    yield f"id: {msg_id}\nevent: done\ndata: {json_empty()}\n\n"
                    redis_manager.delete_cache(msg_key)
                    return

            time.sleep(0.1)

    # 返回流式响应
    return Response(
        stream_with_context(stream_producer()),
        mimetype='text/event-stream'
    )

# 处理直接请求
@app.route('/invoke', methods=['POST', 'GET'])
def invoke():
    # 优先从 header 获取配置，如果不存在则从 POST 参数获取
    text = request.args.get('text') or request.form.get('text')
    model_type = request.args.get('model_type') or request.form.get('model_type') or 'openai'
    model_name = request.args.get('model_name') or request.form.get('model_name') or 'gpt-3.5-turbo'
    system_message = request.args.get('system_message') or request.form.get('system_message')
    api_key = request.args.get('api_key') or request.form.get('api_key')
    agency = request.args.get('agency') or request.form.get('agency')
    context_key = request.args.get('context_key') or request.form.get('context_key')
    context_limit = int(request.args.get('context_limit') or request.form.get('context_limit') or 0)
    
    # 检查必要参数是否为空
    if not all([text, api_key]):
        return jsonify({"code": 400, "error": "Parameter error"})

    # 获取模型实例
    model = get_model_instance(
        model_type=model_type,
        model_name=model_name,
        api_key=api_key,
        agency=agency,
        streaming=False,
    )

    # 初始化上下文
    if context_key:
        context = redis_manager.get_context(f"invoke_{context_key}")
    else:
        context = []

    # 添加系统消息到上下文
    if system_message:
        context.insert(0, ("system", system_message))

    # 添加用户的新消息
    context.append(("human", text))

    # 开始请求直接响应
    try:
        response = model.invoke(context)
        if context_key:
            redis_manager.extend_contexts(f"invoke_{context_key}", [
                ("human", text),
                ("assistant", response.content)
            ], model_type, model_name, context_limit)
        return jsonify({
            "code": 200, 
            "data": {
                "content": response.content,
                "usage": {
                    "total_tokens": response.usage_metadata.get("total_tokens", 0),
                    "prompt_tokens": response.usage_metadata.get("input_tokens", 0),
                    "completion_tokens": response.usage_metadata.get("output_tokens", 0)
                }
            }
        })
    except Exception as e:
        return jsonify({"code": 500, "error": str(e)})

# 健康检查
@app.route('/health')
def health():
    try:
        # 检查 Redis 连接
        redis_manager = RedisManager()
        redis_manager.client.ping()
        return jsonify({"status": "healthy", "redis": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

# Swagger UI route
@app.route('/swagger')
def swagger():
    return get_swagger_ui()

# Swagger YAML route
@app.route('/swagger.yaml')
def swagger_yaml():
    return app.send_static_file('swagger.yaml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=SERVER_PORT)
