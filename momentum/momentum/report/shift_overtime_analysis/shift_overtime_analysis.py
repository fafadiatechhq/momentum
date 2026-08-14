"""
Report: Shift & Overtime Analysis
Buckets job card time logs into Morning / Afternoon / Evening-Night shifts and
flags overtime based on Momentum Settings.standard_working_hours_per_day.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "work_center",    "label": "Work Center",    "fieldtype": "Link",  "options": "Work Center", "width": 160},
        {"fieldname": "work_date",      "label": "Date",           "fieldtype": "Date",                            "width": 110},
        {"fieldname": "shift",          "label": "Shift",          "fieldtype": "Data",                            "width": 120},
        {"fieldname": "total_hours",    "label": "Total Hours",    "fieldtype": "Float",                           "width": 110},
        {"fieldname": "overtime_hours", "label": "Overtime Hours", "fieldtype": "Float",                           "width": 120},
        {"fieldname": "is_overtime",    "label": "Overtime?",      "fieldtype": "Check",                           "width": 90},
    ]

    cond_parts = [
        "jc.docstatus = 1",
        "DATE(jctl.from_time) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("company"):
        cond_parts.append("jc.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("work_center"):
        cond_parts.append("jc.workstation = %(work_center)s")
        params["work_center"] = filters["work_center"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            jc.workstation AS work_center,
            DATE(jctl.from_time) AS work_date,
            CASE
                WHEN HOUR(jctl.from_time) < 12 THEN 'Morning'
                WHEN HOUR(jctl.from_time) < 18 THEN 'Afternoon'
                ELSE 'Evening/Night'
            END AS shift,
            ROUND(SUM(jctl.time_in_mins) / 60.0, 2) AS total_hours
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE {conditions}
        GROUP BY jc.workstation, DATE(jctl.from_time), shift
        ORDER BY work_date DESC, work_center, shift
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    settings = frappe.get_single("Momentum Settings")
    std_hours = getattr(settings, "standard_working_hours_per_day", None) or 8.0

    for row in data:
        total = row.get("total_hours") or 0.0
        overtime = round(max(0.0, total - std_hours), 2)
        row["overtime_hours"] = overtime
        row["is_overtime"] = 1 if overtime > 0 else 0

    return columns, data
