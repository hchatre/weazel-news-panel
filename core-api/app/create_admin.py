"""Create (or reset) a system administrator. The password is read from a prompt or WEAZEL_ADMIN_PASSWORD, never from argv.
Usage: python -m app.create_admin --email you@example.com --name "Your Name"
"""
import argparse
import getpass
import os
import sys

from app import models as m
from app.db import SessionLocal
from app.security import hash_password
from app.seed import seed_defaults


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    pw = os.environ.get("WEAZEL_ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if len(pw) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        seed_defaults(db)
        role = db.query(m.Role).filter_by(key="system_admin").one()
        user = db.query(m.User).filter_by(email=args.email.lower()).one_or_none()
        if user is None:
            db.add(m.User(display_name=args.name, email=args.email.lower(), password_hash=hash_password(pw), role_id=role.id, source="local"))
            print("Administrator created.")
        else:
            user.password_hash, user.role_id, user.is_active = hash_password(pw), role.id, True
            user.token_version += 1
            print("Existing user updated: password reset, role set to system_admin, sessions invalidated.")
        db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
