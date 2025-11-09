from types import SimpleNamespace
from pathlib import Path
from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
from helper.utils import get_model_instance, get_swagger_ui, json_empty, json_error, json_content, replace_think_content, remove_reasoning_content, process_html_content
from helper.invoke import extract_param, coerce_int, coerce_float, coerce_str, parse_context, build_invoke_stream_key
from helper.models import ModelListError, get_models_list
from helper.request import Request
from helper.redis import handle_context_limits, RedisManager
from helper.thread_pool import DynamicThreadPoolExecutor
from helper.config import SERVER_PORT, CLEAR_COMMANDS, STREAM_TIMEOUT
import json
import time
import random
import string

app = Flask(__name__)
CORS(app)  # 启用CORS，允许所有来源的跨域请求

UI_DIST_PATH = Path(__file__).resolve().parent / "static" / "ui"


def ui_assets_available() -> bool:
    return UI_DIST_PATH.exists() and UI_DIST_PATH.is_dir()

# 初始化 Redis 管理器
redis_manager = RedisManager()

# 初始化线程池
thread_pool = DynamicThreadPoolExecutor(
    min_workers=5,
    max_workers=50,
    thread_name_prefix="ai_stream_"
)

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
        model_name = extras_json.get('model_name', 'gpt-5-nano')
        system_message = extras_json.get('system_message')
        server_url = extras_json.get('server_url')
        api_key = extras_json.get('api_key')
        base_url = extras_json.get('base_url')
        agency = extras_json.get('agency')
        temperature = float(extras_json.get('temperature', 0.7))
        max_tokens = int(extras_json.get('max_tokens', 0))
        thinking = int(extras_json.get('thinking', 0))
        before_text = extras_json.get('before_text')
        before_clear = int(extras_json.get('before_clear', 0))
        context_key = extras_json.get('context_key', '')
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

    # 创建请求客户端
    request_client = Request(server_url, version, token, dialog_id)

    # 定义上下文键
    context_key = f"{model_type}_{model_name}_{dialog_id}_{context_key}"

    # 如果是清空上下文的命令
    if text in CLEAR_COMMANDS:
        redis_manager.delete_context(context_key)
        # 调用回调
        request_client.call({
            "notice": "上下文已清空",
            "silence": "yes",
            "source": "ai",
        }, action='notice')
        return jsonify({"code": 200, "data": {"desc": "Context cleared"}})

    # 如果需要在请求前清空上下文
    if before_clear:
        redis_manager.delete_context(context_key)

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

    # 处理HTML内容（图片标签）
    text = process_html_content(text)
    
    # 生成随机8位字符串
    stream_key = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 将输入存储到 Redis
    redis_manager.set_input(send_id, {
        "text": text,
        "token": token,
        "dialog_id": dialog_id,
        "version": version,

        "before_text": before_text,
    
        "model_type": model_type,
        "model_name": model_name,
        "system_message": system_message,
        "server_url": server_url,
        "api_key": api_key,
        "base_url": base_url,
        "agency": agency,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "thinking": thinking,
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
        """
        流式生成响应
        """

        response = ""
        try:
            # 更新数据状态
            data["status"] = "processing"
            redis_manager.set_input(msg_id, data)
            
            # 获取对应的模型实例
            model = get_model_instance(
                model_type=data["model_type"],
                model_name=data["model_name"],
                api_key=data["api_key"],
                base_url=data["base_url"],
                agency=data["agency"],
                temperature=data["temperature"],
                max_tokens=data["max_tokens"],
                thinking=data["thinking"],
                streaming=True,
            )

            # 前置上下文处理
            pre_context = []

            # 添加系统消息到上下文开始
            if data["system_message"]:
                pre_context.append(("system", data["system_message"]))

            # 添加 before_text 到上下文
            if data["before_text"]:
                # 这些模型不支持连续的消息，需要在每条消息之间插入确认消息
                models_need_confirmation = ["deepseek-reasoner", "deepseek-coder"]
                if data["model_name"] in models_need_confirmation:
                    for msg in data["before_text"]:
                        pre_context.append(msg)
                        pre_context.append(["assistant", "好的，明白了。"])
                else:
                    pre_context.extend(data["before_text"])

            # 获取现有上下文
            middle_context = redis_manager.get_context(data["context_key"])

            # 添加用户的新消息
            end_context = [("human", data["text"])]
            
            # 处理模型限制
            final_context = handle_context_limits(
                pre_context=pre_context,
                middle_context=middle_context,
                end_context=end_context,
                model_type=data["model_type"], 
                model_name=data["model_name"], 
                custom_limit=data["context_limit"]
            )

            # 检查上下文是否超限
            if not final_context:
                raise Exception("Context limit exceeded")

            # 缓存配置
            cache_interval = 0.1  # 缓存间隔
            last_cache_time = time.time()

            # 状态变量
            has_reasoning = False
            is_response = False

            # 开始请求流式响应
            for chunk in model.stream(final_context):
                if hasattr(chunk, 'content') and isinstance(chunk.content, list):
                    isContinue = True
                    if chunk.content:
                        chunk = SimpleNamespace(**chunk.content[0])
                        if hasattr(chunk, 'type'):
                            if chunk.type == 'thinking' and hasattr(chunk, 'thinking'):    
                                chunk = SimpleNamespace(reasoning_content=chunk.thinking)
                                isContinue = False
                            elif chunk.type == 'reasoning' and hasattr(chunk, 'reasoning'):    
                                chunk = SimpleNamespace(reasoning_content=chunk.reasoning)
                                isContinue = False
                            elif chunk.type == 'text' and hasattr(chunk, 'text'):
                                chunk = SimpleNamespace(content=chunk.text)
                                isContinue = False
                    if isContinue:
                        continue

                if hasattr(chunk, 'reasoning_content') and chunk.reasoning_content and not is_response:
                    if not has_reasoning:
                        response += "::: reasoning\n"
                        has_reasoning = True
                    response += chunk.reasoning_content
                    response = replace_think_content(response)
                    current_time = time.time()
                    if current_time - last_cache_time >= cache_interval:
                        redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)
                        last_cache_time = current_time  
                        
                if hasattr(chunk, 'content') and chunk.content:
                    if has_reasoning:
                        response += "\n:::\n\n"
                        has_reasoning = False
                    is_response = True
                    response += chunk.content
                    response = replace_think_content(response)
                    current_time = time.time()
                    if current_time - last_cache_time >= cache_interval:
                        redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)
                        last_cache_time = current_time                    

            # 更新上下文
            if response:    
                redis_manager.extend_contexts(data["context_key"], [
                    ("human", data["text"]),
                    ("assistant", remove_reasoning_content(response))
                ], data["model_type"], data["model_name"], data["context_limit"])

        except Exception as e:
            # 处理异常
            response = str(e)
        finally:
            # 确保状态总是被更新
            try:
                # 更新完整缓存
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
            except Exception as e:
                # 记录最终阶段的错误，但不影响主流程
                print(f"Error in cleanup: {str(e)}")

    def stream_producer():
        """
        流式生产者
        """

        # 生成消息 key
        msg_key = f"stream_msg_{msg_id}"
        
        # 如果是第一个请求，启动异步生产者
        if redis_manager.set_cache(msg_key, "", ex=STREAM_TIMEOUT, nx=True):
            thread_pool.submit(stream_generate, msg_id, msg_key, data, redis_manager)

        # 所有请求都作为消费者处理
        wait_start = time.time()
        last_response = ""
        sleep_interval = 0.1  # 睡眠间隔
        timeout_check_interval = 1.0  # 检查超时间隔
        last_timeout_check = time.time()
        check_status_interval = 0.2  # 检查完成状态间隔
        last_status_check = time.time()
        
        while True:
            current_time = time.time()
            
            # 检查超时
            if current_time - last_timeout_check >= timeout_check_interval:
                if current_time - wait_start > STREAM_TIMEOUT:
                    yield f"id: {msg_id}\nevent: replace\ndata: {json_content('Request timeout')}\n\n"
                    yield f"id: {msg_id}\nevent: done\ndata: {json_error('Timeout')}\n\n"
                    return
                last_timeout_check = current_time

            response = redis_manager.get_cache(msg_key)
            if response:
                if not last_response:
                    yield f"id: {msg_id}\nevent: replace\ndata: {json_content(response)}\n\n"
                else:
                    append_response = response[len(last_response):]
                    if append_response:
                        yield f"id: {msg_id}\nevent: append\ndata: {json_content(append_response)}\n\n"
                last_response = response

                # 只在有新响应时才检查状态
                if current_time - last_status_check >= check_status_interval:
                    current_data = redis_manager.get_input(msg_id)
                    if current_data and current_data["status"] == "finished":
                        yield f"id: {msg_id}\nevent: done\ndata: {json_empty()}\n\n"
                        return
                    last_status_check = current_time

            # 睡眠等待
            time.sleep(sleep_interval)

    # 返回流式响应
    return Response(
        stream_with_context(stream_producer()),
        mimetype='text/event-stream'
    )

