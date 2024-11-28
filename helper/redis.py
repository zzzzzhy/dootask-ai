import redis
import json
import os

class RedisManager:
    _instance = None
    _prefix = "dootask_ai:"  # 添加全局应用前缀

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
            cls._instance.client = redis.Redis(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=int(os.environ.get('REDIS_PORT', 6379)),
                db=int(os.environ.get('REDIS_DB', 0)),  # 添加数据库配置
                decode_responses=True
            )
        return cls._instance

    def _make_key(self, type_prefix, key):
        """生成带有应用前缀的完整键名"""
        return f"{self._prefix}{type_prefix}:{key}"

    def get_context(self, key):
        """从 Redis 获取上下文"""
        data = self.client.get(self._make_key("context", key))
        return json.loads(data) if data else None

    def set_context(self, key, value, model_type=None, model_name=None):
        """设置上下文到 Redis，根据模型限制截断内容"""
        # 定义模型的上下文限制（字符数）
        context_limits = {
            "openai": {
                "gpt-4": 24000,                # 约 6000 tokens
                "gpt-4-turbo": 128000,         # 约 32000 tokens
                "gpt-4o": 24000,               # 约 6000 tokens
                "gpt-4o-mini": 24000,          # 约 6000 tokens
                "gpt-3.5-turbo": 12000,        # 约 3000 tokens
                "gpt-3.5-turbo-16k": 65000,    # 约 16000 tokens
                "gpt-3.5-turbo-0125": 12000,   # 约 3000 tokens
                "gpt-3.5-turbo-1106": 12000,   # 约 3000 tokens
                "default": 12000               # 默认限制
            },
            "claude": {
                "claude-3-opus-20240229": 200000,   # 约 200k tokens
                "claude-3-sonnet-20240229": 200000, # 约 200k tokens
                "claude-2.1": 100000,              # 约 100k tokens
                "claude-2.0": 100000,              # 约 100k tokens
                "default": 100000                  # 默认限制
            },
            "gemini": {
                "gemini-pro": 100000,         # 约 100k tokens
                "gemini-pro-vision": 100000,  # 约 100k tokens
                "default": 100000
            },
            "zhipu": {
                "glm-4": 128000,       # 约 32k tokens
                "glm-4v": 128000,      # 约 32k tokens
                "glm-3-turbo": 32000,  # 约 8k tokens
                "default": 32000
            },
            "qwen": {
                "qwen-turbo": 32000,           # 约 8k tokens
                "qwen-plus": 32000,            # 约 8k tokens
                "qwen-max": 32000,             # 约 8k tokens
                "qwen-max-longcontext": 128000, # 约 32k tokens
                "default": 32000
            },
            "wenxin": {
                "ernie-bot-4": 32000,    # 约 8k tokens
                "ernie-bot-8k": 32000,   # 约 8k tokens
                "ernie-bot-turbo": 32000,# 约 8k tokens
                "ernie-bot": 32000,      # 约 8k tokens
                "default": 32000
            },
            "llama": {
                "llama-2-7b": 16000,   # 约 4k tokens
                "llama-2-13b": 16000,  # 约 4k tokens
                "llama-2-70b": 16000,  # 约 4k tokens
                "default": 16000
            },
            "cohere": {
                "command-r": 32000,    # 约 8k tokens
                "default": 32000
            },
            "eleutherai": {
                "gpt-neo": 8000,      # 约 2k tokens
                "gpt-j": 8000,        # 约 2k tokens
                "gpt-neox": 8000,     # 约 2k tokens
                "default": 8000
            },
            "mistral": {
                "mistral-7b": 32000,     # 约 8k tokens
                "mistral-mixtral": 32000, # 约 8k tokens
                "default": 32000
            },
            "default": 12000               # 全局默认限制
        }

        # 获取模型的上下文限制
        limit = context_limits.get("default")
        if model_type:
            model_limits = context_limits.get(model_type, {})
            limit = model_limits.get(model_name, model_limits.get("default", limit))

        # 如果内容超过限制，从开头截断
        if len(value) > limit:
            value = value[-limit:]

        # 保存到 Redis
        self.client.set(self._make_key("context", key), json.dumps(value))

    def get_input(self, key):
        """从 Redis 获取输入"""
        data = self.client.get(self._make_key("input", key))
        return json.loads(data) if data else None

    def set_input(self, key, value, expire=600):
        """设置输入到 Redis"""
        self.client.setex(self._make_key("input", key), expire, json.dumps(value))

    def delete_context(self, key):
        """删除上下文"""
        self.client.delete(self._make_key("context", key))

    def delete_input(self, key):
        """删除输入"""
        self.client.delete(self._make_key("input", key))

    def scan_inputs(self, match="input:*"):
        """扫描所有输入"""
        full_match = f"{self._prefix}{match}"
        prefix_len = len(self._prefix) + len("input:")
        for key in self.client.scan_iter(full_match):
            key_id = key[prefix_len:]  # 移除前缀部分
            data = self.get_input(key_id)
            if data:
                yield key_id, data

    def scan_contexts(self, match="context:*"):
        """扫描所有上下文"""
        full_match = f"{self._prefix}{match}"
        prefix_len = len(self._prefix) + len("context:")
        for key in self.client.scan_iter(full_match):
            key_id = key[prefix_len:]  # 移除前缀部分
            data = self.get_context(key_id)
            if data:
                yield key_id, data
