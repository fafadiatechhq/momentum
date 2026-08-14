"""
Momentum demo seed data.

Run with:
    bench --site <site> execute momentum.seed.run

Idempotent at two levels:
  1. A sentinel file (.momentum_seed_complete) in the site directory is written
     after a successful full run. Subsequent calls return immediately.
  2. Each individual record is checked via frappe.db.exists() before creation,
     so partial runs (e.g. interrupted mid-way) are also safe to re-run.

What gets created (against the first company found on the site):
  - 2 Departments
  - 4 Activity Types with billing + costing rates
  - 5 Employees with distinct utilization / compliance profiles
  - 4 Customers (Demo Client A–D)
  - 4 Projects with Tasks linked to customers  (Services pack demo)
    Budgets are tuned so the set includes On Track, At Risk, and Over Budget
  - ~90 days of timesheets with employee→project affinity, mixed billable
    ratios, some skipped weeks (compliance gaps), and most rows linked to tasks
  - 3 submitted Sales Invoices with staggered posting dates (one project left unbilled)
  - Momentum Project Snapshots AND Employee Utilization Snapshots for ~90 working days
  - 1 Item, 1 BOM, 2 Work Centers, 2 Operations,
    ~8 Work Orders over 90 days, Job Cards with multi-day time logs,
    operators, and Morning / Afternoon / Evening shifts
  - Momentum Operation Efficiency Snapshots for each Job Card date

If you need to rebuild snapshots on an existing seeded site (e.g. after
upgrading Momentum) without wiping source data, run:
    bench --site <site> execute momentum.seed.seed_dashboard_snapshots
    bench --site <site> execute momentum.seed.seed_manufacturing_snapshots

Docker usage:
    The docker/create-site.sh script calls complete_setup_wizard() then run()
    automatically on every  docker compose up, so demo data is ready without
    any manual wizard step.  Both functions are fully idempotent.
"""

import os
import random
from datetime import date, timedelta

import frappe

from momentum.install import assign_momentum_manager, ensure_momentum_roles

_SENTINEL = ".momentum_seed_complete"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _exists(doctype, filters):
    return bool(frappe.db.exists(doctype, filters))


def _get_or_skip(doctype, filters, label=""):
    name = frappe.db.get_value(doctype, filters, "name")
    if name:
        return name
    return None


def _insert(doc_dict, unique_field=None, unique_value=None):
    """Insert a document, skip silently if it already exists."""
    doctype = doc_dict["doctype"]
    if unique_field and unique_value:
        if _exists(doctype, {unique_field: unique_value}):
            return frappe.db.get_value(doctype, {unique_field: unique_value}, "name")
    doc = frappe.get_doc(doc_dict)
    doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
    frappe.db.commit()
    return doc.name


def _workdays(start: date, end: date):
    """Yield each weekday (Mon–Fri) between start and end inclusive."""
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def _dt(d: date, hour: int, minute: int = 0):
    """Return a datetime string from a date + hour."""
    return f"{d} {hour:02d}:{minute:02d}:00"


# Country → fiscal-year start (MM-DD). Mirrors erpnext/public/js/setup_wizard.js.
# End date is always start + 1 year − 1 day (required by Fiscal Year validation).
_FY_START_MMDD = {
    "Afghanistan": "12-21",
    "Australia": "07-01",
    "Bangladesh": "07-01",
    "Costa Rica": "10-01",
    "Egypt": "07-01",
    "Ethiopia": "07-08",
    "Hong Kong": "04-01",
    "India": "04-01",
    "Iran": "06-23",
    "Kenya": "07-01",
    "Malaysia": "07-01",
    "Myanmar": "04-01",
    "Nepal": "07-16",
    "New Zealand": "04-01",
    "Pakistan": "07-01",
    "Singapore": "04-01",
    "South Africa": "03-01",
    "Thailand": "10-01",
    "United Kingdom": "04-01",
}


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29 Feb → 28 Feb on non-leap years
        return d.replace(year=d.year + years, day=28)


def _fy_year_name(start: date, end: date) -> str:
    if start.year == end.year:
        return str(start.year)
    return f"{start.year}-{end.year}"


def _current_fy_dates(country: str, today: date | None = None) -> tuple[date, date]:
    """Return (start, end) of the fiscal year that contains `today`, for `country`."""
    today = today or date.today()
    start_md = _FY_START_MMDD.get(country, "01-01")
    year = today.year
    start = date.fromisoformat(f"{year}-{start_md}")
    if start > today:
        start = date.fromisoformat(f"{year - 1}-{start_md}")
    end = _add_years(start, 1) - timedelta(days=1)
    return start, end


def _fiscal_year_covers(d: date) -> bool:
    return bool(
        frappe.db.sql(
            """
            SELECT name FROM `tabFiscal Year`
            WHERE year_start_date <= %(d)s
              AND year_end_date >= %(d)s
              AND IFNULL(disabled, 0) = 0
            LIMIT 1
            """,
            {"d": d},
        )
    )


