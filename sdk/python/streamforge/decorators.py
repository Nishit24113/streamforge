import functools
import time
import traceback
from typing import Any, Callable

from .client import StreamForge


_default_client: StreamForge | None = None


def configure(api_url: str | None = None, **kwargs) -> StreamForge:
    global _default_client
    _default_client = StreamForge(api_url=api_url, **kwargs)
    return _default_client


def _get_client() -> StreamForge:
    global _default_client
    if _default_client is None:
        _default_client = StreamForge()
    return _default_client


def streamforge_event(pipeline_id: str, event_type: str = 'function_result'):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            try:
                event = result if isinstance(result, dict) else {'result': result}
                event.setdefault('event_type', event_type)
                event.setdefault('timestamp', int(time.time() * 1000))
                _get_client().ingest(pipeline_id, [event])
            except Exception:
                pass
            return result
        return wrapper
    return decorator


def streamforge_track(pipeline_id: str, fields: list[str] | None = None):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            error = None
            result = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = e
                raise
            finally:
                duration_ms = int((time.time() - start) * 1000)
                event: dict[str, Any] = {
                    'event_type': 'function_call',
                    'function': func.__qualname__,
                    'module': func.__module__,
                    'duration_ms': duration_ms,
                    'success': error is None,
                    'timestamp': int(time.time() * 1000),
                }
                if error:
                    event['error'] = str(error)
                    event['error_type'] = type(error).__name__
                if fields and isinstance(result, dict):
                    for f in fields:
                        if f in result:
                            event[f] = result[f]
                try:
                    _get_client().ingest(pipeline_id, [event])
                except Exception:
                    pass
        return wrapper
    return decorator
