"""python -m app.legacy --mysql-url mysql+pymysql://reader:pw@127.0.0.1/qbcore [--dry-run] [--verify]"""
import argparse
import json
import os
import sys

from app.db import SessionLocal
from app.legacy.importer import ImportConflict, MySQLSource, import_legacy, verify_legacy


def main() -> int:
    p = argparse.ArgumentParser(description="Import the legacy Weazel MySQL tables (read-only on the MySQL side)")
    p.add_argument("--mysql-url", default=os.environ.get("WEAZEL_LEGACY_MYSQL_URL"), help="or set WEAZEL_LEGACY_MYSQL_URL")
    p.add_argument("--dry-run", action="store_true", help="run everything, then roll back")
    p.add_argument("--verify", action="store_true", help="only compare source and platform, change nothing")
    a = p.parse_args()
    if not a.mysql_url:
        print("Provide --mysql-url or WEAZEL_LEGACY_MYSQL_URL", file=sys.stderr)
        return 2
    src = MySQLSource(a.mysql_url)
    with SessionLocal() as db:
        try:
            out = verify_legacy(db, src) if a.verify else import_legacy(db, src, dry_run=a.dry_run).as_dict()
        except ImportConflict as e:
            print(f"IMPORT ABORTED, nothing was written: {e}", file=sys.stderr)
            return 1
    print(json.dumps(out, indent=2, default=str))
    return 0 if (not a.verify or out["ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