def _insert_fiscal_year(start: date, end: date):
    """Create a Fiscal Year for [start, end] if it does not already exist."""
    year_name = _fy_year_name(start, end)
    if frappe.db.exists("Fiscal Year", year_name):
        print(f"[seed] Fiscal Year already exists: {year_name}")
        return year_name
    if _fiscal_year_covers(start) and _fiscal_year_covers(end):
        print(f"[seed] Date range {start} → {end} already covered by an existing Fiscal Year")
        return None
    doc = frappe.get_doc({
        "doctype": "Fiscal Year",
        "year": year_name,
        "year_start_date": start,
        "year_end_date": end,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"[seed] Fiscal Year: {year_name} ({start} → {end})")
    return year_name


def _ensure_fiscal_years(company=None):
    """
    Guarantee Fiscal Year records exist for today and the 90-day seed window.

    Idempotent. Safe to call when the wizard already created the current FY,
    or when a previous run created a Company but swallowed a failed FY insert.
    """
    if company:
        print(f"[seed] Ensuring Fiscal Years for {company}...")
    country = (
        os.environ.get("DEMO_COUNTRY")
        or frappe.db.get_single_value("System Settings", "country")
        or "India"
    )
    today = date.today()
    seed_start = today - timedelta(days=90)

    current_start, current_end = _current_fy_dates(country, today)
    _insert_fiscal_year(current_start, current_end)

    if not _fiscal_year_covers(seed_start):
        prev_start = _add_years(current_start, -1)
        prev_end = current_start - timedelta(days=1)
        _insert_fiscal_year(prev_start, prev_end)


# ── Setup-wizard automation ────────────────────────────────────────────────────


def complete_setup_wizard():
    """
    Programmatically complete the ERPNext setup wizard so that demo data can be
    seeded without any manual browser interaction.

    Called by docker/create-site.sh before run().  Safe to call on an existing
    site — skips the wizard if a Company is already present, but still ensures
    Fiscal Year records cover today and the 90-day seed window.

    Override defaults via environment variables:
        DEMO_COMPANY   — company name  (default: "Demo Company")
        DEMO_ABBR      — company abbr  (default: "DC")
        DEMO_COUNTRY   — country       (default: "India"; also drives FY dates)
        DEMO_CURRENCY  — currency      (default: "INR")
        DEMO_TIMEZONE  — timezone      (default: "Asia/Kolkata")
    """
    frappe.set_user("Administrator")
    ensure_momentum_roles()
    assign_momentum_manager("Administrator")

    company_name = os.environ.get("DEMO_COMPANY", "Demo Company")
    company_abbr = os.environ.get("DEMO_ABBR", "DC")
    country      = os.environ.get("DEMO_COUNTRY", "India")
    currency     = os.environ.get("DEMO_CURRENCY", "INR")
    timezone     = os.environ.get("DEMO_TIMEZONE", "Asia/Kolkata")
    fy_start, fy_end = _current_fy_dates(country)

    # Skip wizard if a company already exists, but repair a missing Fiscal Year
    # (ERPNext's make_records swallows FY insert errors, so a prior run can
    # leave a Company with no Fiscal Year).
    existing_company = frappe.db.get_value("Company", {}, "name")
    if existing_company:
        print("[seed] Company already exists — setup wizard already complete.")
        _ensure_fiscal_years(existing_company)
        return

    print(f"[seed] Completing ERPNext setup wizard — company: {company_name} ({company_abbr})")
    print(f"[seed] Fiscal Year: {fy_start} → {fy_end}")

    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    args = frappe._dict(
        language="English",
        country=country,
        timezone=timezone,
        currency=currency,
        # Frappe v15 create_or_update_user() reads full_name, not first_name.
        full_name="Demo Admin",
        first_name="Demo",
        last_name="Admin",
        email="admin@momentum.localhost",
        company_name=company_name,
        company_abbr=company_abbr,
        chart_of_accounts="Standard",
        bank_account="Cash",
        fy_start_date=str(fy_start),
        fy_end_date=str(fy_end),
    )

    # The admin user created by `bench new-site` has no first_name, which causes
    # Frappe's mandatory-field validation to reject the User save inside
    # setup_complete().  Patch it directly (bypassing doc validation) before the
    # wizard runs so the record is already valid when touched.
    for user_name in ("Administrator", args.email):
        if frappe.db.exists("User", user_name):
            frappe.db.set_value("User", user_name, "first_name", args.first_name, update_modified=False)
            frappe.db.set_value("User", user_name, "last_name", args.last_name, update_modified=False)
    frappe.db.commit()

    setup_complete(args)
    frappe.db.commit()
    print(f"[seed] Setup wizard complete. Company '{company_name}' is ready.")

    _ensure_fiscal_years(company_name)

    # Grant Momentum Manager so the workspace and all reports are visible
    # immediately after setup without any manual role assignment.
    assign_momentum_manager("Administrator")
    assign_momentum_manager(args.email)


# ── Top-level seeder ───────────────────────────────────────────────────────────


def run():
    frappe.set_user("Administrator")
    ensure_momentum_roles()
    assign_momentum_manager("Administrator")

    # ── Sentinel check ─────────────────────────────────────────────────────────
    sentinel = frappe.get_site_path(_SENTINEL)
    if os.path.exists(sentinel):
        print("[seed] Already complete (sentinel file found) — nothing to do.")
        return

    # ── Guard: setup wizard must be done ──────────────────────────────────────
    company = frappe.db.get_value("Company", {}, "name")
    if not company:
        print(
            "\n[seed] SKIPPED — no Company found on this site.\n"
            "[seed] Run:  bench --site <site> execute momentum.seed.complete_setup_wizard\n"
            "[seed] then: bench --site <site> execute momentum.seed.run\n"
        )
        return

    default_currency = frappe.db.get_value("Company", company, "default_currency") or "INR"
    print(f"\n[seed] Using company: {company}  |  currency: {default_currency}\n")

    try:
        _ensure_momentum_settings()
        dept_map = _seed_departments(company)
        _seed_designations()
        activity_types = _seed_activity_types()
        employees = _seed_employees(company, dept_map)
        customer_map = _seed_customers(company)
        projects, tasks = _seed_projects(company, customer_map)

        # Build project → tasks mapping for timesheet linking
        task_map = {}
        for task_name in tasks:
            project = frappe.db.get_value("Task", task_name, "project")
            if project not in task_map:
                task_map[project] = []
            task_map[project].append(task_name)

        _seed_timesheets(company, employees, projects, tasks, activity_types, task_map)
        _seed_sales_invoices(company, projects, default_currency)
        _seed_services_snapshots(company)

        try:
            _seed_manufacturing(company, employees)
        except Exception as mfg_err:
            print(f"  [seed] Manufacturing seed skipped: {mfg_err}")
            print("  [seed] Enable Manufacturing in ERPNext to seed Work Centers, BOMs, and Job Cards.")
    except Exception as e:
        frappe.db.rollback()
        print(f"\n[seed] ERROR: {e}\n")
        raise

    frappe.db.commit()

    # Write sentinel only after full success
    open(sentinel, "w").close()
    print("\n[seed] Done. Sentinel written. All demo data is in place.\n")


# ── Momentum Settings ──────────────────────────────────────────────────────────


def _ensure_momentum_settings():
    """Turn on both packs so Services and Manufacturing dashboards have data."""
    print("[seed] Momentum Settings...")
    settings = frappe.get_single("Momentum Settings")
    dirty = False
    if not settings.enable_services_pack:
        settings.enable_services_pack = 1
        dirty = True
    if not settings.enable_manufacturing_pack:
        settings.enable_manufacturing_pack = 1
        dirty = True
    if dirty:
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        print("  + Enabled Services and Manufacturing packs")
    else:
        print("  ~ Packs already enabled")


# ── Departments ────────────────────────────────────────────────────────────────


def _seed_departments(company):
    """Create departments and return a dict of {short_name: record_name}."""
    print("[seed] Departments...")
    dept_map = {}
    for dept in ["Engineering", "Design"]:
        existing_name = frappe.db.get_value(
            "Department", {"department_name": dept, "company": company}, "name"
        )
        if existing_name:
            print(f"  ~ Department already exists: {existing_name}")
            dept_map[dept] = existing_name
        else:
            doc = frappe.get_doc({
                "doctype": "Department",
                "department_name": dept,
                "company": company,
                "is_group": 0,
            })
            doc.insert(ignore_permissions=True)
            print(f"  + Department: {doc.name}")
            dept_map[dept] = doc.name
    frappe.db.commit()
    return dept_map


# ── Designations ──────────────────────────────────────────────────────────────


def _seed_designations():
    print("[seed] Designations...")
    designations = [
        "Senior Developer", "Developer", "UI Designer", "Tech Lead", "Project Manager",
    ]
    for name in designations:
        if not _exists("Designation", {"designation_name": name}):
            frappe.get_doc({
                "doctype": "Designation",
                "designation_name": name,
            }).insert(ignore_permissions=True)
            print(f"  + Designation: {name}")
        else:
            print(f"  ~ Designation already exists: {name}")
    frappe.db.commit()


# ── Activity Types ─────────────────────────────────────────────────────────────


def _seed_activity_types():
    print("[seed] Activity Types...")
    types = [
        {"activity_type": "Development", "billing_rate": 2500, "costing_rate": 1500},
        {"activity_type": "Design",      "billing_rate": 2000, "costing_rate": 1200},
        {"activity_type": "Support",     "billing_rate": 1500, "costing_rate": 900},
        {"activity_type": "Management",  "billing_rate": 3000, "costing_rate": 1800},
    ]
    names = []
    for at in types:
        name = at["activity_type"]
        if not _exists("Activity Type", {"activity_type": name}):
            frappe.get_doc({
                "doctype": "Activity Type",
                "activity_type": name,
                "billing_rate": at["billing_rate"],
                "costing_rate": at["costing_rate"],
            }).insert(ignore_permissions=True)
            print(f"  + Activity Type: {name}")
        else:
            print(f"  ~ Activity Type already exists: {name}")
        names.append(name)
    frappe.db.commit()
    return names


# ── Employees ──────────────────────────────────────────────────────────────────


def _seed_employees(company, dept_map):
    print("[seed] Employees...")
    seed_employees = [
        {"first_name": "Aisha",  "last_name": "Mehta",    "dept_key": "Engineering", "designation": "Senior Developer", "dob_years_ago": 32},
        {"first_name": "Rohan",  "last_name": "Sharma",   "dept_key": "Engineering", "designation": "Developer",        "dob_years_ago": 27},
        {"first_name": "Priya",  "last_name": "Nair",     "dept_key": "Design",      "designation": "UI Designer",      "dob_years_ago": 29},
        {"first_name": "Vikram", "last_name": "Joshi",    "dept_key": "Engineering", "designation": "Tech Lead",        "dob_years_ago": 36},
        {"first_name": "Sneha",  "last_name": "Kulkarni", "dept_key": "Design",      "designation": "Project Manager",  "dob_years_ago": 31},
    ]
    employee_names = []
    for i, emp in enumerate(seed_employees):
        full_name = f"{emp['first_name']} {emp['last_name']}"
        existing = frappe.db.get_value(
            "Employee", {"employee_name": full_name, "company": company}, "name"
        )
        if existing:
            print(f"  ~ Employee already exists: {full_name}")
            employee_names.append(existing)
            continue

        # Use the actual Department record name from dept_map (e.g. "Engineering - Fafadia Tech")
        dept_name = dept_map.get(emp["dept_key"], emp["dept_key"])

        doc = frappe.get_doc({
            "doctype": "Employee",
            "first_name": emp["first_name"],
            "last_name": emp["last_name"],
            "employee_name": full_name,
            "company": company,
            "department": dept_name,
            "designation": emp["designation"],
            "gender": "Female" if emp["first_name"] in ("Aisha", "Priya", "Sneha") else "Male",
            "date_of_birth": date.today() - timedelta(days=365 * emp["dob_years_ago"]),
            "date_of_joining": date.today() - timedelta(days=365 * (i + 1)),
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)
        print(f"  + Employee: {full_name} ({doc.name})")
        employee_names.append(doc.name)

    frappe.db.commit()
    return employee_names


# ── Customers ──────────────────────────────────────────────────────────────────


def _seed_customers(company):
    """Create demo customers and return a dict of {customer_name_label: record_name}."""
    print("[seed] Customers...")
    customers = [
        {"customer_name": "Demo Client A"},
        {"customer_name": "Demo Client B"},
        {"customer_name": "Demo Client C"},
        {"customer_name": "Demo Client D"},
    ]
    customer_names = {}
    default_customer_group = (
        frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial"
    )
    default_territory = (
        frappe.db.get_value("Territory", {}, "name") or "All Territories"
    )
    for c in customers:
        label = c["customer_name"]
        existing = frappe.db.get_value("Customer", {"customer_name": label}, "name")
        if existing:
            print(f"  ~ Customer already exists: {label}")
            customer_names[label] = existing
        else:
            doc = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": label,
                "customer_group": default_customer_group,
                "territory": default_territory,
                "customer_type": "Company",
            })
            doc.insert(ignore_permissions=True)
            print(f"  + Customer: {doc.name}")
            customer_names[label] = doc.name
    frappe.db.commit()
    return customer_names


