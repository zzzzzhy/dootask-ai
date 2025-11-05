from types import SimpleNamespace
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException, File, UploadFile, Header
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.params import Form
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from helper.utils import convert_message_content_to_string, dict_to_message, get_model_instance, get_swagger_ui, json_empty, json_error, json_content, message_to_dict, remove_tool_calls, replace_think_content, remove_reasoning_content, process_html_content
from helper.request import RequestClient
from helper.redis import handle_context_limits, RedisManager
# from helper.thread_pool import DynamicThreadPoolExecutor
from helper.config import SERVER_PORT, CLEAR_COMMANDS, STREAM_TIMEOUT, END_CONVERSATION_MARK
import json
import time
import random
import string
# from typing import Optional
# from pydantic import BaseModel
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient
import asyncio
from exceptiongroup import ExceptionGroup
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, AIMessageChunk

from langchain.agents import create_agent 
from helper.models import ModelListError, get_models_list
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # 输出到控制台
    ]
)
logger = logging.getLogger("ai")


UI_DIST_PATH = Path(__file__).resolve().parent / "static" / "ui"


def ui_assets_available() -> bool:
    return UI_DIST_PATH.exists() and UI_DIST_PATH.is_dir()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    try:
        redis_manager = RedisManager()
        logger.info("✅ 初始化成功")
        app.state.redis_manager = redis_manager
    except Exception as e:
        logger.info(f"❌ 初始化失败: {str(e)}")
    yield
    # 关闭时清理
    logger.info("🛑 AI服务正在关闭...")

app = FastAPI(
    title="AI Chat API",
    description="基于AI的聊天服务API",
    version="1.0.0",
    lifespan=lifespan
)
# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化线程池
# thread_pool = DynamicThreadPoolExecutor(
#     min_workers=5,
#     max_workers=50,
#     thread_name_prefix="ai_stream_"
# )