# 直连模型：提交参数生成 stream_key，再用 SSE GET 获取响应
@app.route('/invoke/auth', methods=['POST', 'GET'])
def invoke_auth():
    """
    创建直连流请求并返回可供 SSE 连接的 stream_key。
    """
    payload = request.get_json(silent=True) or {}

    context_messages = parse_context(extract_param(request, payload, "context"))
    model_type = coerce_str(extract_param(request, payload, "model_type"), "openai") or "openai"
    model_name = coerce_str(extract_param(request, payload, "model_name"), "gpt-5-nano") or "gpt-5-nano"
    api_key = coerce_str(extract_param(request, payload, "api_key"))
    base_url = coerce_str(extract_param(request, payload, "base_url"))
    agency = coerce_str(extract_param(request, payload, "agency"))
    temperature = coerce_float(extract_param(request, payload, "temperature"), 0.7)
    max_tokens = coerce_int(extract_param(request, payload, "max_tokens"), 0)
    thinking = coerce_int(extract_param(request, payload, "thinking"), 0)
    if not api_key:
        return jsonify({"code": 400, "error": "api_key is required"}), 400
    if not context_messages:
        return jsonify({"code": 400, "error": "context is required"}), 400

    stream_key = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    storage_key = build_invoke_stream_key(stream_key)
    redis_manager.set_input(storage_key, {
        "final_context": [[role, content] for role, content in context_messages],
        "model_type": model_type,
        "model_name": model_name,
        "api_key": api_key,
        "base_url": base_url,
        "agency": agency,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "thinking": thinking,
        "status": "pending",
        "response": "",
        "created_at": int(time.time()),
    })

    return jsonify({
        "code": 200,
        "data": {
            "stream_key": stream_key,
            "stream_url": f"/invoke/stream/{stream_key}"
        }
    })

