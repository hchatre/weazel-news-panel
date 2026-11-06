"""Delivers queued integration messages. Run beside the API:  python -m app.worker        (loop)   |   python -m app.worker --once"""
import argparse
import logging
import time

from app.db import SessionLocal
from app.services.outbox import process_due


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=15)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    while True:
        with SessionLocal() as db:
            stats = process_due(db)
        if any(stats.values()):
            logging.getLogger("weazel.worker").info("outbox: %s", stats)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