@app.api_route("/chat", methods=["GET", "POST"])
async def chat(request: Request):
    # 智能参数提取
    if request.method == "GET":
        params = dict(request.query_params)
    else:
        form_data = await request.form()
        params = dict(form_data)

    # 参数配置
    defaults = {
        'dialog_id': 0,
        'msg_id': 0,
        'msg_uid': 0,
        'mention': 0,
        'bot_uid': 0,
        'extras': '{}'
    }
    
    # 应用默认值和类型转换
    for key, default_value in defaults.items():
        value = params.get(key, default_value)
        if isinstance(default_value, int):
            try:
                params[key] = int(value)
            except (ValueError, TypeError):
                params[key] = default_value
        else:
            params[key] = value
    
    text = params.get("text")
    token = params.get("token")
    version = params.get("version")
    dialog_id, msg_id, msg_uid, mention, bot_uid, extras = (
        params[k] for k in ["dialog_id", "msg_id", "msg_uid", "mention", "bot_uid", "extras"]
    )

    # 检查必要参数是否为空
    if not all([text, token, dialog_id, msg_uid, bot_uid, version]):
        return JSONResponse(content={"code": 400, "error": "Parameter error"}, status_code=200)

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
        return JSONResponse(content={"code": 400, "error": "Invalid extras parameter"}, status_code=200)

    # 检查 extras 解析后的必要参数是否为空
    if not all([model_type, model_name, server_url, api_key]):
        return JSONResponse(content={"code": 400, "error": "Parameter error in extras"}, status_code=200)

    # 上下文 before_text 处理
    if not before_text:
        before_text = []
    elif isinstance(before_text, str):
        before_text = [HumanMessage(content=before_text)]
    elif isinstance(before_text, list):
        if before_text and isinstance(before_text[0], str):
            before_text = [HumanMessage(content=text) for text in before_text]

    # 创建请求客户端
    request_client = RequestClient(server_url, version, token, dialog_id)

    # 定义上下文键
    context_key = f"{model_type}_{model_name}_{dialog_id}_{context_key}"
    
    # 如果是清空上下文的命令
    if text in CLEAR_COMMANDS:
        await app.state.redis_manager.delete_context(context_key)
        # 调用回调
        asyncio.ensure_future(request_client.call({
            "notice": "上下文已清空",
            "silence": "yes",
            "source": "ai",
        }, action='notice'))
        return JSONResponse(content={"code": 200, "data": {"desc": "Context cleared"}}, status_code=200)

    # 如果需要在请求前清空上下文
    if before_clear:
        await app.state.redis_manager.delete_context(context_key)

    # 创建消息
    send_id = await request_client.call({
        "text": '...',
        "text_type": "md",
        "silence": "yes",
        "reply_id": msg_id,
        "reply_check": "yes",
    })
    
    if not send_id:
        return JSONResponse(content={"code": 400, "error": "Send message failed"}, status_code=200)

    # 处理HTML内容（图片标签）
    text = process_html_content(text)

    # 生成随机8位字符串
    stream_key = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 将输入存储到 Redis
    await app.state.redis_manager.set_input(send_id, {
        "text": text,
        "token": token,
        "dialog_id": dialog_id,
        "version": version,
        "msg_user_token": params.get("msg_user[token]"),
        "before_text": before_text,
        # "use_dootaskmcp": True,
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
    asyncio.create_task(request_client.call({
        "userid": msg_uid,
        "stream_url": f"/stream/{send_id}/{stream_key}",
        "source": "ai",
    }, action='stream'))

    # 返回成功响应
    return JSONResponse(content={"code": 200, "data": {"id": send_id, "key": stream_key}}, status_code=200)

# 处理流式响应
@app.get('/stream/{msg_id}/{stream_key}')
async def stream(msg_id: str, stream_key: str, host: str = Header(..., alias="Host")):
    if not stream_key:
        async def error_stream():
            yield f"id: {msg_id}\nevent: done\ndata: {json_error('No key')}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type='text/event-stream'
        )

    # 检查 msg_id 是否在 Redis 中
    data = await app.state.redis_manager.get_input(msg_id)
    
    if not data:
        async def error_stream():
            yield f"id: {msg_id}\nevent: done\ndata: {json_error('No such ID')}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type='text/event-stream'
        )

    # 检查 stream_key 是否正确
    if stream_key != data["stream_key"]:
        async def error_stream():
            yield f"id: {msg_id}\nevent: done\ndata: {json_error('Invalid key')}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type='text/event-stream'
        )

    # 如果 status 为 finished，直接返回
    if data["status"] == "finished":
        async def finished_stream():
            yield f"""
            id: {msg_id}\nevent: replace\ndata: {json_content(data['response'])}\n\n
            id: {msg_id}\nevent: done\ndata: {json_empty()}\n\n
            """
        return StreamingResponse(
            finished_stream(),
            media_type='text/event-stream'
        )
    
    client = MultiServerMCPClient(
        {
            "dootask-task": {
                "url": f"https://{host}/apps/mcp_server/mcp",
                "transport": "streamable_http",
                "headers": {
                    "token": data.get("msg_user_token","unknown")
                },
            }
        }
    )
    tools = await client.get_tools()
    async def stream_generate(msg_id, msg_key, data, redis_manager):
        """
        流式生成响应
        """

        response = ""
        try:
            # 更新数据状态
            data["status"] = "processing"
            await redis_manager.set_input(msg_id, data)
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
                pre_context.append(SystemMessage(content=data["system_message"]))

            # 添加 before_text 到上下文
            if data["before_text"]:
                # 这些模型不支持连续的消息，需要在每条消息之间插入确认消息
                models_need_confirmation = ["deepseek-reasoner", "deepseek-coder"]
                if data["model_name"] in models_need_confirmation:
                    for msg in data["before_text"]:
                        pre_context.append(msg)
                        pre_context.append(AIMessage(content="好的，明白了。"))
                else:
                    pre_context.extend(data["before_text"])

            # 获取现有上下文
            middle_context = await redis_manager.get_context(data["context_key"])

            middle_messages = []
            if middle_context:
                middle_messages = [dict_to_message(msg_dict) for msg_dict in middle_context]
            # 添加用户的新消息
            end_context = [HumanMessage(content=data["text"])]
            # 处理模型限制
            final_context = handle_context_limits(
                pre_context=pre_context,
                middle_context=middle_messages,
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
            
            agent = create_agent(model, tools)
            
            # 开始请求流式响应
            async for chunk in agent.astream({"messages": final_context}, stream_mode="messages"):
                print(chunk)
                msg, metadata = chunk
                if "skip_stream" in metadata.get("tags", []):
                    continue
                # For some reason, astream("messages") causes non-LLM nodes to send extra messages.
                # Drop them.
                if not isinstance(msg, AIMessageChunk):
                    continue

                if hasattr(msg, 'content') and isinstance(msg.content, list):
                    isContinue = True
                    if msg.content:
                        chunk = SimpleNamespace(**msg.content[0])
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

                if hasattr(msg, 'reasoning_content') and msg.reasoning_content and not is_response:
                    if not has_reasoning:
                        response += "::: reasoning\n"
                        has_reasoning = True
                    response += convert_message_content_to_string(msg.reasoning_content)
                    response = replace_think_content(response)
                    current_time = time.time()
                    print(current_time,last_cache_time)
                    if current_time - last_cache_time >= cache_interval:
                        await redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)
                        last_cache_time = current_time  
                        
                if hasattr(msg, 'content') and msg.content:
                    if has_reasoning:
                        response += "\n:::\n\n"
                        has_reasoning = False
                    is_response = True
                    response += convert_message_content_to_string(remove_tool_calls(msg.content))
                    response = replace_think_content(response)
                    current_time = time.time()
                    if current_time - last_cache_time >= cache_interval:
                        await redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)
                        last_cache_time = current_time                    

            # 更新上下文
            if response:    
                await redis_manager.extend_contexts(data["context_key"], [
                    message_to_dict(HumanMessage(content=data["text"])),
                    message_to_dict(AIMessage(content=remove_reasoning_content(response)))
                ], data["model_type"], data["model_name"], data["context_limit"])

        except Exception as e:
            # 处理异常
            logger.exception(e)
            response = str(e)
        finally:
            # 确保状态总是被更新
            try:
                # 更新完整缓存
                await redis_manager.set_cache(msg_key, response, ex=STREAM_TIMEOUT)

                # 更新数据状态
                data["status"] = "finished"
                data["response"] = response
                await redis_manager.set_input(msg_id, data)

                # 创建请求客户端
                request_client = RequestClient(
                    server_url=data["server_url"], 
                    version=data["version"], 
                    token=data["token"], 
                    dialog_id=data["dialog_id"]
                )

                # 更新完整消息
                asyncio.ensure_future(request_client.call({
                    "update_id": msg_id,
                    "update_mark": "no",
                    "text": response,
                    "text_type": "md",
                    "silence": "yes"
                }))
            except Exception as e:
                # 记录最终阶段的错误，但不影响主流程
                print(f"Error in cleanup: {str(e)}")

    async def stream_producer():
        """
        流式生产者
        """

        # 生成消息 key
        msg_key = f"stream_msg_{msg_id}"
        producer_task = None
        
        # 如果是第一个请求，启动异步生产者
        if await app.state.redis_manager.set_cache(msg_key, "", ex=STREAM_TIMEOUT, nx=True):
            # thread_pool.submit(stream_generate, msg_id, msg_key, data, app.state.redis_manager)
            producer_task = asyncio.create_task(stream_generate(msg_id, msg_key, data, app.state.redis_manager))

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
                    if producer_task:
                        producer_task.cancel()
                    return
                last_timeout_check = current_time

            response = await app.state.redis_manager.get_cache(msg_key)
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
                    current_data = await app.state.redis_manager.get_input(msg_id)
                    if current_data and current_data["status"] == "finished":
                        yield f"id: {msg_id}\nevent: done\ndata: {json_empty()}\n\n"
                        if producer_task:
                            producer_task.cancel()
                        return
                    last_status_check = current_time

            # 睡眠等待
            await asyncio.sleep(sleep_interval)
            # time.sleep(sleep_interval)

    # 返回流式响应
    return StreamingResponse(
        stream_producer(),
        media_type='text/event-stream'
    )

