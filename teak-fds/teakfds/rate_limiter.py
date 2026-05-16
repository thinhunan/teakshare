#!/usr/bin/env python3
"""
RateLimiter - 限流控制器
支持多级限流: 分钟级 + 日级 + 熔断
"""

from teakfds.datasource_log import log_info, log_warn, log_error
import time
import threading
from typing import Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class RateLimitConfig:
    """限流配置"""
    requests_per_minute: int
    requests_per_day: int
    cooldown_seconds: int = 60      # 熔断冷却时间
    failure_threshold: int = 5      # 连续失败N次触发熔断


@dataclass
class ProviderLimitState:
    """Provider限流状态"""
    minute_requests: list = field(default_factory=list)    # 分钟窗口
    day_requests: list = field(default_factory=list)       # 日窗口
    failure_count: int = 0                                  # 连续失败次数
    cooldown_until: float = 0                              # 熔断结束时间
    last_request_time: float = 0                           # 最后请求时间
    
    def is_in_cooldown(self) -> bool:
        """是否在熔断期"""
        return time.time() < self.cooldown_until
    
    def reset_cooldown(self):
        """重置熔断"""
        self.cooldown_until = 0
        self.failure_count = 0


class RateLimiter:
    """
    限流控制器
    
    功能:
    - 分钟级限流
    - 日级限流
    - 熔断机制 (连续失败自动熔断)
    - 自动恢复
    """
    
    # 默认限流配置
    DEFAULT_LIMITS = {
        # P0级 - 实时行情主源
        'tencent': RateLimitConfig(120, 10000, cooldown_seconds=30),  # ≤2次/秒
        'tdx': RateLimitConfig(300, 1000000, cooldown_seconds=30),

        # P1级 - 历史/财务数据主源
        'tushare': RateLimitConfig(120, 10000, cooldown_seconds=60),

        # P0级 - 估值主源
        'lixinger': RateLimitConfig(60, 5000, cooldown_seconds=60),

        # P2级 - 备份源
        'sina': RateLimitConfig(300, 50000, cooldown_seconds=30),  # ≤5次/秒

        # P3-P4级 - 低优先级备份
        'mx_data': RateLimitConfig(2, 50, cooldown_seconds=3600),  # 日限50次
        'mx_search': RateLimitConfig(2, 50, cooldown_seconds=3600),  # 日限50次

        # P4级 - 雪球备份
        'xueqiu': RateLimitConfig(20, 10000, cooldown_seconds=300),  # 分钟限20次

        # P6级 - 搜索兜底
        'search_fallback': RateLimitConfig(10, 500, cooldown_seconds=60),

        # 旧数据源（兼容性）
        'yahoo': RateLimitConfig(60, 100000, cooldown_seconds=60),
        'aggregate': RateLimitConfig(20, 2000, cooldown_seconds=120),
    }
    
    def __init__(self):
        self._states: Dict[str, ProviderLimitState] = defaultdict(ProviderLimitState)
        self._configs: Dict[str, RateLimitConfig] = dict(self.DEFAULT_LIMITS)
        self._lock = threading.RLock()
    
    def configure(self, provider: str, config: RateLimitConfig) -> None:
        """配置Provider限流参数"""
        self._configs[provider] = config
    
    def check(self, provider: str) -> bool:
        """
        检查是否允许请求
        
        Args:
            provider: 数据源名称
        
        Returns:
            True 如果允许请求, False 如果被限流
        """
        with self._lock:
            now = time.time()
            state = self._states[provider]
            config = self._configs.get(provider, RateLimitConfig(60, 10000))
            
            # 检查熔断
            if state.is_in_cooldown():
                return False
            
            # 清理过期记录
            state.minute_requests = [t for t in state.minute_requests if now - t < 60]
            state.day_requests = [t for t in state.day_requests if now - t < 86400]
            
            # 检查分钟限制
            if len(state.minute_requests) >= config.requests_per_minute:
                return False
            
            # 检查日限制
            if len(state.day_requests) >= config.requests_per_day:
                return False
            
            return True
    
    def record_request(self, provider: str) -> None:
        """记录一次请求"""
        with self._lock:
            now = time.time()
            state = self._states[provider]
            
            state.minute_requests.append(now)
            state.day_requests.append(now)
            state.last_request_time = now
            
            # 重置失败计数
            state.failure_count = 0
    
    def record_failure(self, provider: str, is_rate_limit_error: bool = False) -> None:
        """
        记录一次失败
        
        Args:
            provider: 数据源名称
            is_rate_limit_error: 是否为限流错误
        """
        with self._lock:
            state = self._states[provider]
            config = self._configs.get(provider, RateLimitConfig(60, 10000))
            
            state.failure_count += 1
            
            # 如果是限流错误，立即触发熔断
            if is_rate_limit_error:
                state.cooldown_until = time.time() + config.cooldown_seconds
                log_warn(f"⚠ {provider} rate limited, cooldown for {config.cooldown_seconds}s")
            
            # 连续失败达到阈值，触发熔断
            elif state.failure_count >= config.failure_threshold:
                state.cooldown_until = time.time() + config.cooldown_seconds
                log_warn(f"⚠ {provider} circuit breaker triggered, cooldown for {config.cooldown_seconds}s")
    
    def get_status(self, provider: str) -> Dict:
        """获取Provider限流状态"""
        with self._lock:
            now = time.time()
            state = self._states[provider]
            config = self._configs.get(provider, RateLimitConfig(60, 10000))
            
            # 清理过期记录
            state.minute_requests = [t for t in state.minute_requests if now - t < 60]
            state.day_requests = [t for t in state.day_requests if now - t < 86400]
            
            return {
                'provider': provider,
                'minute_used': len(state.minute_requests),
                'minute_limit': config.requests_per_minute,
                'day_used': len(state.day_requests),
                'day_limit': config.requests_per_day,
                'failure_count': state.failure_count,
                'in_cooldown': state.is_in_cooldown(),
                'cooldown_remaining': max(0, state.cooldown_until - now)
            }
    
    def get_all_status(self) -> Dict[str, Dict]:
        """获取所有Provider状态"""
        return {provider: self.get_status(provider) 
                for provider in self._configs}
    
    def reset(self, provider: str = None) -> None:
        """重置限流状态"""
        with self._lock:
            if provider:
                self._states[provider] = ProviderLimitState()
            else:
                self._states.clear()

    def reset_cooldown(self, provider: str) -> None:
        """手动重置某个 Provider 的熔断状态，保留历史请求计数"""
        with self._lock:
            state = self._states[provider]
            state.reset_cooldown()