# ── Projects & Tasks ───────────────────────────────────────────────────────────


def _seed_projects(company, customer_map):
    print("[seed] Projects and Tasks...")
    today = date.today()

    # Map project_name label → customer label
    _project_customer_map = {
        "Website Redesign — Demo Client A": "Demo Client A",
        "ERP Implementation — Demo Client B": "Demo Client B",
        "Mobile App — Demo Client C": "Demo Client C",
        "Support Retainer — Demo Client D": "Demo Client D",
    }

    seed_projects = [
        {
            "project_name": "Website Redesign — Demo Client A",
            "estimated_costing": 650000,
            "tasks": [
                {"subject": "Discovery & Wireframes", "expected_time": 40, "status": "Completed"},
                {"subject": "UI Design", "expected_time": 80, "status": "Completed"},
                {"subject": "Frontend Development", "expected_time": 120, "status": "Working"},
                {"subject": "QA & Launch", "expected_time": 24, "status": "Open"},
            ],
        },
        {
            "project_name": "ERP Implementation — Demo Client B",
            "estimated_costing": 2500000,
            "tasks": [
                {"subject": "Requirements Gathering", "expected_time": 60, "status": "Completed"},
                {"subject": "Configuration", "expected_time": 160, "status": "Working"},
                {"subject": "Data Migration", "expected_time": 80, "status": "Working"},
                {"subject": "UAT", "expected_time": 40, "status": "Open"},
                {"subject": "Go-Live Support", "expected_time": 32, "status": "Open"},
            ],
        },
        {
            "project_name": "Mobile App — Demo Client C",
            "estimated_costing": 850000,
            "tasks": [
                {"subject": "Product Design", "expected_time": 48, "status": "Completed"},
                {"subject": "Backend API", "expected_time": 100, "status": "Working"},
                {"subject": "iOS Development", "expected_time": 80, "status": "Working"},
                {"subject": "Android Development", "expected_time": 16, "status": "Open"},
            ],
        },
        {
            "project_name": "Support Retainer — Demo Client D",
            "estimated_costing": 200000,
            "tasks": [
                {"subject": "Monthly Support Hours", "expected_time": 40, "status": "Working"},
                {"subject": "Bug Fixes", "expected_time": 16, "status": "Working"},
                {"subject": "Performance Optimisation", "expected_time": 80, "status": "Open"},
            ],
        },
    ]

    project_names = []
    task_names = []

    for proj in seed_projects:
        pname = proj["project_name"]
        customer_label = _project_customer_map.get(pname)
        customer_name = customer_map.get(customer_label) if customer_label else None

        existing_proj = frappe.db.get_value("Project", {"project_name": pname, "company": company}, "name")
        if existing_proj:
            print(f"  ~ Project already exists: {pname}")
            project_names.append(existing_proj)
            # Keep budget in sync with the demo profile so status flags stay meaningful
            frappe.db.set_value("Project", existing_proj, "estimated_costing", proj["estimated_costing"])
            if customer_name and not frappe.db.get_value("Project", existing_proj, "customer"):
                frappe.db.set_value("Project", existing_proj, "customer", customer_name)
        else:
            doc = frappe.get_doc({
                "doctype": "Project",
                "project_name": pname,
                "company": company,
                "status": "Open",
                "estimated_costing": proj["estimated_costing"],
                "expected_start_date": today - timedelta(days=90),
                "expected_end_date": today + timedelta(days=90),
                "percent_complete_method": "Task Completion",
                "customer": customer_name,
            })
            doc.insert(ignore_permissions=True)
            print(f"  + Project: {pname}")
            project_names.append(doc.name)
            existing_proj = doc.name

        for task in proj["tasks"]:
            task_subject = task["subject"]
            existing_task = frappe.db.get_value(
                "Task",
                {"subject": task_subject, "project": existing_proj},
                "name",
            )
            if existing_task:
                frappe.db.set_value("Task", existing_task, {
                    "expected_time": task["expected_time"],
                    "status": task["status"],
                })
                task_names.append(existing_task)
            else:
                tdoc = frappe.get_doc({
                    "doctype": "Task",
                    "subject": task_subject,
                    "project": existing_proj,
                    "status": task["status"],
                    "expected_time": task["expected_time"],
                    "exp_start_date": today - timedelta(days=60),
                    "exp_end_date": today + timedelta(days=30),
                })
                tdoc.insert(ignore_permissions=True)
                task_names.append(tdoc.name)

    frappe.db.commit()
    return project_names, task_names


