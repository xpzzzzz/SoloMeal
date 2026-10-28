"""Run from an access-controlled application host, with its database credentials.

Example: python -m app.commands.reconcile_memory --receipt-id UUID --apply
Without --apply the command performs no database or network operation.
"""
import argparse
import os

from ..core.config import Settings
from ..core.database import build_engine, build_session_factory
from ..services.memory import get_memory_provider
from ..services.memory_operations import reconcile_confirmation


def _operator():
    if os.name == "nt":
        return "os:" + os.getlogin()
    import pwd
    return f"uid:{os.geteuid()}:{pwd.getpwuid(os.geteuid()).pw_name}"


def main():
    parser = argparse.ArgumentParser(description="Inspect one unknown memory confirmation")
    parser.add_argument("--receipt-id", required=True, help="Local confirmation operation UUID")
    parser.add_argument("--apply", action="store_true", help="Perform the controlled inspection")
    args = parser.parse_args()
    if not args.apply:
        print("Dry run: no database or remote requests; pass --apply to inspect one operation.")
        return
    try:
        operator = _operator()
        settings = Settings()
        engine = build_engine(settings.database_url)
        provider = get_memory_provider(settings)
        try:
            with build_session_factory(engine)() as db:
                result = reconcile_confirmation(db, args.receipt_id, provider, operator=operator)
        finally:
            provider.close()
            engine.dispose()
        print("Reconciliation outcome:", result)
    except Exception:
        # Configuration, connection exceptions and SQL may contain credentials.
        print("Reconciliation failed; no conclusion can be drawn.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