def parse_langchain_response(messages: list) -> dict:
    """
    正确处理LangChain消息对象的解析函数
    """
    result = {
        "final_response": "",
        "metadata": {}
    }
    
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.response_metadata.get("finish_reason") == "stop":
            # print("-------------")
            result["final_response"] = msg.content
            result["metadata"].update({
                "model_name": msg.response_metadata.get("model_name"),
                "prompt_tokens": msg.response_metadata.get("token_usage",{}).get("prompt_tokens"),
                "total_tokens": msg.response_metadata.get("token_usage",{}).get("total_tokens")
            })
    return result

# 处理直接请求
@app.post('/invoke')
async def invoke(request: Request):
    if request.method == "GET":
        params = dict(request.query_params)
    else:
        form_data = await request.form()
        params = dict(form_data)
    defaults = {
        'model_type': 'openai',
        'model_name': 'gpt-5-chat',
        'max_tokens': 0,
        'temperature': 0.7,
        'thinking': 0,
        'context_limit': 0,
    }
    
    # 应用默认值和类型转换
    for key, default_value in defaults.items():
        value = params.get(key, default_value)
        if isinstance(default_value, int):
            try:
                params[key] = int(value)
            except (ValueError, TypeError):
                params[key] = default_value
        else:
            params[key] = value

    text = params.get("text")
    system_message = params.get('system_message')
    api_key = params.get('api_key')
    base_url = params.get('base_url')
    agency = params.get('agency')
    before_text = params.get('before_text')
    context_key = params.get('context_key')
    model_type, model_name, max_tokens, temperature, thinking, context_limit = (
        params[k] for k in defaults.keys()
    )
    
    # 检查必要参数是否为空
    if not all([text, api_key]):
        return JSONResponse(content={"code": 400, "error": "Parameter error"}, status_code=200)

    # 上下文 before_text 处理
    if not before_text:
        before_text = []
    elif isinstance(before_text, str):
        before_text = [HumanMessage(content=before_text)]
    elif isinstance(before_text, list):
        if before_text and isinstance(before_text[0], str):
            before_text = [HumanMessage(content=text) for text in before_text]

    # 获取模型实例
    model = get_model_instance(
        model_type=model_type,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        agency=agency,
        temperature=temperature,
        max_tokens=max_tokens,
        thinking=thinking,
        streaming=False,
    )

    # 前置上下文
    pre_context = []

    # 添加系统消息到上下文开始
    if system_message:
        pre_context.append(SystemMessage(content=system_message))

    # 添加 before_text 到上下文
    if before_text:
        # 优化处理不同模型的上下文添加逻辑
        models_need_confirmation = {"deepseek-reasoner", "deepseek-coder"}
        for item in before_text:
            pre_context.append(item)
            if model_name in models_need_confirmation:
                pre_context.append(AIMessage(content="好的，明白了。"))

    # 获取现有上下文
    middle_context = await app.state.redis_manager.get_context(f"invoke_{context_key}")

    # 添加用户的新消息
    end_context = [HumanMessage(content=text)]

    # 处理模型限制
    final_context = handle_context_limits(
        pre_context = pre_context,
        middle_context = middle_context,
        end_context = end_context,
        model_type=model_type, 
        model_name=model_name, 
        custom_limit=context_limit
    )
    host = request.headers.get("Host")
    client = MultiServerMCPClient(
        {
            "dootask-task": {
                "url": f"https://{host}/apps/mcp_server/mcp",
                "transport": "streamable_http",
                "headers": {
                    "token": params.get("msg_user[token]")
                },
            }
        }
    )
    # 开始请求直接响应
    try:
        tools = await client.get_tools()
        agent = create_agent(model, tools)
        response = await agent.ainvoke(final_context)
        # response = model.invoke(final_context)
        result = parse_langchain_response(response["messages"])
        resContent = replace_think_content(result["final_response"])
        if context_key:
            await app.state.redis_manager.extend_contexts(f"invoke_{context_key}", [
                HumanMessage(content=text),
                AIMessage(content=remove_reasoning_content(resContent))
            ], model_type, model_name, context_limit)
        usage_metadata = {}
        if "usage_metadata" in response:
            usage_metadata = response["usage_metadata"]
        elif result["metadata"]:
            usage_metadata = {
                "total_tokens": result["metadata"].get("total_tokens", 0),
                "input_tokens": result["metadata"].get("prompt_tokens", 0),
                "output_tokens": result["metadata"].get("total_tokens", 0) - result["metadata"].get("prompt_tokens", 0)
            }
        return JSONResponse(
            content={
                "code": 200, 
                "data": {
                    "content": resContent,
                    "usage": {
                        "total_tokens": usage_metadata.get("total_tokens", 0),
                        "prompt_tokens": usage_metadata.get("input_tokens", 0),
                        "completion_tokens": usage_metadata.get("output_tokens", 0)
                    }
                }
            },
            status_code=200
        )
    except ExceptionGroup as eg:
        # 处理异常组中的每个异常
        for exc in eg.exceptions:
            if isinstance(exc, httpx.ConnectError):
                raise HTTPException(
                    status_code=503,
                    detail="后端服务不可用"
                )
        raise HTTPException(
            status_code=500,
            detail="处理请求时发生多个错误"
        )
    except Exception as e:
        return JSONResponse(content={"code": 500, "error": str(e)}, status_code=200)