# ── Timesheets ─────────────────────────────────────────────────────────────────


# Distinct demo profiles so utilization, bench, and compliance reports have
# contrast instead of every employee looking the same.
# project_weights follow seed project order: Website, ERP, Mobile, Support.
_EMPLOYEE_PROFILES = [
    {  # Aisha Mehta — Senior Developer, fully loaded
        "hours": (7.5, 8.5),
        "billable_p": 0.92,
        "skip_weeks": set(),
        "activities": ["Development", "Development", "Development", "Management"],
        "project_weights": [0.55, 0.25, 0.10, 0.10],
    },
    {  # Rohan Sharma — Developer
        "hours": (7.0, 8.0),
        "billable_p": 0.85,
        "skip_weeks": set(),
        "activities": ["Development", "Development", "Support"],
        "project_weights": [0.10, 0.55, 0.25, 0.10],
    },
    {  # Priya Nair — UI Designer, below utilization target
        "hours": (6.5, 8.0),
        "billable_p": 0.68,
        "skip_weeks": {2},
        "activities": ["Design", "Design", "Design", "Support"],
        "project_weights": [0.50, 0.05, 0.40, 0.05],
    },
    {  # Vikram Joshi — Tech Lead
        "hours": (7.5, 8.5),
        "billable_p": 0.88,
        "skip_weeks": set(),
        "activities": ["Development", "Management", "Development"],
        "project_weights": [0.10, 0.45, 0.35, 0.10],
    },
    {  # Sneha Kulkarni — Project Manager, more non-billable + missing weeks
        "hours": (5.0, 6.5),
        "billable_p": 0.55,
        "skip_weeks": {1, 8},
        "activities": ["Management", "Management", "Support"],
        "project_weights": [0.20, 0.30, 0.20, 0.30],
    },
]


