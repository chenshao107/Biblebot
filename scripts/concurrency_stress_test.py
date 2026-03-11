#!/usr/bin/env python3
"""
并发压测脚本 - 测试 Agent API 的并发处理能力

使用方法:
    python scripts/concurrency_stress_test.py [选项]

示例:
    # 基础测试（10并发，每个请求1次）
    python scripts/concurrency_stress_test.py
    
    # 高并发测试
    python scripts/concurrency_stress_test.py --concurrency 20 --requests-per-client 5
    
    # 只测试非流式接口
    python scripts/concurrency_stress_test.py --endpoint agent --no-stream
    
    # 长时间压力测试
    python scripts/concurrency_stress_test.py --concurrency 50 --requests-per-client 10 --duration 300
"""

import asyncio
import aiohttp
import time
import json
import argparse
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import sys


@dataclass
class RequestResult:
    """单个请求的结果"""
    client_id: int
    request_id: int
    success: bool
    latency: float  # 秒
    start_time: float
    end_time: float
    error_message: Optional[str] = None
    response_length: int = 0


@dataclass
class TestSummary:
    """测试汇总结果"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_time: float = 0.0
    latencies: List[float] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0.0
    
    @property
    def min_latency(self) -> float:
        return min(self.latencies) if self.latencies else 0.0
    
    @property
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0.0
    
    @property
    def p50_latency(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0.0
    
    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]
    
    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]
    
    @property
    def requests_per_second(self) -> float:
        if self.total_time == 0:
            return 0.0
        return self.total_requests / self.total_time


class ConcurrencyTester:
    """并发测试器"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        concurrency: int = 10,
        requests_per_client: int = 1,
        duration: Optional[int] = None,
        query: str = "什么是CMake？",
        stream: bool = True,
        endpoint: str = "agent"
    ):
        self.base_url = base_url.rstrip('/')
        self.concurrency = concurrency
        self.requests_per_client = requests_per_client
        self.duration = duration
        self.query = query
        self.stream = stream
        self.endpoint = endpoint
        self.results: List[RequestResult] = []
        self.lock = asyncio.Lock()
        
    def get_url(self) -> str:
        """获取请求URL"""
        if self.endpoint == "agent":
            return f"{self.base_url}/agent"
        elif self.endpoint == "chat":
            return f"{self.base_url}/v1/chat/completions"
        else:
            raise ValueError(f"Unknown endpoint: {self.endpoint}")
    
    def get_payload(self) -> Dict:
        """获取请求体"""
        if self.endpoint == "agent":
            return {
                "query": self.query,
                "stream": self.stream
            }
        elif self.endpoint == "chat":
            return {
                "model": "biblebot"
                "messages": [{"role": "user", "content": self.query}],
                "stream": self.stream
            }
    
    async def send_request(
        self,
        session: aiohttp.ClientSession,
        client_id: int,
        request_id: int
    ) -> RequestResult:
        """发送单个请求"""
        url = self.get_url()
        payload = self.get_payload()
        
        start_time = time.time()
        
        try:
            if self.stream:
                # 流式请求
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        end_time = time.time()
                        return RequestResult(
                            client_id=client_id,
                            request_id=request_id,
                            success=False,
                            latency=end_time - start_time,
                            start_time=start_time,
                            end_time=end_time,
                            error_message=f"HTTP {response.status}: {error_text[:200]}"
                        )
                    
                    # 读取所有流式数据
                    content_length = 0
                    async for line in response.content:
                        content_length += len(line)
                    
                    end_time = time.time()
                    return RequestResult(
                        client_id=client_id,
                        request_id=request_id,
                        success=True,
                        latency=end_time - start_time,
                        start_time=start_time,
                        end_time=end_time,
                        response_length=content_length
                    )
            else:
                # 非流式请求
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    data = await response.text()
                    end_time = time.time()
                    
                    if response.status == 200:
                        return RequestResult(
                            client_id=client_id,
                            request_id=request_id,
                            success=True,
                            latency=end_time - start_time,
                            start_time=start_time,
                            end_time=end_time,
                            response_length=len(data)
                        )
                    else:
                        return RequestResult(
                            client_id=client_id,
                            request_id=request_id,
                            success=False,
                            latency=end_time - start_time,
                            start_time=start_time,
                            end_time=end_time,
                            error_message=f"HTTP {response.status}: {data[:200]}"
                        )
                        
        except asyncio.TimeoutError:
            end_time = time.time()
            return RequestResult(
                client_id=client_id,
                request_id=request_id,
                success=False,
                latency=end_time - start_time,
                start_time=start_time,
                end_time=end_time,
                error_message="Request timeout"
            )
        except Exception as e:
            end_time = time.time()
            return RequestResult(
                client_id=client_id,
                request_id=request_id,
                success=False,
                latency=end_time - start_time,
                start_time=start_time,
                end_time=end_time,
                error_message=str(e)[:200]
            )
    
    async def client_worker(
        self,
        session: aiohttp.ClientSession,
        client_id: int,
        semaphore: asyncio.Semaphore
    ):
        """客户端工作协程"""
        async with semaphore:
            for i in range(self.requests_per_client):
                result = await self.send_request(session, client_id, i)
                async with self.lock:
                    self.results.append(result)
                
                # 打印进度
                if result.success:
                    print(f"  [Client {client_id:3d}] Request {i+1}/{self.requests_per_client} - OK ({result.latency:.2f}s)")
                else:
                    print(f"  [Client {client_id:3d}] Request {i+1}/{self.requests_per_client} - FAILED: {result.error_message[:50]}")
                
                # 检查是否达到测试时长限制
                if self.duration and (time.time() - self.start_time) >= self.duration:
                    break
    
    async def run_test(self) -> TestSummary:
        """运行测试"""
        self.start_time = time.time()
        self.results = []
        
        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(self.concurrency)
        
        print(f"\n{'='*60}")
        print(f"开始并发压测")
        print(f"{'='*60}")
        print(f"目标URL: {self.get_url()}")
        print(f"并发数: {self.concurrency}")
        print(f"每客户端请求数: {self.requests_per_client}")
        print(f"总请求数: {self.concurrency * self.requests_per_client}")
        print(f"流式模式: {self.stream}")
        print(f"测试查询: {self.query[:50]}...")
        print(f"{'='*60}\n")
        
        async with aiohttp.ClientSession() as session:
            # 创建所有客户端任务
            tasks = [
                self.client_worker(session, i, semaphore)
                for i in range(self.concurrency)
            ]
            
            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        
        # 生成汇总
        summary = TestSummary(
            total_requests=len(self.results),
            successful_requests=sum(1 for r in self.results if r.success),
            failed_requests=sum(1 for r in self.results if not r.success),
            total_time=end_time - self.start_time,
            latencies=[r.latency for r in self.results if r.success]
        )
        
        return summary
    
    def print_report(self, summary: TestSummary):
        """打印测试报告"""
        print(f"\n{'='*60}")
        print(f"测试结果报告")
        print(f"{'='*60}")
        print(f"\n📊 基本统计:")
        print(f"  总请求数: {summary.total_requests}")
        print(f"  成功请求: {summary.successful_requests}")
        print(f"  失败请求: {summary.failed_requests}")
        print(f"  成功率: {summary.success_rate:.2f}%")
        print(f"  总耗时: {summary.total_time:.2f}s")
        print(f"  QPS (每秒请求数): {summary.requests_per_second:.2f}")
        
        if summary.latencies:
            print(f"\n⏱️  延迟统计 (秒):")
            print(f"  平均延迟: {summary.avg_latency:.2f}s")
            print(f"  最小延迟: {summary.min_latency:.2f}s")
            print(f"  最大延迟: {summary.max_latency:.2f}s")
            print(f"  P50延迟: {summary.p50_latency:.2f}s")
            print(f"  P95延迟: {summary.p95_latency:.2f}s")
            print(f"  P99延迟: {summary.p99_latency:.2f}s")
        
        # 显示失败详情
        failed_results = [r for r in self.results if not r.success]
        if failed_results:
            print(f"\n❌ 失败请求详情 (前10个):")
            for r in failed_results[:10]:
                print(f"  Client {r.client_id}, Request {r.request_id}: {r.error_message}")
        
        print(f"\n{'='*60}\n")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Agent API 并发压测脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础测试
  python concurrency_stress_test.py
  
  # 高并发测试 (20并发，每客户端5次请求)
  python concurrency_stress_test.py -c 20 -n 5
  
  # 只测试非流式 agent 接口
  python concurrency_stress_test.py --endpoint agent --no-stream
  
  # 测试 OpenAI 兼容接口
  python concurrency_stress_test.py --endpoint chat
  
  # 长时间压力测试 (持续300秒)
  python concurrency_stress_test.py -c 50 -n 10 -d 300
        """
    )
    
    parser.add_argument(
        "-u", "--url",
        default="http://localhost:8000",
        help="API 基础 URL (默认: http://localhost:8000)"
    )
    
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=10,
        help="并发客户端数量 (默认: 10)"
    )
    
    parser.add_argument(
        "-n", "--requests-per-client",
        type=int,
        default=1,
        help="每个客户端发送的请求数 (默认: 1)"
    )
    
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=None,
        help="测试持续时间(秒)，到达时间后停止新请求"
    )
    
    parser.add_argument(
        "-q", "--query",
        default="什么是CMake？",
        help="测试查询内容 (默认: '什么是CMake？')"
    )
    
    parser.add_argument(
        "--endpoint",
        choices=["agent", "chat"],
        default="agent",
        help="测试的端点: agent 或 chat (默认: agent)"
    )
    
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="使用非流式模式 (默认使用流式)"
    )
    
    parser.add_argument(
        "--compare",
        action="store_true",
        help="对比流式和非流式模式的性能"
    )
    
    return parser.parse_args()


async def main():
    args = parse_args()
    
    if args.compare:
        # 对比模式：分别测试流式和非流式
        print("\n" + "="*60)
        print("对比测试模式：流式 vs 非流式")
        print("="*60)
        
        # 测试流式
        print("\n>>> 测试流式模式 <<<")
        tester_stream = ConcurrencyTester(
            base_url=args.url,
            concurrency=args.concurrency,
            requests_per_client=args.requests_per_client,
            duration=args.duration,
            query=args.query,
            stream=True,
            endpoint=args.endpoint
        )
        summary_stream = await tester_stream.run_test()
        tester_stream.print_report(summary_stream)
        
        # 等待一下，让服务器恢复
        print("等待 5 秒让服务器恢复...")
        await asyncio.sleep(5)
        
        # 测试非流式
        print("\n>>> 测试非流式模式 <<<")
        tester_no_stream = ConcurrencyTester(
            base_url=args.url,
            concurrency=args.concurrency,
            requests_per_client=args.requests_per_client,
            duration=args.duration,
            query=args.query,
            stream=False,
            endpoint=args.endpoint
        )
        summary_no_stream = await tester_no_stream.run_test()
        tester_no_stream.print_report(summary_no_stream)
        
        # 对比总结
        print("\n" + "="*60)
        print("对比总结")
        print("="*60)
        print(f"\n{'指标':<25} {'流式模式':>15} {'非流式模式':>15}")
        print("-" * 60)
        print(f"{'成功率':<25} {summary_stream.success_rate:>14.2f}% {summary_no_stream.success_rate:>14.2f}%")
        print(f"{'平均延迟 (s)':<25} {summary_stream.avg_latency:>15.2f} {summary_no_stream.avg_latency:>15.2f}")
        print(f"{'P95延迟 (s)':<25} {summary_stream.p95_latency:>15.2f} {summary_no_stream.p95_latency:>15.2f}")
        print(f"{'QPS':<25} {summary_stream.requests_per_second:>15.2f} {summary_no_stream.requests_per_second:>15.2f}")
        print("="*60)
        
    else:
        # 单次测试
        tester = ConcurrencyTester(
            base_url=args.url,
            concurrency=args.concurrency,
            requests_per_client=args.requests_per_client,
            duration=args.duration,
            query=args.query,
            stream=not args.no_stream,
            endpoint=args.endpoint
        )
        
        summary = await tester.run_test()
        tester.print_report(summary)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
