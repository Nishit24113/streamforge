"""
Query result caching layer for StreamForge analytics.

Supports:
- In-memory caching with TTL
- Redis caching (optional)
- Cache invalidation on new data
- Query fingerprinting
"""

import json
import hashlib
import time
from typing import Any, Optional
from functools import lru_cache


class CacheManager:
    """Manages query result caching with multiple backends."""

    def __init__(self, backend='memory', ttl=300):
        """
        Initialize cache manager.

        Args:
            backend: 'memory' or 'redis'
            ttl: Time to live in seconds (default 5 minutes)
        """
        self.backend = backend
        self.ttl = ttl
        self._memory_cache = {}

        if backend == 'redis':
            try:
                import redis
                self.redis_client = redis.Redis(
                    host='localhost',
                    port=6379,
                    decode_responses=True
                )
            except ImportError:
                print('Redis not available, falling back to memory cache')
                self.backend = 'memory'

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if self.backend == 'memory':
            return self._get_from_memory(key)
        elif self.backend == 'redis':
            return self._get_from_redis(key)
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        ttl = ttl or self.ttl

        if self.backend == 'memory':
            self._set_in_memory(key, value, ttl)
        elif self.backend == 'redis':
            self._set_in_redis(key, value, ttl)

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        if self.backend == 'memory':
            self._memory_cache.pop(key, None)
        elif self.backend == 'redis':
            try:
                self.redis_client.delete(key)
            except Exception:
                pass

    def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate all keys matching pattern (e.g., 'pipeline_*')."""
        if self.backend == 'memory':
            keys_to_delete = [k for k in self._memory_cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._memory_cache[key]
        elif self.backend == 'redis':
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            except Exception:
                pass

    def _get_from_memory(self, key: str) -> Optional[Any]:
        """Get from in-memory cache."""
        entry = self._memory_cache.get(key)
        if not entry:
            return None

        value, expiry = entry
        if time.time() > expiry:
            del self._memory_cache[key]
            return None

        return value

    def _set_in_memory(self, key: str, value: Any, ttl: int) -> None:
        """Set in in-memory cache."""
        expiry = time.time() + ttl
        self._memory_cache[key] = (value, expiry)

    def _get_from_redis(self, key: str) -> Optional[Any]:
        """Get from Redis cache."""
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception:
            pass
        return None

    def _set_in_redis(self, key: str, value: Any, ttl: int) -> None:
        """Set in Redis cache."""
        try:
            self.redis_client.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
        except Exception:
            pass


def query_fingerprint(sql: str, params: dict = None) -> str:
    """
    Generate unique fingerprint for query + params.

    Used as cache key.
    """
    query_str = sql.lower().strip()
    if params:
        query_str += json.dumps(params, sort_keys=True)

    return hashlib.md5(query_str.encode()).hexdigest()


@lru_cache(maxsize=1000)
def parse_query_cached(sql: str) -> dict:
    """
    Parse SQL query and cache the result.

    Useful for extracting table names, columns, etc.
    """
    # Simplified parser - in production, use sqlparse library
    sql_lower = sql.lower()

    tables = []
    if 'from' in sql_lower:
        from_idx = sql_lower.index('from')
        after_from = sql[from_idx + 4:].strip().split()[0]
        tables.append(after_from)

    return {
        'tables': tables,
        'is_select': sql_lower.startswith('select'),
        'is_aggregate': any(agg in sql_lower for agg in ['sum(', 'avg(', 'count(', 'max(', 'min(']),
    }


class QueryCache:
    """High-level query cache with automatic invalidation."""

    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager

    def get_query_result(self, sql: str, params: dict = None) -> Optional[dict]:
        """Get cached query result."""
        key = f'query:{query_fingerprint(sql, params)}'
        return self.cache.get(key)

    def set_query_result(self, sql: str, result: dict, params: dict = None, ttl: int = 300) -> None:
        """Cache query result."""
        key = f'query:{query_fingerprint(sql, params)}'
        self.cache.set(key, result, ttl)

    def invalidate_table(self, table_name: str) -> None:
        """Invalidate all queries touching a table."""
        pattern = f'query:*'
        self.cache.invalidate_pattern(pattern)

    def invalidate_pipeline(self, pipeline_id: str) -> None:
        """Invalidate all queries for a pipeline."""
        pattern = f'query:*{pipeline_id}*'
        self.cache.invalidate_pattern(pattern)


class BatchProcessor:
    """Batch processing optimizations."""

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size

    def batch_events(self, events: list, batch_size: int = None) -> list:
        """
        Split events into batches.

        Example:
            >>> processor = BatchProcessor(batch_size=100)
            >>> batches = processor.batch_events(events, batch_size=50)
            >>> for batch in batches:
            ...     process(batch)
        """
        batch_size = batch_size or self.batch_size
        batches = []

        for i in range(0, len(events), batch_size):
            batches.append(events[i:i + batch_size])

        return batches

    def parallel_process(self, items: list, process_fn, max_workers: int = 4):
        """
        Process items in parallel using ThreadPoolExecutor.

        Example:
            >>> def process_batch(batch):
            ...     return transform(batch)
            >>> results = processor.parallel_process(batches, process_batch)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_fn, item) for item in items]

            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f'Error processing batch: {e}')

        return results


class PerformanceMonitor:
    """Monitor query and processing performance."""

    def __init__(self):
        self.metrics = {
            'query_count': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'avg_query_time': 0,
            'total_query_time': 0,
        }

    def record_query(self, duration: float, cache_hit: bool = False) -> None:
        """Record query execution."""
        self.metrics['query_count'] += 1
        self.metrics['total_query_time'] += duration

        if cache_hit:
            self.metrics['cache_hits'] += 1
        else:
            self.metrics['cache_misses'] += 1

        self.metrics['avg_query_time'] = (
            self.metrics['total_query_time'] / self.metrics['query_count']
        )

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.metrics['cache_hits'] + self.metrics['cache_misses']
        if total == 0:
            return 0.0
        return self.metrics['cache_hits'] / total

    def get_stats(self) -> dict:
        """Get performance statistics."""
        return {
            **self.metrics,
            'cache_hit_rate': self.get_cache_hit_rate(),
        }

    def reset(self) -> None:
        """Reset metrics."""
        self.metrics = {
            'query_count': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'avg_query_time': 0,
            'total_query_time': 0,
        }


# Global instances for Lambda reuse
_cache_manager = None
_query_cache = None
_performance_monitor = None


def get_cache_manager() -> CacheManager:
    """Get singleton cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(backend='memory', ttl=300)
    return _cache_manager


def get_query_cache() -> QueryCache:
    """Get singleton query cache instance."""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache(get_cache_manager())
    return _query_cache


def get_performance_monitor() -> PerformanceMonitor:
    """Get singleton performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor
