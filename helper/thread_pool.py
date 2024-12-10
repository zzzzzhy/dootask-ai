from concurrent.futures import ThreadPoolExecutor
import threading
import time
import psutil
import logging

class DynamicThreadPoolExecutor(ThreadPoolExecutor):
    """
    动态线程池执行器
    可以根据系统负载动态调整线程池大小
    """
    def __init__(self, min_workers=5, max_workers=20, cpu_threshold=70, memory_threshold=70,
                 check_interval=30, thread_name_prefix="dynamic_pool_"):
        """
        初始化动态线程池
        :param min_workers: 最小工作线程数
        :param max_workers: 最大工作线程数
        :param cpu_threshold: CPU使用率阈值（百分比）
        :param memory_threshold: 内存使用率阈值（百分比）
        :param check_interval: 检查间隔（秒）
        :param thread_name_prefix: 线程名称前缀
        """
        # 初始化日志
        self._logger = logging.getLogger("DynamicThreadPool")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self._logger.addHandler(handler)

        super().__init__(max_workers=min_workers, thread_name_prefix=thread_name_prefix)
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.check_interval = check_interval
        
        # 当前工作线程数
        self._current_workers = min_workers
        
        # 活跃任务计数
        self._active_tasks = 0
        self._active_tasks_lock = threading.Lock()
        
        try:
            # 测试psutil是否可用
            psutil.cpu_percent()
            self._has_psutil = True
        except Exception as e:
            self._logger.warning(f"psutil not available, falling back to task-based monitoring: {str(e)}")
            self._has_psutil = False
        
        # 启动监控线程
        self._monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self._monitor_thread.start()

    def submit(self, fn, *args, **kwargs):
        """
        提交任务到线程池
        """
        with self._active_tasks_lock:
            self._active_tasks += 1
            
        future = super().submit(fn, *args, **kwargs)
        future.add_done_callback(self._task_done_callback)
        return future

    def _task_done_callback(self, future):
        """
        任务完成回调
        """
        with self._active_tasks_lock:
            self._active_tasks -= 1

    def _monitor_resources(self):
        """
        监控系统资源使用情况
        """
        while True:
            try:
                # 获取当前活跃任务数
                with self._active_tasks_lock:
                    active_tasks = self._active_tasks

                if self._has_psutil:
                    # 获取系统资源使用情况
                    try:
                        cpu_percent = psutil.cpu_percent(interval=1)
                        memory_percent = psutil.virtual_memory().percent
                        
                        # 根据系统资源使用情况调整线程池大小
                        if cpu_percent > self.cpu_threshold or memory_percent > self.memory_threshold:
                            # 系统负载高，减少线程数
                            if self._current_workers > self.min_workers:
                                new_workers = max(self.min_workers, self._current_workers - 2)
                                self._adjust_pool_size(new_workers)
                                self._logger.info(f"High system load detected (CPU: {cpu_percent}%, MEM: {memory_percent}%), "
                                                f"reducing workers to {new_workers}")
                    except Exception as e:
                        self._logger.error(f"Error getting system metrics: {str(e)}")
                
                # 根据任务数调整线程数
                if active_tasks > self._current_workers * 0.8:  # 任务数超过80%时扩容
                    new_workers = min(self.max_workers, self._current_workers + 2)
                    self._adjust_pool_size(new_workers)
                    self._logger.info(f"High task load detected (Active: {active_tasks}), "
                                    f"increasing workers to {new_workers}")
                elif active_tasks < self._current_workers * 0.2:  # 任务数少于20%时缩容
                    if self._current_workers > self.min_workers:
                        new_workers = max(self.min_workers, self._current_workers - 1)
                        self._adjust_pool_size(new_workers)
                        self._logger.info(f"Low task load detected (Active: {active_tasks}), "
                                        f"reducing workers to {new_workers}")
                
                # 记录当前状态
                status_msg = f"Pool status - Workers: {self._current_workers}, Active tasks: {active_tasks}"
                if self._has_psutil:
                    status_msg += f", CPU: {cpu_percent}%, MEM: {memory_percent}%"
                self._logger.debug(status_msg)
                
            except Exception as e:
                self._logger.error(f"Error in monitor thread: {str(e)}")
            
            time.sleep(self.check_interval)

    def _adjust_pool_size(self, new_size):
        """
        调整线程池大小
        """
        if new_size == self._current_workers:
            return
            
        self._max_workers = new_size
        self._current_workers = new_size