# 前端 UI 首页路由
@app.get('/')
async def root():
    if not ui_assets_available():
        return JSONResponse(content={"message": "DooTask AI service"}, status_code=200)
    return FileResponse(UI_DIST_PATH / 'index.html')

# 前端 UI 静态资源路由
@app.get('/ui/')
@app.get('/ui/{path:path}')
async def ui_assets(path: str = 'index.html'):
    if not ui_assets_available():
        return JSONResponse(content={"error": "UI assets not available"}, status_code=404)

    safe_path = path.lstrip("/")
    target = UI_DIST_PATH / safe_path
    if target.exists() and target.is_file():
        return FileResponse(target)

    return FileResponse(UI_DIST_PATH / 'index.html')

# 获取模型列表
@app.get('/models/list')
async def models_list(
    type: str = '',
    base_url: str = '',
    key: str = '',
    agency: str = ''
):
    model_type = type.strip()
    base_url = base_url.strip()
    key = key.strip()
    agency = agency.strip()

    try:
        data = get_models_list(
            model_type,
            base_url=base_url or None,
            key=key or None,
            agency=agency or None,
        )
    except ModelListError as exc:
        return JSONResponse(content={"code": 400, "error": str(exc)}, status_code=400)
    except Exception as exc:  # pragma: no cover - defensive logging
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to get model list")
        return JSONResponse(content={"code": 500, "error": "获取失败"}, status_code=500)

    return JSONResponse(content={"code": 200, "data": data}, status_code=200)

# 健康检查
@app.get('/health')
async def health():
    try:

        await app.state.redis_manager.client.ping()
        return JSONResponse(content={"status": "healthy", "redis": "connected"}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"status": "unhealthy", "error": str(e)}, status_code=500)


# Swagger UI route
@app.get('/swagger')
async def swagger():
    return get_swagger_ui()

# Swagger YAML route
@app.get('/swagger.yaml')
async def swagger_yaml():
    static_file_path = Path(__file__).resolve().parent / "static" / "swagger.yaml"
    return FileResponse(static_file_path)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host='0.0.0.0', port=8080,reload=True)
