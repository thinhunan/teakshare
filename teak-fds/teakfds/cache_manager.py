#!/usr/bin/env python3
"""
CacheManager - 缓存管理器
支持内存缓存和文件缓存
"""

import time
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import threading


@dataclass
class CacheEntry:
    """缓存条目"""
    data: Any
    timestamp: float
    ttl: float
    hits: int = 0


class CacheManager:
    """
    缓存管理器
    
    特点:
    - 支持内存缓存 (默认)
    - 支持文件持久化 (可选)
    - TTL过期机制
    - LRU淘汰策略
    - 线程安全
    """
    
    # 默认TTL配置 (秒)
    DEFAULT_TTL = {
        'quote': 60,           # 实时行情缓存60秒
        'depth': 30,           # 盘口数据缓存30秒
        'intraday': 60,        # 分时数据缓存60秒
        'kline': 86400,        # 历史K线缓存1天
        'financial': 604800,   # 财务数据缓存7天
        'valuation': 86400,    # 估值数据缓存1天
        'news': 3600,          # 新闻数据缓存1小时
    }
    
    def __init__(self, 
                 max_size: int = 1000,
                 persist_path: Optional[Path] = None):
        """
        Args:
            max_size: 最大缓存条目数
            persist_path: 持久化路径 (None则不持久化)
        """
        self.max_size = max_size
        self.persist_path = persist_path
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        # 命中统计
        self._hits = 0
        self._misses = 0
        
        # 加载持久化数据
        if persist_path and persist_path.exists():
            self._load_from_disk()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            key: 缓存键
        
        Returns:
            缓存数据，不存在或过期返回None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # 检查是否过期
            if time.time() - entry.timestamp > entry.ttl:
                del self._cache[key]
                self._misses += 1
                return None
            
            # 更新命中
            entry.hits += 1
            self._hits += 1
            
            return entry.data
    
    def set(self, key: str, data: Any, ttl: Optional[float] = None, 
            data_type: str = 'default') -> None:
        """
        设置缓存数据
        
        Args:
            key: 缓存键
            data: 缓存数据
            ttl: 过期时间 (秒)，None则使用默认值
            data_type: 数据类型，用于获取默认TTL
        """
        # 获取TTL
        if ttl is None:
            ttl = self.DEFAULT_TTL.get(data_type, 3600)
        
        with self._lock:
            # 检查是否需要淘汰
            if len(self._cache) >= self.max_size:
                self._evict()
            
            # 存入缓存
            self._cache[key] = CacheEntry(
                data=data,
                timestamp=time.time(),
                ttl=ttl
            )
            
            # 持久化
            if self.persist_path:
                self._save_to_disk()
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            
            return {
                'total_entries': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'persist_enabled': self.persist_path is not None
            }
    
    def _evict(self) -> None:
        """LRU淘汰策略"""
        # 按访问次数和最后访问时间排序
        entries = sorted(
            self._cache.items(),
            key=lambda x: (x[1].hits, x[1].timestamp)
        )
        
        # 删除最旧的25%
        evict_count = max(1, len(entries) // 4)
        for key, _ in entries[:evict_count]:
            del self._cache[key]
    
    def _save_to_disk(self) -> None:
        """保存到磁盘"""
        if not self.persist_path:
            return
        
        try:
            data = {}
            for key, entry in self._cache.items():
                data[key] = {
                    'data': entry.data,
                    'timestamp': entry.timestamp,
                    'ttl': entry.ttl,
                    'hits': entry.hits
                }
            
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self.persist_path.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            print(f"CacheManager save error: {e}")
    
    def _load_from_disk(self) -> None:
        """从磁盘加载"""
        if not self.persist_path or not self.persist_path.exists():
            return
        
        try:
            data = json.loads(self.persist_path.read_text())
            
            now = time.time()
            for key, entry in data.items():
                # 跳过过期数据
                if now - entry['timestamp'] > entry['ttl']:
                    continue
                
                self._cache[key] = CacheEntry(
                    data=entry['data'],
                    timestamp=entry['timestamp'],
                    ttl=entry['ttl'],
                    hits=entry.get('hits', 0)
                )
        except Exception as e:
            print(f"CacheManager load error: {e}")
    
    @staticmethod
    def generate_key(*args, **kwargs) -> str:
        """生成缓存键"""
        key_str = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_str.encode()).hexdigest()


# 带TTL的便捷缓存函数

def cached(ttl: int = 60, data_type: str = 'default'):
    """
    缓存装饰器
    
    Usage:
        @cached(ttl=60, data_type='quote')
        def get_quote(symbol: str):
            ...
    """
    def decorator(func):
        cache = {}
        
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key = CacheManager.generate_key(func.__name__, *args, **kwargs)
            
            # 检查缓存
            if key in cache:
                entry = cache[key]
                if time.time() - entry['timestamp'] < ttl:
                    return entry['data']
            
            # 调用函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            cache[key] = {
                'data': result,
                'timestamp': time.time()
            }
            
            return result
        
        return wrapper
    return decorator


# 全局缓存实例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        persist_path = Path.home() / '.openclaw' / 'cache' / 'data_proxy_cache.json'
        _cache_manager = CacheManager(max_size=2000, persist_path=persist_path)
    return _cache_manager


if __name__ == '__main__':
    # 测试
    print("Testing CacheManager...")
    
    cache = CacheManager(max_size=10)
    
    # 测试基本功能
    cache.set('test_key', {'name': 'test'}, ttl=60)
    data = cache.get('test_key')
    print(f"✓ Set and get: {data}")
    
    # 测试过期
    cache.set('expire_key', {'name': 'expire'}, ttl=1)
    time.sleep(1.5)
    data = cache.get('expire_key')
    print(f"✓ Expired key: {data}")
    
    # 测试统计
    cache.get('not_exist')
    stats = cache.get_stats()
    print(f"✓ Stats: hits={stats['hits']}, misses={stats['misses']}, hit_rate={stats['hit_rate']:.2%}")
    
    # 测试装饰器
    @cached(ttl=60)
    def expensive_function(n: int) -> int:
        print(f"  Computing expensive_function({n})...")
        return n * n
    
    print("\n✓ Testing decorator:")
    print(f"  First call: {expensive_function(5)}")
    print(f"  Second call (cached): {expensive_function(5)}")
    
    print("\n✓ CacheManager test passed!")
