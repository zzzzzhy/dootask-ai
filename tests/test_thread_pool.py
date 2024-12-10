import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helper.thread_pool import DynamicThreadPoolExecutor
import time
import threading

def test_thread_pool_queue():
    # 创建一个最大线程数为3的线程池（为了便于测试）
    pool = DynamicThreadPoolExecutor(
        min_workers=2,
        max_workers=3,
        check_interval=5
    )

    def slow_task(task_id):
        """模拟一个耗时的任务"""
        print(f"Task {task_id} started, thread: {threading.current_thread().name}")
        time.sleep(2)  # 睡眠2秒模拟工作
        print(f"Task {task_id} completed, thread: {threading.current_thread().name}")
        return task_id

    # 提交6个任务（是最大线程数的2倍）
    futures = []
    for i in range(6):
        print(f"Submitting task {i}")
        future = pool.submit(slow_task, i)
        futures.append(future)

    # 等待所有任务完成
    for i, future in enumerate(futures):
        result = future.result()
        print(f"Got result from task {result}")

if __name__ == "__main__":
    test_thread_pool_queue()
