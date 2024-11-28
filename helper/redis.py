import redis
import json
import os

class RedisManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
            cls._instance.client = redis.Redis(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=int(os.environ.get('REDIS_PORT', 6379)),
                db=0,
                decode_responses=True
            )
        return cls._instance

    def get_context(self, key):
        """从 Redis 获取上下文"""
        data = self.client.get(f"context:{key}")
        return json.loads(data) if data else None

    def set_context(self, key, value, expire=3600):
        """设置上下文到 Redis"""
        self.client.setex(f"context:{key}", expire, json.dumps(value))

    def get_input(self, key):
        """从 Redis 获取输入"""
        data = self.client.get(f"input:{key}")
        return json.loads(data) if data else None

    def set_input(self, key, value, expire=3600):
        """设置输入到 Redis"""
        self.client.setex(f"input:{key}", expire, json.dumps(value))

    def delete_context(self, key):
        """删除上下文"""
        self.client.delete(f"context:{key}")

    def delete_input(self, key):
        """删除输入"""
        self.client.delete(f"input:{key}")

    def scan_inputs(self, match="input:*"):
        """扫描所有输入"""
        for key in self.client.scan_iter(match):
            key_id = key.split(":", 1)[1]
            data = self.get_input(key_id)
            if data:
                yield key_id, data

    def scan_contexts(self, match="context:*"):
        """扫描所有上下文"""
        for key in self.client.scan_iter(match):
            key_id = key.split(":", 1)[1]
            data = self.get_context(key_id)
            if data:
                yield key_id, data

    def cleanup_expired_data(self, timeout=600):
        """清理超时数据"""
        import time
        current_time = int(time.time())

        # 清理超时的输入数据
        for key_id, data in self.scan_inputs():
            if current_time - data.get("created_at", 0) > timeout:
                self.delete_input(key_id)

        # 清理超时的上下文数据
        for key_id, data in self.scan_contexts():
            if isinstance(data, str):
                # 如果是字符串格式的上下文，检查最后修改时间
                if current_time - self.client.ttl(f"context:{key_id}") > timeout:
                    self.delete_context(key_id)
            elif isinstance(data, dict) and current_time - data.get("timestamp", 0) > timeout:
                # 如果是字典格式的上下文，检查timestamp
                self.delete_context(key_id)
