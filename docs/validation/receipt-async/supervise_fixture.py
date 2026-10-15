"""Test-only entry; production uses the default supervisor app."""
from app.jobs.supervise import main

if __name__ == '__main__':
    raise SystemExit(main('validation_worker:app'))