def _seed_timesheets(company, employees, projects, tasks, activity_types, task_map):
    """
    Create one Timesheet per employee per week for the last 90 days.
    Each timesheet has 5 Timesheet Detail rows (Mon–Fri).

    Hours, billable mix, project affinity, and skipped weeks come from
    _EMPLOYEE_PROFILES so Utilization, Bench, Compliance, and Client Effort
    reports have a realistic spread — not five identical employees.
    """
    print("[seed] Timesheets (this may take a moment)...")
    random.seed(42)

    today = date.today()
    period_start = today - timedelta(days=90)

    # Find the Monday of the week containing period_start
    week_start = period_start - timedelta(days=period_start.weekday())
    weeks = []
    while week_start <= today:
        weeks.append(week_start)
        week_start += timedelta(weeks=1)

    total_created = 0
    total_skipped = 0

    for emp_idx, employee in enumerate(employees):
        profile = _EMPLOYEE_PROFILES[emp_idx % len(_EMPLOYEE_PROFILES)]

        # Idempotency: if this employee already has any timesheets, skip entirely.
        # This avoids Frappe's overlap validation when partial data exists from
        # a prior run.
        existing_count = frappe.db.count("Timesheet", {"employee": employee, "company": company})
        if existing_count:
            total_skipped += existing_count
            continue

        for week_index, week_monday in enumerate(weeks):
            if week_index in profile["skip_weeks"]:
                continue

            week_end = week_monday + timedelta(days=4)  # Friday

            # Skip if no overlap with our 90-day window
            if week_end < period_start:
                continue

            # Build one log row per working day in this week
            time_logs = []
            for work_date in _workdays(
                max(week_monday, period_start),
                min(week_end, today - timedelta(days=1)),
            ):
                hours = random.uniform(*profile["hours"])
                start_hour = 9
                end_hour_decimal = start_hour + hours
                end_hour = int(end_hour_decimal)
                end_minute = int((end_hour_decimal - end_hour) * 60)

                weights = profile["project_weights"][:len(projects)]
                if len(weights) < len(projects):
                    weights = weights + [0.1] * (len(projects) - len(weights))
                project = random.choices(projects, weights=weights, k=1)[0]
                activity = random.choice(profile["activities"])
                if activity not in activity_types:
                    activity = random.choice(activity_types)
                billable = random.random() < profile["billable_p"]

                # Most rows link to a task so Estimate vs Actual is populated
                task = None
                if random.random() < 0.75 and project in task_map:
                    task = random.choice(task_map[project])

                log = {
                    "doctype": "Timesheet Detail",
                    "activity_type": activity,
                    "project": project,
                    "from_time": _dt(work_date, start_hour),
                    "to_time": _dt(work_date, end_hour, end_minute),
                    "hours": round(hours, 2),
                    "is_billable": 1 if billable else 0,
                }
                if task:
                    log["task"] = task
                time_logs.append(log)

            if not time_logs:
                continue

            ts = frappe.get_doc({
                "doctype": "Timesheet",
                "employee": employee,
                "company": company,
                "start_date": week_monday,
                "end_date": week_end,
                "time_logs": time_logs,
            })
            ts.insert(ignore_permissions=True)
            ts.submit()
            total_created += 1

    frappe.db.commit()
    print(f"  + Timesheets created: {total_created}  (skipped existing: {total_skipped})")


# ── Sales Invoices ─────────────────────────────────────────────────────────────


