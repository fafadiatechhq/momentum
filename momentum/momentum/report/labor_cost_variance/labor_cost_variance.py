"""
Report: Labor Cost Variance Report
Compares planned operating cost vs actual labour cost per operation.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "work_order",       "label": "Work Order",       "fieldtype": "Link",    "options": "Work Order", "width": 150},
        {"fieldname": "production_item",  "label": "Production Item",  "fieldtype": "Link",    "options": "Item",       "width": 140},
        {"fieldname": "operation",        "label": "Operation",        "fieldtype": "Data",                             "width": 130},
        {"fieldname": "work_center",      "label": "Work Center",      "fieldtype": "Link",    "options": "Work Center","width": 140},
        {"fieldname": "standard_cost",    "label": "Standard Cost",    "fieldtype": "Currency",                         "width": 120},
        {"fieldname": "actual_cost",      "label": "Actual Cost",      "fieldtype": "Currency",                         "width": 120},
        {"fieldname": "cost_variance",    "label": "Cost Variance",    "fieldtype": "Currency",                         "width": 120},
        {"fieldname": "variance_percent", "label": "Variance %",       "fieldtype": "Percent",                          "width": 110},
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
            ROUND(COALESCE(woo.planned_operating_cost, 0), 2) AS standard_cost,
            ROUND(SUM(jctl.time_in_mins) / 60.0 * COALESCE(wc.hour_rate, 0), 2) AS actual_cost,
            ROUND(
                SUM(jctl.time_in_mins) / 60.0 * COALESCE(wc.hour_rate, 0)
                - COALESCE(woo.planned_operating_cost, 0), 2
            ) AS cost_variance,
            ROUND(
                (SUM(jctl.time_in_mins) / 60.0 * COALESCE(wc.hour_rate, 0)
                 - COALESCE(woo.planned_operating_cost, 0))
                / NULLIF(COALESCE(woo.planned_operating_cost, 0), 0) * 100, 2
            ) AS variance_percent
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        LEFT JOIN `tabWork Order Operation` woo
            ON woo.parent = jc.work_order AND woo.operation = jc.operation
        LEFT JOIN `tabWork Center` wc ON wc.name = jc.workstation
        WHERE {conditions}
        GROUP BY jc.work_order, jc.operation, jc.workstation
        ORDER BY cost_variance DESC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)
    return columns, data
