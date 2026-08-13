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
  - 5 Employees
  - 4 Projects with Tasks  (Services pack demo)
  - ~65 working-day timesheets spread over the last 90 days
  - 1 Item, 1 BOM, 2 Work Centers, 2 Operations,
    2 Work Orders, Job Cards per work order  (Manufacturing pack demo)
"""

import os
import random
from datetime import date, timedelta

import frappe

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


# ── Top-level seeder ───────────────────────────────────────────────────────────


def run():
    frappe.set_user("Administrator")

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
            "[seed] Complete the ERPNext setup wizard at http://localhost:8080,\n"
            "[seed] then run:  docker compose up  and seeding will resume automatically.\n"
        )
        return

    default_currency = frappe.db.get_value("Company", company, "default_currency") or "INR"
    print(f"\n[seed] Using company: {company}  |  currency: {default_currency}\n")

    try:
        dept_map = _seed_departments(company)
        _seed_designations()
        activity_types = _seed_activity_types()
        employees = _seed_employees(company, dept_map)
        projects, tasks = _seed_projects(company)
        _seed_timesheets(company, employees, projects, tasks, activity_types)
        try:
            _seed_manufacturing(company)
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


# ── Projects & Tasks ───────────────────────────────────────────────────────────


def _seed_projects(company):
    print("[seed] Projects and Tasks...")
    today = date.today()
    seed_projects = [
        {
            "project_name": "Website Redesign — Demo Client A",
            "estimated_costing": 800000,
            "tasks": ["Discovery & Wireframes", "UI Design", "Frontend Development", "QA & Launch"],
        },
        {
            "project_name": "ERP Implementation — Demo Client B",
            "estimated_costing": 1500000,
            "tasks": ["Requirements Gathering", "Configuration", "Data Migration", "UAT", "Go-Live Support"],
        },
        {
            "project_name": "Mobile App — Demo Client C",
            "estimated_costing": 600000,
            "tasks": ["Product Design", "Backend API", "iOS Development", "Android Development"],
        },
        {
            "project_name": "Support Retainer — Demo Client D",
            "estimated_costing": 300000,
            "tasks": ["Monthly Support Hours", "Bug Fixes", "Performance Optimisation"],
        },
    ]

    project_names = []
    task_names = []

    for proj in seed_projects:
        pname = proj["project_name"]
        existing_proj = frappe.db.get_value("Project", {"project_name": pname, "company": company}, "name")
        if existing_proj:
            print(f"  ~ Project already exists: {pname}")
            project_names.append(existing_proj)
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
            })
            doc.insert(ignore_permissions=True)
            print(f"  + Project: {pname}")
            project_names.append(doc.name)
            existing_proj = doc.name

        for task_subject in proj["tasks"]:
            existing_task = frappe.db.get_value(
                "Task",
                {"subject": task_subject, "project": existing_proj},
                "name",
            )
            if existing_task:
                task_names.append(existing_task)
            else:
                tdoc = frappe.get_doc({
                    "doctype": "Task",
                    "subject": task_subject,
                    "project": existing_proj,
                    "status": "Open",
                    "expected_time": random.choice([8, 16, 24, 40]),
                    "exp_start_date": today - timedelta(days=60),
                    "exp_end_date": today + timedelta(days=30),
                })
                tdoc.insert(ignore_permissions=True)
                task_names.append(tdoc.name)

    frappe.db.commit()
    return project_names, task_names


# ── Timesheets ─────────────────────────────────────────────────────────────────


def _seed_timesheets(company, employees, projects, tasks, activity_types):
    """
    Create one Timesheet per employee per week for the last 90 days.
    Each timesheet has 5 Timesheet Detail rows (Mon–Fri), 6–8 hours each.
    Skips a week if a timesheet for that employee + start-of-week already exists.
    """
    print("[seed] Timesheets (this may take a moment)...")

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

    for employee in employees:
        # Idempotency: if this employee already has any timesheets, skip entirely.
        # This avoids Frappe's overlap validation when partial data exists from
        # a prior run.
        existing_count = frappe.db.count("Timesheet", {"employee": employee, "company": company})
        if existing_count:
            total_skipped += existing_count
            continue

        for week_monday in weeks:
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
                hours = random.uniform(6.0, 8.5)
                start_hour = 9
                end_hour_decimal = start_hour + hours
                end_hour = int(end_hour_decimal)
                end_minute = int((end_hour_decimal - end_hour) * 60)

                project = random.choice(projects)
                activity = random.choice(activity_types)
                billable = random.random() > 0.15  # ~85% billable

                time_logs.append({
                    "doctype": "Timesheet Detail",
                    "activity_type": activity,
                    "project": project,
                    "from_time": _dt(work_date, start_hour),
                    "to_time": _dt(work_date, end_hour, end_minute),
                    "hours": round(hours, 2),
                    "is_billable": 1 if billable else 0,
                })

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


# ── Manufacturing demo data ────────────────────────────────────────────────────


def _seed_manufacturing(company):
    print("[seed] Manufacturing demo data...")

    _seed_work_centers(company)
    _seed_operations(company)
    item_code = _seed_item(company)
    bom_no = _seed_bom(company, item_code)
    _seed_work_orders(company, item_code, bom_no)

    frappe.db.commit()


def _seed_work_centers(company):
    work_centers = [
        {"work_center_name": "Assembly Line A", "capacity": 8},
        {"work_center_name": "Quality Control",  "capacity": 4},
    ]
    for wc in work_centers:
        name = wc["work_center_name"]
        if not _exists("Work Center", {"work_center_name": name, "company": company}):
            frappe.get_doc({
                "doctype": "Work Center",
                "work_center_name": name,
                "company": company,
                "hour_rate": 500,
                "capacity": wc["capacity"],
            }).insert(ignore_permissions=True)
            print(f"  + Work Center: {name}")
        else:
            print(f"  ~ Work Center already exists: {name}")


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

    assembly_wc = frappe.db.get_value("Work Center", {"work_center_name": "Assembly Line A"}, "name")
    qc_wc = frappe.db.get_value("Work Center", {"work_center_name": "Quality Control"}, "name")

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


def _seed_work_orders(company, item_code, bom_no):
    today = date.today()
    work_orders = [
        {"qty": 50, "days_ago": 30},
        {"qty": 30, "days_ago": 15},
    ]
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
            _seed_job_cards(existing, planned_start, company)
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

        _seed_job_cards(wo.name, planned_start, company)


def _seed_job_cards(work_order_name, planned_start, company):
    """Create Job Cards with time logs for the given Work Order if they don't exist."""
    operations_on_wo = frappe.get_all(
        "Work Order Operation",
        filters={"parent": work_order_name},
        fields=["name", "operation", "workstation"],
    )

    for op in operations_on_wo:
        existing_jc = frappe.db.get_value(
            "Job Card",
            {"work_order": work_order_name, "operation": op["operation"]},
            "name",
        )
        if existing_jc:
            continue

        # Create a simple job card with one time log
        work_date = planned_start + timedelta(days=1)
        actual_mins = random.randint(45, 90)  # realistic variation around standard

        jc = frappe.get_doc({
            "doctype": "Job Card",
            "work_order": work_order_name,
            "operation": op["operation"],
            "workstation": op["workstation"],
            "company": company,
            "time_logs": [
                {
                    "from_time": _dt(work_date, 9),
                    "to_time": _dt(work_date, 9 + actual_mins // 60, actual_mins % 60),
                    "completed_qty": 1,
                    "time_in_mins": actual_mins,
                }
            ],
        })
        jc.insert(ignore_permissions=True)
        jc.submit()
        print(f"    + Job Card: {jc.name} ({op['operation']}, {actual_mins} mins actual)")