def _seed_sales_invoices(company, projects, currency):
    """Create submitted Sales Invoices for the first 3 projects, staggered in time.

    The fourth project is left unbilled so Unbilled Hours (WIP) has a fat 30+ bucket
    and Realization Rate shows a 0% row alongside partially-invoiced work.
    """
    print("[seed] Sales Invoices...")

    income_account = (
        frappe.db.get_value("Account", {"account_type": "Income Account", "company": company, "is_group": 0}, "name")
        or frappe.db.get_value("Account", {"root_type": "Income", "company": company, "is_group": 0}, "name")
    )

    # Stagger posting dates so the invoiced-amount dashboard trend steps up.
    invoice_plan = [
        {"days_ago": 50, "fraction": 0.35},
        {"days_ago": 22, "fraction": 0.25},
        {"days_ago": 6,  "fraction": 0.45},
    ]

    for i, project_name in enumerate(projects[:3]):
        project_data = frappe.db.get_value(
            "Project",
            project_name,
            ["project_name", "customer", "estimated_costing"],
            as_dict=True,
        )
        if not project_data or not project_data.customer:
            print(f"  ! Project {project_name} has no customer — skipping Sales Invoice")
            continue

        existing = frappe.db.get_value(
            "Sales Invoice",
            {"project": project_name, "docstatus": ["!=", 2]},
            "name",
        )
        if existing:
            print(f"  ~ Sales Invoice already exists for project {project_name}")
            continue

        plan = invoice_plan[i]
        posting_date = date.today() - timedelta(days=plan["days_ago"])
        invoice_amount = round((project_data.estimated_costing or 0) * plan["fraction"], 2)

        si = frappe.get_doc({
            "doctype": "Sales Invoice",
            "company": company,
            "customer": project_data.customer,
            "project": project_name,
            "currency": currency,
            "posting_date": str(posting_date),
            "set_posting_time": 1,
            "due_date": str(posting_date + timedelta(days=30)),
            "items": [
                {
                    "item_name": f"Services — {project_data.project_name}",
                    "description": f"Professional services for {project_data.project_name}",
                    "qty": 1,
                    "rate": invoice_amount,
                    "uom": "Nos",
                    "income_account": income_account,
                }
            ],
        })
        try:
            si.insert(ignore_permissions=True)
            si.submit()
            print(
                f"  + Sales Invoice: {si.name} (project: {project_name}, "
                f"amount: {invoice_amount}, posted {posting_date})"
            )
        except Exception as e:
            print(f"  ! Could not create Sales Invoice for {project_name}: {e}")

    frappe.db.commit()


# ── Services snapshots (project + utilization) ─────────────────────────────────


def _seed_services_snapshots(company):
    """
    Rebuild Momentum Project Snapshot and Employee Utilization Snapshot for
    every weekday in the last 90 days. Charts on all three dashboards read
    these doctypes — without them the Services and Executive dashboards are empty.
    """
    print("[seed] Momentum Services Snapshots (90-day backfill)...")
    from momentum.momentum.aggregation.services import (
        rebuild_project_snapshot,
        rebuild_utilization_snapshot,
    )

    today = date.today()
    created = 0
    for days_ago in range(90, 0, -1):
        target_date = today - timedelta(days=days_ago)
        if target_date.weekday() >= 5:
            continue
        try:
            rebuild_project_snapshot(str(target_date), company)
            rebuild_utilization_snapshot(str(target_date), company)
            created += 1
        except Exception as e:
            print(f"  ! Snapshot error for {target_date}: {e}")

    print(f"  + Project + utilization snapshots built for {created} working days")


# ── Manufacturing demo data ────────────────────────────────────────────────────


def _seed_manufacturing(company, employees=None):
    print("[seed] Manufacturing demo data...")
    random.seed(42)

    _seed_work_centers(company)
    _seed_operations(company)
    item_code = _seed_item(company)
    bom_no = _seed_bom(company, item_code)
    _seed_work_orders(company, item_code, bom_no, employees or [])
    _seed_operation_efficiency_snapshots(company)

    frappe.db.commit()


def _seed_work_centers(company):
    work_centers = [
        {"workstation_name": "Assembly Line A", "production_capacity": 8},
        {"workstation_name": "Quality Control",  "production_capacity": 4},
    ]
    for wc in work_centers:
        name = wc["workstation_name"]
        if not _exists("Workstation", {"workstation_name": name}):
            frappe.get_doc({
                "doctype": "Workstation",
                "workstation_name": name,
                "hour_rate": 500,
                "production_capacity": wc["production_capacity"],
            }).insert(ignore_permissions=True)
            print(f"  + Workstation: {name}")
        else:
            print(f"  ~ Workstation already exists: {name}")


def _seed_operations(company):
    operations = ["Assembly", "Quality Inspection"]
    for op_name in operations:
        if not _exists("Operation", {"name": op_name}):
            frappe.get_doc({
                "doctype": "Operation",
                "name": op_name,
                "workstation": op_name.split()[0] + " Line A" if "Assembly" in op_name else "Quality Control",
            }).insert(ignore_permissions=True)
            print(f"  + Operation: {op_name}")
        else:
            print(f"  ~ Operation already exists: {op_name}")


def _seed_item(company):
    item_code = "MOMENTUM-DEMO-WIDGET"
    if not _exists("Item", {"item_code": item_code}):
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": "Demo Widget (Momentum Seed)",
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "Products",
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "include_item_in_manufacturing": 1,
        })
        item.insert(ignore_permissions=True)
        print(f"  + Item: {item_code}")
    else:
        print(f"  ~ Item already exists: {item_code}")
    return item_code


def _seed_bom(company, item_code):
    existing_bom = frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1},
        "name",
    )
    if existing_bom:
        print(f"  ~ BOM already exists: {existing_bom}")
        return existing_bom

    # Check for an unsubmitted draft BOM too
    draft_bom = frappe.db.get_value(
        "BOM",
        {"item": item_code, "docstatus": 0},
        "name",
    )
    if draft_bom:
        print(f"  ~ Draft BOM already exists: {draft_bom}")
        return draft_bom

    assembly_wc = frappe.db.get_value("Workstation", {"workstation_name": "Assembly Line A"}, "name")
    qc_wc = frappe.db.get_value("Workstation", {"workstation_name": "Quality Control"}, "name")

    bom = frappe.get_doc({
        "doctype": "BOM",
        "item": item_code,
        "company": company,
        "quantity": 1,
        "is_default": 1,
        "is_active": 1,
        "with_operations": 1,
        "operations": [
            {
                "operation": "Assembly",
                "workstation": assembly_wc,
                "time_in_mins": 60,
                "operating_cost": 500,
            },
            {
                "operation": "Quality Inspection",
                "workstation": qc_wc,
                "time_in_mins": 30,
                "operating_cost": 250,
            },
        ],
    })
    bom.insert(ignore_permissions=True)
    bom.submit()
    print(f"  + BOM: {bom.name}")
    return bom.name


