#!/bin/bash
# Creates and initialises the Momentum site on first run.
# Idempotent — safe to run again if the container restarts.
set -euo pipefail

SITE_NAME="${SITE_NAME:-momentum.localhost}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

BENCH=/home/frappe/frappe-bench

echo "[create-site] Target site: $SITE_NAME"

# ── Wait for MariaDB ────────────────────────────────────────────────────────────
echo "[create-site] Waiting for MariaDB..."
until mysqladmin ping -h db -u root -p"${DB_ROOT_PASSWORD}" --silent 2>/dev/null; do
    sleep 3
done
echo "[create-site] MariaDB is ready."

# ── Write common_site_config.json ───────────────────────────────────────────────
# The configurator normally does this; we repeat it here so the create-site
# service is self-contained even when run independently.
bench set-config -g db_host db
bench set-config -g db_port 3306
bench set-config -g redis_cache "redis://redis-cache:6379"
bench set-config -g redis_queue "redis://redis-queue:6379"
bench set-config -g socketio_port 9000

# ── Register momentum in bench apps.txt ────────────────────────────────────────
# apps.txt lives in the sites volume; bench get-app normally writes it.
# Since we COPY the source directly, we register it here using Python to
# handle files that lack a trailing newline (common in frappe bench).
APPS_TXT="$BENCH/sites/apps.txt"
python3 - <<'PYEOF'
import os, sys
apps_file = os.environ.get('APPS_TXT', '/home/frappe/frappe-bench/sites/apps.txt')
try:
    raw = open(apps_file).read()
    # Split on whitespace to handle files missing trailing newlines
    apps = [a for a in raw.split() if a]
except FileNotFoundError:
    apps = []
if 'momentum' not in apps:
    apps.append('momentum')
    open(apps_file, 'w').write('\n'.join(apps) + '\n')
    print(f"[create-site] Registered momentum in apps.txt: {apps}")
else:
    print(f"[create-site] momentum already in apps.txt")
PYEOF

# ── Create site (skip if it already exists) ─────────────────────────────────────
SITES_DIR="$BENCH/sites"

if [ -f "$SITES_DIR/$SITE_NAME/site_config.json" ]; then
    echo "[create-site] Site '$SITE_NAME' already exists — checking installed apps..."
    # Ensure momentum is installed (handles image rebuilds / re-runs)
    INSTALLED=$(bench --site "$SITE_NAME" list-apps 2>/dev/null || true)
    if ! echo "$INSTALLED" | grep -q "^momentum$"; then
        echo "[create-site] Installing Momentum on existing site..."
        bench --site "$SITE_NAME" install-app momentum
    else
        echo "[create-site] Momentum already installed on '$SITE_NAME'."
    fi
    echo "[create-site] Running migrations..."
    bench --site "$SITE_NAME" migrate
else
    echo "[create-site] Creating site '$SITE_NAME'..."
    bench new-site "$SITE_NAME" \
        --db-root-password "$DB_ROOT_PASSWORD" \
        --admin-password "$ADMIN_PASSWORD" \
        --mariadb-user-host-login-scope='%'

    echo "[create-site] Installing ERPNext..."
    bench --site "$SITE_NAME" install-app erpnext

    echo "[create-site] Installing Momentum..."
    bench --site "$SITE_NAME" install-app momentum

    echo "[create-site] Running migrations..."
    bench --site "$SITE_NAME" migrate

    echo "[create-site] Setting site as default..."
    bench use "$SITE_NAME"

    echo "[create-site] Site '$SITE_NAME' ready."
fi

# ── Complete ERPNext setup wizard (if not already done) ─────────────────────────
# Creates the demo Company programmatically so the seed can run without any
# manual browser interaction.  Idempotent — skips if a Company already exists.
echo "[create-site] Completing ERPNext setup wizard (if needed)..."
bench --site "$SITE_NAME" execute momentum.seed.complete_setup_wizard
echo "[create-site] Setup wizard step complete."

# ── Seed demo data ──────────────────────────────────────────────────────────────
# The seed script manages its own idempotency via a sentinel file written to
# the site directory after a successful full run.  We always invoke it so that
# deferred seeds (e.g. setup wizard not done yet) retry on the next up.
echo "[create-site] Running demo data seed..."
bench --site "$SITE_NAME" execute momentum.seed.run
echo "[create-site] Seed step complete."

# Repair manufacturing demo data on sites that already have the seed sentinel
# (e.g. first run skipped BOM/Job Cards). Idempotent — safe on a fresh site too.
echo "[create-site] Ensuring manufacturing demo data..."
bench --site "$SITE_NAME" execute momentum.seed.seed_manufacturing_demo
echo "[create-site] Manufacturing demo data complete."
