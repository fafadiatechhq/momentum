"""
Report: Operation Efficiency Report
Compares standard vs actual time per operation to compute efficiency %.
"""

import frappe
from frappe.utils import add_months, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "work_order",          "label": "Work Order",         "fieldtype": "Link",    "options": "Work Order", "width": 150},
        {"fieldname": "production_item",     "label": "Production Item",    "fieldtype": "Link",    "options": "Item",       "width": 140},
        {"fieldname": "operation",           "label": "Operation",          "fieldtype": "Data",                             "width": 130},
        {"fieldname": "work_center",         "label": "Work Center",        "fieldtype": "Link",    "options": "Work Center","width": 140},
        {"fieldname": "standard_time_mins",  "label": "Standard Time (min)","fieldtype": "Float",                            "width": 130},
        {"fieldname": "actual_time_mins",    "label": "Actual Time (min)",  "fieldtype": "Float",                            "width": 130},
        {"fieldname": "efficiency_percent",  "label": "Efficiency %",       "fieldtype": "Percent",                          "width": 110},
    ]

    cond_parts = [
        "jc.docstatus = 1",
        "DATE(jctl.from_time) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.get("from_date") or add_months(today(), -1),
        "to_date": filters.get("to_date") or today(),
    }

    if filters.get("company"):
        cond_parts.append("jc.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("work_order"):
        cond_parts.append("jc.work_order = %(work_order)s")
        params["work_order"] = filters["work_order"]

    if filters.get("work_center"):
        cond_parts.append("jc.workstation = %(work_center)s")
        params["work_center"] = filters["work_center"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            jc.work_order,
            wo.production_item,
            jc.operation,
            jc.workstation AS work_center,
            COALESCE(woo.time_in_mins, 0) AS standard_time_mins,
            ROUND(SUM(jctl.time_in_mins), 2) AS actual_time_mins,
            ROUND(COALESCE(woo.time_in_mins, 0) / NULLIF(SUM(jctl.time_in_mins), 0) * 100, 2) AS efficiency_percent
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        LEFT JOIN `tabWork Order Operation` woo
            ON woo.parent = jc.work_order AND woo.operation = jc.operation
        WHERE {conditions}
        GROUP BY jc.work_order, jc.operation, jc.workstation
        ORDER BY efficiency_percent ASC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)
    return columns, data
