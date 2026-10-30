"""Run the proactive tick on an application host, using its configured database."""
import argparse
import json
import sys
from datetime import datetime, timezone
from uuid import UUID

from ..core.config import Settings
from ..core.database import build_engine, build_session_factory
from ..services.proactivity_store import tick_all


def main():
    parser = argparse.ArgumentParser(description="Run the proactive inbox tick")
    parser.add_argument("--user-id", type=UUID)
    args = parser.parse_args()
    engine = None
    try:
        engine = build_engine(Settings().database_url)
        with build_session_factory(engine)() as db:
            print(json.dumps(tick_all(db, datetime.now(timezone.utc), args.user_id)))
    except Exception:
        # Database diagnostics may include SQL parameters or credentials.
        print("Proactive tick failed; check database availability and migrations.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
