"""
Report: Utilization Summary
Shows billable vs total hours per employee with utilization % vs target.
"""

import frappe
from frappe.utils import add_months, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "employee",           "label": "Employee",           "fieldtype": "Link",    "options": "Employee",   "width": 120},
        {"fieldname": "employee_name",      "label": "Employee Name",      "fieldtype": "Data",                             "width": 150},
        {"fieldname": "department",         "label": "Department",         "fieldtype": "Link",    "options": "Department", "width": 120},
        {"fieldname": "total_hours",        "label": "Total Hours",        "fieldtype": "Float",                            "width": 100},
        {"fieldname": "billable_hours",     "label": "Billable Hours",     "fieldtype": "Float",                            "width": 110},
        {"fieldname": "non_billable_hours", "label": "Non-Billable Hours", "fieldtype": "Float",                            "width": 130},
        {"fieldname": "utilization_percent","label": "Utilization %",      "fieldtype": "Percent",                          "width": 110},
        {"fieldname": "target_percent",     "label": "Target %",           "fieldtype": "Percent",                          "width": 90},
        {"fieldname": "vs_target",          "label": "vs Target",          "fieldtype": "Float",                            "width": 100},
    ]

    cond_parts = [
        "ts.docstatus = 1",
        "DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.get("from_date") or add_months(today(), -1),
        "to_date": filters.get("to_date") or today(),
    }

    if filters.get("company"):
        cond_parts.append("ts.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        cond_parts.append("emp.department = %(department)s")
        params["department"] = filters["department"]

    if filters.get("employee"):
        cond_parts.append("ts.employee = %(employee)s")
        params["employee"] = filters["employee"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            emp.name AS employee,
            emp.employee_name,
            emp.department,
            ROUND(SUM(tsd.hours), 2) AS total_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END), 2) AS billable_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 0 THEN tsd.hours ELSE 0 END), 2) AS non_billable_hours,
            ROUND(
                SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END)
                / NULLIF(SUM(tsd.hours), 0) * 100, 2
            ) AS utilization_percent
        FROM `tabTimesheet` ts
        JOIN `tabTimesheet Detail` tsd ON tsd.parent = ts.name
        JOIN `tabEmployee` emp ON emp.name = ts.employee
        LEFT JOIN `tabDepartment` dept ON dept.name = emp.department
        WHERE {conditions}
        GROUP BY emp.name, emp.employee_name, emp.department
        ORDER BY utilization_percent DESC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    settings = frappe.get_single("Momentum Settings")
    target = settings.utilization_target_percent or 75.0

    for row in data:
        row["target_percent"] = target
        row["vs_target"] = round((row["utilization_percent"] or 0) - target, 2)

    return columns, data