class TokenBucket:
    """
    令牌桶限流器 (备选方案)
    更平滑的限流
    """
    
    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: 令牌产生速率 (个/秒)
            capacity: 桶容量
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        消费令牌
        
        Args:
            tokens: 需要的令牌数
        
        Returns:
            True 如果成功消费, False 如果令牌不足
        """
        with self._lock:
            now = time.time()
            
            # 补充令牌
            elapsed = now - self.last_update
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            # 尝试消费
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def wait_for_token(self, tokens: int = 1, timeout: float = None) -> bool:
        """
        等待令牌可用
        
        Args:
            tokens: 需要的令牌数
            timeout: 超时时间 (秒)
        
        Returns:
            True 如果成功获取令牌, False 如果超时
        """
        start = time.time()
        
        while True:
            if self.consume(tokens):
                return True
            
            if timeout and (time.time() - start) > timeout:
                return False
            
            # 等待一段时间再试
            time.sleep(0.1)


# 全局限流器实例
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """获取全局限流器"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


if __name__ == '__main__':
    # 测试
    print("Testing RateLimiter...")
    
    limiter = RateLimiter()
    
    # 测试基本限流
    print("\n✓ Testing basic rate limiting:")
    for i in range(5):
        if limiter.check('tushare'):
            limiter.record_request('tushare')
            print(f"  Request {i+1}: allowed")
        else:
            print(f"  Request {i+1}: blocked")
    
    # 测试熔断
    print("\n✓ Testing circuit breaker:")
    for i in range(6):
        limiter.record_failure('xueqiu')
        status = limiter.get_status('xueqiu')
        print(f"  Failure {i+1}: failure_count={status['failure_count']}, in_cooldown={status['in_cooldown']}")
    
    # 测试状态
    print("\n✓ All status:")
    for provider, status in limiter.get_all_status().items():
        print(f"  {provider}: {status['minute_used']}/{status['minute_limit']} per min, "
              f"{status['day_used']}/{status['day_limit']} per day")
    
    # 测试令牌桶
    print("\n✓ Testing TokenBucket:")
    bucket = TokenBucket(rate=1, capacity=5)  # 1个/秒，容量5
    
    for i in range(10):
        if bucket.consume():
            print(f"  Request {i+1}: consumed (tokens left: {bucket.tokens:.1f})")
        else:
            print(f"  Request {i+1}: no tokens")
    
    print("\n✓ RateLimiter test passed!")
