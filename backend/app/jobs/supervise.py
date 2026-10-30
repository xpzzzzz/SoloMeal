"""Run the outbox and Celery in one Worker service; stop both on service shutdown."""
import signal
import subprocess
import sys
import time
from pathlib import Path


def main(celery_application="app.jobs.celery_app:app"):
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    children.append(subprocess.Popen([sys.executable, "-m", "app.jobs.outbox"]))
    children.append(subprocess.Popen([sys.executable, "-m", "celery", "-A", celery_application,
                                     "worker", "--loglevel=INFO", "--pool=prefork"]))
    Path("/tmp/receipt-worker.pid").write_text(str(children[-1].pid))
    try:
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(.25)
    finally:
        requested_stop = stopping
        stop()
        for child in children:
            try:
                child.wait(timeout=100)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return 0 if requested_stop else 1


if __name__ == "__main__":
    sys.exit(main())
