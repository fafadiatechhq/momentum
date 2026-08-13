# Momentum — Developer Notes

This document covers everything a developer needs to work on the Momentum app: local setup, architecture decisions, how to add reports, how the scheduler works, and how to debug common issues.

---

## Table of Contents

1. [Local Development Setup](#1-local-development-setup)
2. [Docker Development](#2-docker-development)
3. [Architecture Overview](#3-architecture-overview)
4. [DocType Reference](#4-doctype-reference)
5. [Adding a New Report](#5-adding-a-new-report)
6. [Snapshot Scheduler](#6-snapshot-scheduler)
7. [Roles & Permissions](#7-roles--permissions)
8. [Seed Data](#8-seed-data)
9. [Performance Guidelines](#9-performance-guidelines)
10. [Open Engineering Questions (from PRD)](#10-open-engineering-questions-from-prd)

---

## 1. Local Development Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- MariaDB 10.6+
- Redis
- `bench` CLI installed

### Install

```bash
# From your bench root
bench get-app /path/to/momentum   # or git URL
bench --site your-dev-site.localhost install-app momentum
bench --site your-dev-site.localhost migrate
bench start
```

### Pre-commit hooks

```bash
cd apps/momentum
pip install pre-commit
pre-commit install
```

The hooks run `ruff` (lint + format), `eslint`, `prettier`, and `pyupgrade` on every commit.

### Run tests

```bash
bench --site your-dev-site.localhost run-tests --app momentum
```

---

## 2. Docker Development

See the [Dockerized setup](#) section for `docker compose up` instructions. For active development, mount the app source as a volume in `docker-compose.override.yml`:

```yaml
services:
  backend:
    volumes:
      - .:/home/frappe/frappe-bench/apps/momentum
```

Then after code changes:
```bash
docker compose exec backend bench --site momentum.localhost migrate
docker compose restart backend
```

---

## 3. Architecture Overview

### Core principle
Momentum does **not** touch ERPNext's data entry flow. It only **reads** from existing doctypes (`Timesheet`, `Timesheet Detail`, `Job Card`, `Work Order`, `Project`, `Task`, `Sales Invoice`) and exposes aggregated results through Reports and Dashboards.

### Two output surfaces
1. **Script Reports** (Python) — for all tabular/analytical views. Run on demand with user-specified filters. Use `frappe.db.sql()` or Query Builder with `GROUP BY` and derived columns. Never loop over `frappe.get_all()` results server-side.

2. **Snapshot DocTypes** (stored aggregate records) — for Number Cards and Dashboard Charts. Frappe Dashboard Charts can only query a single DocType; they cannot do live joins. So we pre-compute daily aggregates into `Momentum Project Snapshot`, `Momentum Employee Utilization Snapshot`, and `Momentum Operation Efficiency Snapshot` via a nightly scheduler job.

### Why snapshots instead of views
- Frappe Dashboard Charts accept only a `doctype` parameter for their data source, not a query.
- Trend charts (line charts over time) need stored rows per date — there is no ad-hoc "date dimension" in the chart engine.
- Number Cards similarly fetch one row from one doctype.
- SQL views are not portable across MariaDB versions and can't be expressed in Frappe fixtures.

### Aggregation is idempotent
The nightly job deletes and recreates the snapshot rows for the target date before inserting fresh ones. This means jobs can be safely re-run or backfilled without duplicates.

---

## 4. DocType Reference

### `Momentum Settings` (Single)
The single configuration doctype. App behaviour pivots off `enable_services_pack` and `enable_manufacturing_pack`. The `cost_rate_source` field controls how the scheduler resolves an employee's hourly cost in snapshot calculations.

### `Momentum Project Snapshot`
Keyed on `(project, date)`. Rebuilt nightly for all open projects. Used by:
- Services Dashboard — margin trend chart, at-risk projects card.
- `Margin Trend by Project` Script Report (reads stored snapshots for trend lines).

Fields: `project`, `date`, `company`, `billable_hours`, `non_billable_hours`, `total_cost`, `billed_amount_at_standard_rate`, `actual_invoiced_amount`, `budget_hours`, `budget_amount`, `status_flag`.

### `Momentum Employee Utilization Snapshot`
Keyed on `(employee, date)`. Rebuilt nightly. Used by:
- Services Dashboard — overall utilization % card, utilization trend chart.
- `Utilization Summary` report when trend mode is selected.

Fields: `employee`, `date`, `company`, `available_hours`, `billable_hours`, `non_billable_hours`, `utilization_percent`, `overtime_hours`.

### `Momentum Operation Efficiency Snapshot`
Keyed on `(work_order, operation, date)`. Manufacturing pack only. Used by:
- Manufacturing Dashboard — efficiency trend by work center.

Fields: `work_order`, `operation`, `work_center`, `date`, `standard_time_mins`, `actual_time_mins`, `efficiency_percent`, `standard_cost`, `actual_cost`, `cost_variance`.

---

## 5. Adding a New Report

1. Create the Script Report via Frappe Desk (DocType: `Report`, type: `Script Report`).
2. Place the Python file at:
   ```
   momentum/momentum/report/<report_slug>/<report_slug>.py
   ```
3. The file must export `execute(filters=None)` returning `(columns, data)`.
4. Columns use the standard Frappe column dict:
   ```python
   {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150}
   ```
5. Use `frappe.db.sql(query, values, as_dict=True)` with parameterised values — never f-strings with user filter values.
6. Add company filter + permission query condition so that Company-level User Permissions are respected:
   ```python
   conditions = "AND ts.company = %(company)s" if filters.get("company") else ""
   ```
7. Commit the report JSON fixture alongside the Python file so it can be exported and version-controlled:
   ```bash
   bench --site ... export-fixtures --app momentum
   ```

---

## 6. Snapshot Scheduler

Entry point in `hooks.py`:
```python
scheduler_events = {
    "daily": ["momentum.tasks.rebuild_daily_snapshots"]
}
```

The `rebuild_daily_snapshots` function in `momentum/tasks.py`:
1. Reads `Momentum Settings` to check which packs are enabled.
2. For each enabled pack, calls the relevant builder:
   - `momentum.aggregation.services.rebuild_project_snapshot(date)`
   - `momentum.aggregation.services.rebuild_utilization_snapshot(date)`
   - `momentum.aggregation.manufacturing.rebuild_operation_snapshot(date)`
3. Each builder: deletes existing rows for that date, recomputes from source doctypes, inserts fresh rows.

### Backfill
The `backfill_snapshots(from_date, to_date)` whitelisted method iterates over each date in the range and calls the same builders. Exposed as a button on Momentum Settings.

### Re-running manually
```bash
bench --site your-site.localhost execute momentum.tasks.rebuild_daily_snapshots
```

---

## 7. Roles & Permissions

Three roles, defined in fixtures:

| Role | Report Access | Dashboard Access | Settings |
|---|---|---|---|
| Momentum Manager | All reports, all companies | Both dashboards | Read/Write |
| Momentum Services Viewer | Services reports only | Services dashboard | None |
| Momentum Manufacturing Viewer | Manufacturing reports only | Manufacturing dashboard | None |

Permission query conditions are set on all Snapshot doctypes and all reports to enforce ERPNext's existing Company-level User Permissions. The `company` field on each snapshot is the join point.

---

## 8. Seed Data

The seed script creates demo data for development and testing. It is idempotent — safe to run multiple times.

```bash
# Inside your bench (or Docker container)
bench --site your-site.localhost execute momentum.seed.run
```

What it creates:
- **2 departments**: Engineering, Design
- **5 employees** with activity type cost rates
- **4 activity types** with billing and costing rates
- **4 projects** with tasks (Services)
- **90 days of timesheets** (~65 working days × 5 employees, weekly batches)
- **2 work centers**, **2 operations**, **2 work orders**, **job cards** (Manufacturing)

All records use the first company found on the site. If a record already exists (matched by name/identifier), it is skipped.

---

## 9. Performance Guidelines

- All Script Reports must run against 50k+ Timesheet rows in under 5 seconds.
- Use `frappe.db.sql()` with `GROUP BY` and aggregate functions. Do not fetch all rows and aggregate in Python.
- Snapshot tables must have composite indexes on `(date, <link field>)`. Define these in the DocType JSON (`in_standard_filter: 1`, `search_index: 1`).
- Number Cards and Dashboard Charts always query snapshot doctypes — never live Timesheet/Job Card tables.
- For the backfill path, use `frappe.db.bulk_insert()` when inserting many snapshot rows at once.

---

## 10. Open Engineering Questions (from PRD)

These are unresolved before implementation begins on the relevant reports:

1. **Employee cost rate source in ERPNext v15** — `Momentum Settings.cost_rate_source` supports three modes: "Employee Cost Rate", "Activity Type Costing Rate", "Custom Field". The exact field paths in ERPNext v15 for the first and third options need to be confirmed against the client's ERPNext configuration before the snapshot builder is written. The Activity Type path is straightforward (`Activity Type.costing_rate`).

2. **Standard time source for manufacturing efficiency** — The Operation Efficiency Snapshot needs a "standard time" baseline. In ERPNext v15, this can come from either the `BOM Operation.time_in_mins` field or the `Operation` master's default time. Confirm which the client's manufacturing module uses before building the manufacturing aggregation logic.