def _seed_work_orders(company, item_code, bom_no, employees):
    today = date.today()
    # Spread WOs across the quarter with gaps so workstation time logs don't overlap,
    # and a mix of efficiency factors so Operation Efficiency / At-Risk have contrast.
    work_orders = [
        {"qty": 40, "days_ago": 80, "efficiency": 0.72},  # efficient
        {"qty": 30, "days_ago": 60, "efficiency": 1.28},  # overrun
        {"qty": 45, "days_ago": 40, "efficiency": 0.95},  # on target
        {"qty": 25, "days_ago": 22, "efficiency": 1.20},  # overrun
        {"qty": 35, "days_ago": 8,  "efficiency": 0.82},  # efficient
    ]
    operators = employees[:3] if employees else []

    for wo_def in work_orders:
        planned_start = today - timedelta(days=wo_def["days_ago"])
        existing = frappe.db.get_value(
            "Work Order",
            {
                "production_item": item_code,
                "planned_start_date": planned_start,
                "company": company,
            },
            "name",
        )
        if existing:
            print(f"  ~ Work Order already exists for {planned_start}")
            _seed_job_cards(existing, planned_start, company, operators, wo_def)
            continue

        # Warehouses — pick the first matching ones
        wip_warehouse = frappe.db.get_value(
            "Warehouse", {"warehouse_type": "Work In Progress", "company": company}, "name"
        ) or frappe.db.get_value("Warehouse", {"company": company}, "name")

        fg_warehouse = frappe.db.get_value(
            "Warehouse", {"warehouse_type": "Finished Goods", "company": company}, "name"
        ) or wip_warehouse

        wo = frappe.get_doc({
            "doctype": "Work Order",
            "production_item": item_code,
            "bom_no": bom_no,
            "qty": wo_def["qty"],
            "company": company,
            "planned_start_date": planned_start,
            "wip_warehouse": wip_warehouse,
            "fg_warehouse": fg_warehouse,
        })
        wo.insert(ignore_permissions=True)
        wo.submit()
        frappe.db.set_value("Work Order", wo.name, "status", "In Process")
        print(f"  + Work Order: {wo.name} ({wo_def['qty']} units, started {planned_start})")

        _align_work_order_operation_standards(wo.name, wo_def["qty"])
        _seed_job_cards(wo.name, planned_start, company, operators, wo_def)


def _align_work_order_operation_standards(work_order_name, qty):
    """
    ERPNext sometimes stores WO operation time as the BOM per-unit figure.
    Scale it by qty so efficiency % = standard / actual is in a realistic 70–130 range.
    """
    ops = frappe.get_all(
        "Work Order Operation",
        filters={"parent": work_order_name},
        fields=["name", "time_in_mins", "planned_operating_cost"],
    )
    for op in ops:
        std_mins = op.get("time_in_mins") or 0
        std_cost = op.get("planned_operating_cost") or 0
        # Per-unit leftover: Assembly BOM is 60 mins, QC is 30. Scale if too small.
        if qty and std_mins and std_mins < qty * 10:
            frappe.db.set_value(
                "Work Order Operation",
                op["name"],
                {
                    "time_in_mins": std_mins * qty,
                    "planned_operating_cost": (std_cost or 0) * qty,
                },
                update_modified=False,
            )


def _dt_offset(d: date, hour: float):
    """Datetime string from a date + fractional hour, overflowing past midnight."""
    extra_days, hour = divmod(hour, 24)
    whole = int(hour)
    minute = int(round((hour - whole) * 60))
    if minute == 60:
        whole += 1
        minute = 0
    target = d + timedelta(days=int(extra_days))
    return _dt(target, whole, minute)


def _job_card_time_logs(planned_start, std_mins, factor, employees, qty):
    """
    Spread actual minutes over several working days with a mix of shifts.

    factor < 1 → faster than standard (high efficiency)
    factor > 1 → slower than standard (cost overrun, possible overtime)
    """
    actual_total = max(45.0, float(std_mins) * factor)
    jc_has_emp = frappe.get_meta("Job Card Time Log").has_field("employee")

    # Shift pattern cycles so Morning / Afternoon / Evening all appear,
    # and at least one day runs long enough to flag overtime (> 8h).
    # (start_hour, target_hours)
    shift_pattern = [
        (8, 9.5),   # Morning overtime
        (8, 7.5),   # Morning
        (14, 5.0),  # Afternoon
        (19, 3.5),  # Evening/Night
        (9, 8.0),   # Morning full day
        (8, 7.0),
        (14, 4.5),
        (19, 3.0),
    ]

    logs = []
    remaining_mins = actual_total
    remaining_qty = float(qty)
    work_date = planned_start + timedelta(days=1)
    day_i = 0

    while remaining_mins > 5 and work_date < date.today() and day_i < 12:
        if work_date.weekday() >= 5:
            work_date += timedelta(days=1)
            continue

        start_hour, target_hours = shift_pattern[day_i % len(shift_pattern)]
        mins = min(remaining_mins, target_hours * 60)
        # Last chunk: dump whatever is left, capped at 10 hours
        if remaining_mins - mins < 30:
            mins = min(remaining_mins, 10 * 60)

        completed = remaining_qty if remaining_mins - mins < 30 else max(
            1.0, round(qty * (mins / actual_total), 2)
        )
        remaining_qty = max(0.0, remaining_qty - completed)

        log = {
            "from_time": _dt(work_date, start_hour),
            "to_time": _dt_offset(work_date, start_hour + mins / 60.0),
            "completed_qty": completed,
            "time_in_mins": round(mins, 2),
        }
        if jc_has_emp and employees:
            log["employee"] = employees[day_i % len(employees)]
        logs.append(log)

        remaining_mins -= mins
        work_date += timedelta(days=1)
        day_i += 1

    return logs