# 直连模型：通过 stream_key 建立 SSE 拉取 AI 输出
@app.route('/invoke/stream/<stream_key>', methods=['GET'])
def invoke_stream(stream_key):
    """
    使用 stream_key 建立直连 SSE 连接。
    """
    if not stream_key:
        return Response(
            "id: invoke\nevent: done\ndata: {}\n\n",
            mimetype='text/event-stream'
        )

    storage_key = build_invoke_stream_key(stream_key)
    data = redis_manager.get_input(storage_key)
    if not data:
        return Response(
            f"id: {stream_key}\nevent: done\ndata: {json_error('Invalid stream key')}\n\n",
            mimetype='text/event-stream'
        )

    if data.get("status") == "finished" and data.get("response") is not None:
        return Response(
            f"id: {stream_key}\nevent: replace\ndata: {json_content(data.get('response', ''))}\n\n"
            f"id: {stream_key}\nevent: done\ndata: {json_empty()}\n\n",
            mimetype='text/event-stream'
        )

    if data.get("status") == "processing":
        return Response(
            f"id: {stream_key}\nevent: done\ndata: {json_error('Stream is processing')}\n\n",
            mimetype='text/event-stream'
        )

    stored_context = data.get("final_context") or []
    final_context = parse_context(stored_context)
    if not final_context:
        return Response(
            f"id: {stream_key}\nevent: done\ndata: {json_error('No context found')}\n\n",
            mimetype='text/event-stream'
        )

    try:
        model = get_model_instance(
            model_type=data["model_type"],
            model_name=data["model_name"],
            api_key=data["api_key"],
            base_url=data["base_url"],
            agency=data["agency"],
            temperature=data["temperature"],
            max_tokens=data["max_tokens"],
            thinking=data["thinking"],
            streaming=True,
        )
    except Exception as exc:
        return Response(
            f"id: {stream_key}\nevent: done\ndata: {json_error(str(exc))}\n\n",
            mimetype='text/event-stream'
        )

    def stream_invoke_response():
        response_text = ""
        last_sent = ""
        has_reasoning = False
        is_response = False
        data["status"] = "processing"
        redis_manager.set_input(storage_key, data)
        try:
            for chunk in model.stream(final_context):
                if hasattr(chunk, "content") and isinstance(chunk.content, list):
                    should_continue = True
                    if chunk.content:
                        chunk = SimpleNamespace(**chunk.content[0])
                        if hasattr(chunk, "type"):
                            if chunk.type == "thinking" and hasattr(chunk, "thinking"):
                                chunk = SimpleNamespace(reasoning_content=chunk.thinking)
                                should_continue = False
                            elif chunk.type == "reasoning" and hasattr(chunk, "reasoning"):
                                chunk = SimpleNamespace(reasoning_content=chunk.reasoning)
                                should_continue = False
                            elif chunk.type == "text" and hasattr(chunk, "text"):
                                chunk = SimpleNamespace(content=chunk.text)
                                should_continue = False
                    if should_continue:
                        continue

                if hasattr(chunk, "reasoning_content") and chunk.reasoning_content and not is_response:
                    if not has_reasoning:
                        response_text += "::: reasoning\n"
                        has_reasoning = True
                    response_text += chunk.reasoning_content
                    response_text = replace_think_content(response_text)
                if hasattr(chunk, "content") and chunk.content:
                    if has_reasoning:
                        response_text += "\n:::\n\n"
                        has_reasoning = False
                    is_response = True
                    response_text += chunk.content
                    response_text = replace_think_content(response_text)

                if response_text != last_sent:
                    if last_sent and response_text.startswith(last_sent):
                        delta = response_text[len(last_sent):]
                        event_type = "append"
                    else:
                        delta = response_text
                        event_type = "replace"
                    if delta:
                        yield f"id: {stream_key}\nevent: {event_type}\ndata: {json_content(delta)}\n\n"
                    last_sent = response_text

            data["status"] = "finished"
            data["response"] = response_text
            redis_manager.set_input(storage_key, data)
            yield f"id: {stream_key}\nevent: done\ndata: {json_empty()}\n\n"
        except Exception as exc:
            data["status"] = "finished"
            data["response"] = response_text or str(exc)
            data["error"] = str(exc)
            redis_manager.set_input(storage_key, data)
            yield f"id: {stream_key}\nevent: done\ndata: {json_error(str(exc))}\n\n"

    return Response(
        stream_with_context(stream_invoke_response()),
        mimetype='text/event-stream'
    )

