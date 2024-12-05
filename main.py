from flask import Flask, request, jsonify, Response, stream_with_context
from helper.utils import get_model_instance, check_timeouts, get_swagger_ui, json_empty, json_error, json_content
from helper.request import Request
from helper.redis import RedisManager
from helper.vector_store import VectorStoreManager
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.prompts import MessagesPlaceholder
from langchain.prompts import ChatMessagePromptTemplate
from langchain_core.documents import Document
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
    project = request.args.get('project') or request.form.get('project')  # Get project from extras
    task_name = request.args.get('task_name') or request.form.get('task_name')
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
        qianfan_sk = extras_json.get('qianfan_sk')
        context_limit = int(extras_json.get('context_limit', 0))
    except json.JSONDecodeError:
        return jsonify({"code": 400, "error": "Invalid extras parameter"})

    # 检查 extras 解析后的必要参数是否为空
    if not all([model_type, model_name, server_url, api_key]):
        return jsonify({"code": 400, "error": "Parameter error in extras"})

    # 群里使用回复消息模式
    reply_id = int(msg_id) if dialog_type == 'group' else 0

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

    # 获取或初始化上下文
    context_key = f"{dialog_id}_{msg_uid}"
    
    # 如果是清空上下文的命令
    if text in CLEAR_COMMANDS:
        redis_manager.delete_context(context_key)
        # 调用回调
        request_client.call({
            "notice": "清空上下文",
            "silence": "yes",
            "source": "ai",
        }, action='notice')
        return jsonify({"code": 200, "data": {"id": send_id, "key": ""}})

    # 生成随机8位字符串
    stream_key = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 将输入存储到 Redis
    redis_manager.set_input(send_id, {
        "text": text,
        "token": token,
        "dialog_id": dialog_id,
        "version": version,
    
        "model_type": model_type,
        "model_name": model_name,
        "system_message": system_message,
        "server_url": server_url,
        "api_key": api_key,
        "agency": agency,
        "context_limit": context_limit,
        "project": project,  # Add project to redis data
        "task_name": task_name,
        "qianfan_sk": qianfan_sk,

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
        task_name = data.get('task_name', None)
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
            try:
                # 初始化向量存储管理器并获取相关上下文
                vector_store_manager = VectorStoreManager(
                    project=data.get("project", "default"),
                    embedding_api_key=data["api_key"],
                    llm=data["model_type"],
                    qianfan_sk=data.get("qianfan_sk"),
                )
                relevant_docs = vector_store_manager.similarity_search(data["text"],expr=f"'source == {task_name}'")
                vector_context = "\n".join([doc.page_content for doc in relevant_docs]) if relevant_docs else ""
            except ValueError as e:
                print(e)  

            # 添加系统消息和向量上下文到上下文开始
            if data["system_message"]:
                system_msg = data["system_message"] or ""
                
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", f"{system_msg}\n\nHere is some relevant context,The contents are in the <data> tag,<data>{vector_context}<data>"),
                    MessagesPlaceholder(variable_name="redis_history"),
                    ("human", """{question}""")
                ]
            )
            chain = prompt | model
            # 添加用户的新消息
            # context.append(("human", data["text"]))
            msg = prompt.format_prompt(redis_history=context,question=data["text"]).to_messages()
            # 开始请求流式响应
            for chunk in chain.stream(msg):
                if chunk.content:
                    response += chunk.content
                    redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)

            # 更新上下文
            redis_manager.extend_contexts(data["context_key"], [
                ("human", data["text"]),
                ("assistant", response)
            ], data["model_type"], data["model_name"], data["context_limit"])
            
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
    project = request.args.get('project') or request.form.get('project')
    task_name = request.args.get('task_name') or request.form.get('task_name')
    qianfan_sk = request.args.get('qianfan_sk') or request.form.get('qianfan_sk')

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
    try:
        # 初始化向量存储管理器并获取相关上下文
        vector_store_manager = VectorStoreManager(
            project=project,
            embedding_api_key=api_key,
            llm=model_type,
            qianfan_sk=qianfan_sk,
        )
        relevant_docs = vector_store_manager.similarity_search(text,expr=f"'source == {task_name}'")
        vector_context = "\n".join([doc.page_content for doc in relevant_docs]) if relevant_docs else ""
    except Exception as e:
        vector_context = ''
    prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", f"{system_message}\n\nHere is some relevant context,The contents are in the <data> tag,<data>{vector_context}<data>"),
                    MessagesPlaceholder(variable_name="redis_history"),
                    ("human", """{question}""")
                ]
            )
    chain = prompt | model
    msg = prompt.format_prompt(redis_history=context,question=text).to_messages()
    # 开始请求直接响应
    try:
        response = chain.invoke(msg)
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
    
# 添加向量存储
@app.route('/vectors', methods=['POST'])
def add_vectors():
    """添加向量存储接口
    
    POST body 格式:
    {
        "text": "文档内容",
        "metadata": {"source": "任务名称", ...},
        "project": "项目名称",
        "model_type": "openai",
        "api_key": "your-api-key",
        "qianfan_sk": "your-sk"  # 可选
    }
    """
    try:
        # 获取 POST body
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "error": "Missing request body"})
            
        # 获取必需参数
        text = data.get('text')
        metadata = data.get('metadata', {})
        api_key = data.get('api_key')
        
        # 获取可选参数
        project = data.get('project', 'default')
        model_type = data.get('model_type', 'openai')
        qianfan_sk = data.get('qianfan_sk')
        
        # 检查必需参数
        if not all([text, api_key]):
            return jsonify({"code": 400, "error": "Missing required parameters: text and api_key"})
            
        # 检查 source 是否存在于 metadata 中
        if not metadata.get('source'):
            return jsonify({"code": 400, "error": "metadata.source is required"})
            
        # 初始化向量存储管理器
        vector_store_manager = VectorStoreManager(
            project=project,
            embedding_api_key=api_key,
            llm=model_type,
            qianfan_sk=qianfan_sk
        )
        
        document = Document(
            page_content=text,
            metadata=metadata
        )
        
        # 添加文档到向量存储
        success = vector_store_manager.add_documents([document])
        
        if success:
            return jsonify({
                "code": 200,
                "message": "Vector added successfully"
            })
        return jsonify({
            "code": 500,
            "error": "Failed to add vector"
        })
    except json.JSONDecodeError:
        return jsonify({
            "code": 400,
            "error": "Invalid JSON format in request body"
        })
    except Exception as e:
        return jsonify({
            "code": 500,
            "error": f"Unexpected error: {str(e)}"
        })

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
