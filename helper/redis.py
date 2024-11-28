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

    def set_context(self, key, value, expire=3600):
        """设置上下文到 Redis"""
        self.client.setex(self._make_key("context", key), expire, json.dumps(value))

    def get_input(self, key):
        """从 Redis 获取输入"""
        data = self.client.get(self._make_key("input", key))
        return json.loads(data) if data else None

    def set_input(self, key, value, expire=3600):
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

    def cleanup_expired_data(self, max_age_seconds=600):
        """清理过期数据"""
        for key in self.client.scan_iter(f"{self._prefix}*"):
            if not self.client.ttl(key):  # 如果键没有过期时间
                self.client.delete(key)
