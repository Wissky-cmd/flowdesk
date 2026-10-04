import logging
import signal
import threading

from .job_runtime import dispatch_once
from .worker import export_csv

stop = threading.Event()


def main():
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        try:
            dispatch_once(lambda job_id: export_csv.apply_async(args=[job_id]))
        except Exception:
            logging.exception('Dispatcher tick failed; persisted budgets are retained')
        stop.wait(5)


if __name__ == '__main__':
    main()
