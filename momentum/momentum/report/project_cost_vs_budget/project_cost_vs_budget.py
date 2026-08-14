"""
Report: Project Cost vs Budget
Compares actual timesheet cost (hours * costing rate) against project estimated_costing.
"""

import frappe
from frappe.utils import add_months, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "project",                    "label": "Project",               "fieldtype": "Link",     "options": "Project",   "width": 150},
        {"fieldname": "project_name",               "label": "Project Name",          "fieldtype": "Data",                             "width": 180},
        {"fieldname": "customer",                   "label": "Customer",              "fieldtype": "Link",     "options": "Customer",  "width": 130},
        {"fieldname": "budget_amount",              "label": "Budget Amount",         "fieldtype": "Currency",                         "width": 130},
        {"fieldname": "actual_cost",                "label": "Actual Cost",           "fieldtype": "Currency",                         "width": 130},
        {"fieldname": "variance",                   "label": "Variance",              "fieldtype": "Currency",                         "width": 120},
        {"fieldname": "budget_utilization_percent", "label": "Budget Utilization %",  "fieldtype": "Percent",                          "width": 130},
        {"fieldname": "status",                     "label": "Status",                "fieldtype": "Data",                             "width": 100},
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

    if filters.get("project"):
        cond_parts.append("proj.name = %(project)s")
        params["project"] = filters["project"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            proj.name AS project,
            proj.project_name,
            proj.customer,
            ROUND(SUM(tsd.hours * COALESCE(at.costing_rate, 0)), 2) AS actual_cost,
            proj.estimated_costing AS budget_amount,
            ROUND(SUM(tsd.hours), 2) AS total_hours,
            ROUND(
                (SUM(tsd.hours * COALESCE(at.costing_rate, 0)) / NULLIF(proj.estimated_costing, 0)) * 100, 2
            ) AS budget_utilization_percent
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        JOIN `tabProject` proj ON proj.name = tsd.project
        LEFT JOIN `tabActivity Type` at ON at.name = tsd.activity_type
        WHERE {conditions}
        GROUP BY proj.name, proj.project_name, proj.customer, proj.estimated_costing
        ORDER BY budget_utilization_percent DESC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    settings = frappe.get_single("Momentum Settings")
    threshold = settings.budget_overrun_threshold_percent or 80

    for row in data:
        actual_cost = row.get("actual_cost") or 0
        budget_amount = row.get("budget_amount") or 0
        row["variance"] = round(actual_cost - budget_amount, 2)

        if budget_amount and actual_cost > budget_amount:
            row["status"] = "Over Budget"
        elif budget_amount and actual_cost > budget_amount * (threshold / 100):
            row["status"] = "At Risk"
        else:
            row["status"] = "On Track"

    return columns, data
