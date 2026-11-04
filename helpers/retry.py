import functools
import time


def retry(times=5, delay=3, exceptions=(Exception,)):
    if times < 1:
        raise ValueError(f"times must be >= 1, got {times}")

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == times:
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator