"""
Momentum aggregation services.

Provides functions to rebuild project and employee utilization snapshots.
Called by the Frappe scheduler daily, or manually for backfilling.
"""

import frappe


def rebuild_project_snapshot(target_date, company=None):
    """
    Delete existing Momentum Project Snapshot records for target_date (and company
    if provided), then recompute and insert fresh records for every open project.

    :param target_date: datetime.date or ISO string (YYYY-MM-DD)
    :param company: optional company filter
    """
    target_date = str(target_date)

    # ── Read settings ──────────────────────────────────────────────────────────
    settings = frappe.get_single("Momentum Settings")
    threshold = settings.budget_overrun_threshold_percent or 80

    # ── Delete existing snapshots for this date ────────────────────────────────
    delete_filters = {"date": target_date}
    if company:
        delete_filters["company"] = company
    frappe.db.delete("Momentum Project Snapshot", delete_filters)

    # ── Fetch open projects ────────────────────────────────────────────────────
    proj_filters = {"status": "Open"}
    if company:
        proj_filters["company"] = company
    projects = frappe.get_all(
        "Project",
        filters=proj_filters,
        fields=["name", "project_name", "company", "customer", "estimated_costing"],
    )

    for proj in projects:
        proj_name = proj["name"]
        proj_company = proj["company"]

        # ── Timesheet Detail aggregation for this project on target_date ───────
        ts_row = frappe.db.sql(
            """
            SELECT
                COALESCE(SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END), 0) AS billable_hours,
                COALESCE(SUM(CASE WHEN tsd.is_billable = 0 THEN tsd.hours ELSE 0 END), 0) AS non_billable_hours,
                COALESCE(SUM(tsd.hours * COALESCE(at.costing_rate, 0)), 0) AS total_cost,
                COALESCE(SUM(CASE WHEN tsd.is_billable = 1
                    THEN tsd.hours * COALESCE(at.billing_rate, 0) ELSE 0 END), 0
                ) AS billed_amount_at_standard_rate
            FROM `tabTimesheet Detail` tsd
            JOIN `tabTimesheet` ts ON ts.name = tsd.parent
            LEFT JOIN `tabActivity Type` at ON at.name = tsd.activity_type
            WHERE ts.docstatus = 1
              AND tsd.project = %(project)s
              AND DATE(tsd.from_time) = %(target_date)s
            """,
            {"project": proj_name, "target_date": target_date},
            as_dict=True,
        )

        agg = ts_row[0] if ts_row else {}
        billable_hours = agg.get("billable_hours") or 0
        non_billable_hours = agg.get("non_billable_hours") or 0
        total_cost = agg.get("total_cost") or 0
        billed_amount = agg.get("billed_amount_at_standard_rate") or 0

        # ── Actual invoiced amount (all time, not date-filtered) ───────────────
        inv_row = frappe.db.sql(
            """
            SELECT COALESCE(SUM(si.base_grand_total), 0) AS actual_invoiced
            FROM `tabSales Invoice` si
            WHERE si.project = %(project)s
              AND si.docstatus = 1
            """,
            {"project": proj_name},
            as_dict=True,
        )
        actual_invoiced = (inv_row[0].get("actual_invoiced") or 0) if inv_row else 0

        budget_amount = proj.get("estimated_costing") or 0

        # ── Determine status flag ──────────────────────────────────────────────
        if budget_amount and total_cost > budget_amount:
            status_flag = "Over Budget"
        elif budget_amount and total_cost > budget_amount * (threshold / 100):
            status_flag = "At Risk"
        else:
            status_flag = "On Track"

        # ── Insert snapshot ────────────────────────────────────────────────────
        snap = frappe.get_doc({
            "doctype": "Momentum Project Snapshot",
            "project": proj_name,
            "date": target_date,
            "company": proj_company,
            "billable_hours": round(billable_hours, 4),
            "non_billable_hours": round(non_billable_hours, 4),
            "total_cost": round(total_cost, 2),
            "billed_amount_at_standard_rate": round(billed_amount, 2),
            "actual_invoiced_amount": round(actual_invoiced, 2),
            "budget_hours": 0,
            "budget_amount": round(budget_amount, 2),
            "status_flag": status_flag,
        })
        snap.insert(ignore_permissions=True)

    frappe.db.commit()


def rebuild_utilization_snapshot(target_date, company=None):
    """
    Delete existing Momentum Employee Utilization Snapshot records for target_date
    (and company if provided), then recompute and insert fresh records for every
    active employee.

    :param target_date: datetime.date or ISO string (YYYY-MM-DD)
    :param company: optional company filter
    """
    target_date = str(target_date)

    # ── Read settings ──────────────────────────────────────────────────────────
    settings = frappe.get_single("Momentum Settings")
    std_hours = settings.standard_working_hours_per_day or 8.0

    # ── Delete existing snapshots ──────────────────────────────────────────────
    delete_filters = {"date": target_date}
    if company:
        delete_filters["company"] = company
    frappe.db.delete("Momentum Employee Utilization Snapshot", delete_filters)

    # ── Fetch active employees ─────────────────────────────────────────────────
    emp_filters = {"status": "Active"}
    if company:
        emp_filters["company"] = company
    employees = frappe.get_all(
        "Employee",
        filters=emp_filters,
        fields=["name", "company"],
    )

    for emp in employees:
        emp_name = emp["name"]
        emp_company = emp["company"]

        # ── Aggregate hours for this employee on target_date ───────────────────
        ts_row = frappe.db.sql(
            """
            SELECT
                COALESCE(SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END), 0) AS billable_hours,
                COALESCE(SUM(CASE WHEN tsd.is_billable = 0 THEN tsd.hours ELSE 0 END), 0) AS non_billable_hours
            FROM `tabTimesheet Detail` tsd
            JOIN `tabTimesheet` ts ON ts.name = tsd.parent
            WHERE ts.docstatus = 1
              AND ts.employee = %(employee)s
              AND DATE(tsd.from_time) = %(target_date)s
            """,
            {"employee": emp_name, "target_date": target_date},
            as_dict=True,
        )

        agg = ts_row[0] if ts_row else {}
        billable_hours = agg.get("billable_hours") or 0
        non_billable_hours = agg.get("non_billable_hours") or 0
        available_hours = std_hours
        utilization_percent = (billable_hours / available_hours * 100) if available_hours else 0
        overtime_hours = max(0, (billable_hours + non_billable_hours) - available_hours)

        snap = frappe.get_doc({
            "doctype": "Momentum Employee Utilization Snapshot",
            "employee": emp_name,
            "date": target_date,
            "company": emp_company,
            "available_hours": available_hours,
            "billable_hours": round(billable_hours, 4),
            "non_billable_hours": round(non_billable_hours, 4),
            "utilization_percent": round(utilization_percent, 2),
            "overtime_hours": round(overtime_hours, 4),
        })
        snap.insert(ignore_permissions=True)

    frappe.db.commit()


def run_daily_snapshots():
    """Called by Frappe scheduler daily. Rebuilds yesterday's snapshots."""
    from datetime import date, timedelta

    settings = frappe.get_single("Momentum Settings")
    yesterday = str(date.today() - timedelta(days=1))
    for company in frappe.get_all("Company", pluck="name"):
        if settings.enable_services_pack:
            rebuild_project_snapshot(yesterday, company)
            rebuild_utilization_snapshot(yesterday, company)