def _seed_job_cards(work_order_name, planned_start, company, employees, wo_def):
    """Create (or fill) Job Cards with multi-day time logs for a Work Order."""
    operations_on_wo = frappe.get_all(
        "Work Order Operation",
        filters={"parent": work_order_name},
        fields=["name", "operation", "workstation", "time_in_mins"],
    )

    jc_meta = frappe.get_meta("Job Card")
    qty = wo_def.get("qty") or 1
    factor = wo_def.get("efficiency") or 1.0
    wip_warehouse = frappe.db.get_value(
        "Warehouse", {"warehouse_type": "Work In Progress", "company": company}, "name"
    ) or frappe.db.get_value("Warehouse", {"company": company}, "name")

    for op in operations_on_wo:
        existing_jc = frappe.db.get_value(
            "Job Card",
            {
                "work_order": work_order_name,
                "operation": op["operation"],
                "docstatus": ["<", 2],
            },
            "name",
        )
        if existing_jc:
            docstatus = frappe.db.get_value("Job Card", existing_jc, "docstatus")
            has_logs = frappe.db.count("Job Card Time Log", {"parent": existing_jc})
            # Submitted with time already logged — leave it alone.
            if docstatus == 1 and has_logs:
                continue
            # Submitted but empty (ERPNext auto-creates these on WO submit) — cancel
            # so we can insert a card with real time logs.
            if docstatus == 1 and not has_logs:
                try:
                    frappe.get_doc("Job Card", existing_jc).cancel()
                    existing_jc = None
                except Exception as e:
                    print(f"    ! Could not cancel empty Job Card {existing_jc}: {e}")
                    continue
            else:
                jc = frappe.get_doc("Job Card", existing_jc)

        if not existing_jc:
            jc_dict = {
                "doctype": "Job Card",
                "work_order": work_order_name,
                "operation": op["operation"],
                "workstation": op["workstation"],
                "company": company,
            }
            if jc_meta.has_field("for_quantity"):
                jc_dict["for_quantity"] = qty
            if jc_meta.has_field("posting_date"):
                jc_dict["posting_date"] = str(planned_start)
            if jc_meta.has_field("operation_id"):
                jc_dict["operation_id"] = op["name"]
            if jc_meta.has_field("wip_warehouse") and wip_warehouse:
                jc_dict["wip_warehouse"] = wip_warehouse
            jc = frappe.get_doc(jc_dict)

        std_mins = op.get("time_in_mins") or 60
        # QC typically runs after assembly — offset by a couple of days
        start = planned_start + timedelta(days=2) if "Quality" in (op["operation"] or "") else planned_start
        for log in _job_card_time_logs(start, std_mins, factor, employees, qty):
            jc.append("time_logs", log)

        if not jc.time_logs:
            continue

        try:
            if existing_jc:
                jc.save(ignore_permissions=True)
            else:
                jc.insert(ignore_permissions=True)
            jc.submit()
            print(
                f"    + Job Card: {jc.name} ({op['operation']}, "
                f"{len(jc.time_logs)} logs, factor={factor})"
            )
        except Exception as e:
            print(f"    ! Could not submit Job Card ({op['operation']}): {e}")


# ── Operation Efficiency Snapshots ─────────────────────────────────────────────


def _seed_operation_efficiency_snapshots(company):
    """
    Rebuild Momentum Operation Efficiency Snapshots for every date on which
    a submitted Job Card time log exists.
    """
    print("[seed] Momentum Operation Efficiency Snapshots...")
    from momentum.momentum.aggregation.manufacturing import rebuild_operation_efficiency_snapshot

    dates = frappe.db.sql("""
        SELECT DISTINCT DATE(jctl.from_time) AS work_date
        FROM `tabJob Card Time Log` jctl
        JOIN `tabJob Card` jc ON jc.name = jctl.parent
        WHERE jc.docstatus = 1
          AND jc.company = %(company)s
        ORDER BY work_date
    """, {"company": company}, as_dict=True)

    created = 0
    for row in dates:
        target_date = str(row["work_date"])
        try:
            rebuild_operation_efficiency_snapshot(target_date, company)
            created += 1
        except Exception as e:
            print(f"  ! Snapshot error for {target_date}: {e}")

    print(f"  + Operation efficiency snapshots built for {created} date(s)")


# ── Standalone re-seeders for existing installs ────────────────────────────────


def seed_dashboard_snapshots():
    """
    Rebuild Project, Utilization, and Operation Efficiency snapshots from
    whatever source documents already exist. Safe to run on a site that already
    has the sentinel file (does not recreate timesheets or job cards).

    Usage:
        bench --site <site> execute momentum.seed.seed_dashboard_snapshots
    """
    frappe.set_user("Administrator")
    company = frappe.db.get_value("Company", {}, "name")
    if not company:
        print("[seed] No company found — run the ERPNext setup wizard first.")
        return
    _ensure_momentum_settings()
    _seed_services_snapshots(company)
    _seed_operation_efficiency_snapshots(company)
    frappe.db.commit()
    print("[seed] Done.")


def seed_manufacturing_snapshots():
    """
    Standalone entry point for sites that already ran the full seed but need
    the Operation Efficiency Snapshots added (e.g. after upgrading Momentum).

    Usage:
        bench --site <site> execute momentum.seed.seed_manufacturing_snapshots
    """
    frappe.set_user("Administrator")
    company = frappe.db.get_value("Company", {}, "name")
    if not company:
        print("[seed] No company found — run the ERPNext setup wizard first.")
        return
    _seed_operation_efficiency_snapshots(company)
    frappe.db.commit()
    print("[seed] Done.")
