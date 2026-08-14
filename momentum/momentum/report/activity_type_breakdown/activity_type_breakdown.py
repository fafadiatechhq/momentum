"""
Report: Activity Type Breakdown
Summarizes hours and billing/costing value by Activity Type.
"""

import frappe
from frappe.utils import add_months, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "activity_type",     "label": "Activity Type",      "fieldtype": "Link",     "options": "Activity Type", "width": 140},
        {"fieldname": "total_hours",       "label": "Total Hours",        "fieldtype": "Float",                                "width": 110},
        {"fieldname": "billable_hours",    "label": "Billable Hours",     "fieldtype": "Float",                                "width": 110},
        {"fieldname": "non_billable_hours","label": "Non-Billable Hours", "fieldtype": "Float",                                "width": 130},
        {"fieldname": "billing_value",     "label": "Billing Value",      "fieldtype": "Currency",                             "width": 130},
        {"fieldname": "costing_value",     "label": "Costing Value",      "fieldtype": "Currency",                             "width": 130},
        {"fieldname": "employee_count",    "label": "Employees",          "fieldtype": "Int",                                  "width": 120},
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

    if filters.get("employee"):
        cond_parts.append("ts.employee = %(employee)s")
        params["employee"] = filters["employee"]

    if filters.get("department"):
        cond_parts.append("emp.department = %(department)s")
        params["department"] = filters["department"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            tsd.activity_type,
            ROUND(SUM(tsd.hours), 2) AS total_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END), 2) AS billable_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 0 THEN tsd.hours ELSE 0 END), 2) AS non_billable_hours,
            ROUND(SUM(tsd.hours * COALESCE(at.billing_rate, 0)), 2) AS billing_value,
            ROUND(SUM(tsd.hours * COALESCE(at.costing_rate, 0)), 2) AS costing_value,
            COUNT(DISTINCT ts.employee) AS employee_count
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        JOIN `tabEmployee` emp ON emp.name = ts.employee
        LEFT JOIN `tabActivity Type` at ON at.name = tsd.activity_type
        WHERE {conditions}
        GROUP BY tsd.activity_type
        ORDER BY total_hours DESC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    return columns, data
