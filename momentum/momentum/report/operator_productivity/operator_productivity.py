"""
Report: Operator Productivity
Shows actual vs standard time per operator/work-center/operation with efficiency %.
Employee may be NULL (seed data does not always set it); rows are grouped by
work_center + operation in that case.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "employee",           "label": "Employee",           "fieldtype": "Link",    "options": "Employee",   "width": 120},
        {"fieldname": "employee_name",      "label": "Employee Name",      "fieldtype": "Data",                             "width": 150},
        {"fieldname": "work_center",        "label": "Work Center",        "fieldtype": "Link",    "options": "Work Center","width": 140},
        {"fieldname": "operation",          "label": "Operation",          "fieldtype": "Data",                             "width": 130},
        {"fieldname": "actual_time_mins",   "label": "Actual Time (min)",  "fieldtype": "Float",                            "width": 130},
        {"fieldname": "completed_qty",      "label": "Completed Qty",      "fieldtype": "Float",                            "width": 110},
        {"fieldname": "standard_time_mins", "label": "Standard Time (min)","fieldtype": "Float",                            "width": 130},
        {"fieldname": "efficiency_percent", "label": "Efficiency %",       "fieldtype": "Percent",                          "width": 110},
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
            COALESCE(jc.employee, '') AS employee,
            COALESCE(emp.employee_name, '(Unassigned)') AS employee_name,
            jc.workstation AS work_center,
            jc.operation,
            ROUND(SUM(jctl.time_in_mins), 2) AS actual_time_mins,
            SUM(jctl.completed_qty) AS completed_qty,
            COALESCE(woo.time_in_mins, 0) AS standard_time_mins,
            ROUND(COALESCE(woo.time_in_mins, 0) / NULLIF(SUM(jctl.time_in_mins), 0) * 100, 2) AS efficiency_percent
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        LEFT JOIN `tabEmployee` emp ON emp.name = jc.employee
        LEFT JOIN `tabWork Order Operation` woo
            ON woo.parent = jc.work_order AND woo.operation = jc.operation
        WHERE {conditions}
        GROUP BY jc.employee, jc.workstation, jc.operation
        ORDER BY efficiency_percent ASC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)
    return columns, data
