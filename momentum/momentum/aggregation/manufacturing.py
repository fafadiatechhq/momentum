"""Momentum aggregation — manufacturing. Rebuilds Operation Efficiency Snapshots."""
import frappe


def rebuild_operation_efficiency_snapshot(target_date, company=None):
    target_date = str(target_date)
    delete_filters = {"date": target_date}
    if company:
        delete_filters["company"] = company
    frappe.db.delete("Momentum Operation Efficiency Snapshot", delete_filters)

    cond = (
        "jc.docstatus = 1"
        " AND DATE(jctl.from_time) = %(target_date)s"
        " AND IFNULL(jc.workstation, '') != ''"
    )
    params = {"target_date": target_date}
    if company:
        cond += " AND jc.company = %(company)s"
        params["company"] = company

    rows = frappe.db.sql(f"""
        SELECT
            jc.work_order,
            jc.operation,
            jc.workstation AS work_center,
            jc.company,
            COALESCE(woo.time_in_mins, 0) AS standard_time_mins,
            ROUND(SUM(jctl.time_in_mins), 4) AS actual_time_mins,
            ROUND(COALESCE(woo.time_in_mins, 0) / NULLIF(SUM(jctl.time_in_mins), 0) * 100, 2) AS efficiency_percent,
            ROUND(COALESCE(woo.planned_operating_cost, 0), 2) AS standard_cost,
            ROUND(SUM(jctl.time_in_mins) / 60.0 * COALESCE(wc.hour_rate, 0), 2) AS actual_cost
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        LEFT JOIN `tabWork Order Operation` woo
            ON woo.parent = jc.work_order AND woo.operation = jc.operation
        LEFT JOIN `tabWorkstation` wc ON wc.name = jc.workstation
        WHERE {cond}
        GROUP BY jc.work_order, jc.operation, jc.workstation, jc.company
    """, params, as_dict=True)

    for row in rows:
        if not row.get("work_center") or not row.get("work_order") or not row.get("operation"):
            continue
        actual_cost = row.get("actual_cost") or 0
        standard_cost = row.get("standard_cost") or 0
        try:
            snap = frappe.get_doc({
                "doctype": "Momentum Operation Efficiency Snapshot",
                "work_order": row["work_order"],
                "operation": row["operation"],
                "work_center": row["work_center"],
                "date": target_date,
                "company": row["company"],
                "standard_time_mins": row.get("standard_time_mins") or 0,
                "actual_time_mins": row.get("actual_time_mins") or 0,
                "efficiency_percent": row.get("efficiency_percent") or 0,
                "standard_cost": standard_cost,
                "actual_cost": actual_cost,
                "cost_variance": round(actual_cost - standard_cost, 2),
            })
            snap.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title=f"Operation snapshot insert failed ({target_date})",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()


def run_daily_manufacturing_snapshots():
    """Called by Frappe scheduler daily."""
    from datetime import date, timedelta
    settings = frappe.get_single("Momentum Settings")
    if not settings.enable_manufacturing_pack:
        return
    yesterday = str(date.today() - timedelta(days=1))
    for company in frappe.get_all("Company", pluck="name"):
        rebuild_operation_efficiency_snapshot(yesterday, company)