# 前端 UI 首页路由
@app.route('/')
def root():
    if not ui_assets_available():
        return jsonify({"message": "DooTask AI service"}), 200
    return send_from_directory(UI_DIST_PATH, 'index.html')

# 前端 UI 静态资源路由
@app.route('/ui/', defaults={'path': 'index.html'})
@app.route('/ui/<path:path>')
def ui_assets(path):
    if not ui_assets_available():
        return jsonify({"error": "UI assets not available"}), 404

    safe_path = path.lstrip("/")
    target = UI_DIST_PATH / safe_path
    if target.exists() and target.is_file():
        return send_from_directory(UI_DIST_PATH, safe_path)

    return send_from_directory(UI_DIST_PATH, 'index.html')

# 获取模型列表
@app.route('/models/list', methods=['GET'])
def models_list():
    model_type = request.args.get('type', '').strip()
    base_url = request.args.get('base_url', '').strip()
    key = request.args.get('key', '').strip()
    agency = request.args.get('agency', '').strip()

    try:
        data = get_models_list(
            model_type,
            base_url=base_url or None,
            key=key or None,
            agency=agency or None,
        )
    except ModelListError as exc:
        return jsonify({"code": 400, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        app.logger.exception("Failed to get model list")
        return jsonify({"code": 500, "error": "获取失败"}), 500

    return jsonify({"code": 200, "data": data})

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
