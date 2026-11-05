#!/usr/bin/env bash
# Starts PostgreSQL (and, if installed, MariaDB for legacy-import tests) in the Linux sandbox. Not needed on Windows,
# where you run your own PostgreSQL service. Safe to run repeatedly.
service postgresql start >/dev/null 2>&1 || true
if command -v mysqld_safe >/dev/null 2>&1; then
  mkdir -p /run/mysqld && chown mysql:mysql /run/mysqld 2>/dev/null || true
  mariadb -uroot -e "select 1" >/dev/null 2>&1 || (mysqld_safe --user=mysql --bind-address=127.0.0.1 >/tmp/mariadb.log 2>&1 &)
fi
for i in $(seq 1 30); do
  PGPASSWORD=weazel_dev psql -h 127.0.0.1 -U weazel -d weazel_test -tc "select 1" >/dev/null 2>&1 && break; sleep 1
done
echo "postgres: $(PGPASSWORD=weazel_dev psql -h 127.0.0.1 -U weazel -d weazel_test -tAc 'select 1' 2>&1 | head -1)"
command -v mariadb >/dev/null 2>&1 && { for i in $(seq 1 30); do mariadb -uroot -e "select 1" >/dev/null 2>&1 && break; sleep 1; done; echo "mariadb: $(mariadb -uroot -e 'select 1' 2>&1 | tail -1)"; }
