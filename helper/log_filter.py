import logging

class HealthCheckFilter(logging.Filter):
    """
    日志过滤器，用于过滤掉健康检查请求的日志
    """
    def filter(self, record):
        return 'GET /health' not in record.getMessage()
