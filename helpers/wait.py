import time 


def wait_until(condition, wait_time=30, interval=3):
    deadline = time.monotonic() + wait_time
    while True:
        if condition():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Condition {getattr(condition, '__name__', condition)} "
                f"not fulfilled after {wait_time}s"
            )
        time.sleep(min(interval, remaining))