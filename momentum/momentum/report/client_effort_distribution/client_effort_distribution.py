"""
Report: Client Effort Distribution
Shows hours and billing value distributed across customers and their projects.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "customer",          "label": "Customer",          "fieldtype": "Link",     "options": "Customer", "width": 130},
        {"fieldname": "customer_name",     "label": "Customer Name",     "fieldtype": "Data",                            "width": 160},
        {"fieldname": "project",           "label": "Project",           "fieldtype": "Link",     "options": "Project",  "width": 130},
        {"fieldname": "project_name",      "label": "Project Name",      "fieldtype": "Data",                            "width": 180},
        {"fieldname": "total_hours",       "label": "Total Hours",       "fieldtype": "Float",                           "width": 110},
        {"fieldname": "billable_hours",    "label": "Billable Hours",    "fieldtype": "Float",                           "width": 110},
        {"fieldname": "non_billable_hours","label": "Non-Billable Hours","fieldtype": "Float",                           "width": 130},
        {"fieldname": "billing_value",     "label": "Billing Value",     "fieldtype": "Currency",                        "width": 130},
    ]

    cond_parts = [
        "ts.docstatus = 1",
        "DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("company"):
        cond_parts.append("ts.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("customer"):
        cond_parts.append("proj.customer = %(customer)s")
        params["customer"] = filters["customer"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            proj.customer,
            cust.customer_name,
            proj.name AS project,
            proj.project_name,
            ROUND(SUM(tsd.hours), 2) AS total_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END), 2) AS billable_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 0 THEN tsd.hours ELSE 0 END), 2) AS non_billable_hours,
            ROUND(SUM(tsd.hours * COALESCE(at.billing_rate, 0)), 2) AS billing_value
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        JOIN `tabProject` proj ON proj.name = tsd.project
        LEFT JOIN `tabCustomer` cust ON cust.name = proj.customer
        LEFT JOIN `tabActivity Type` at ON at.name = tsd.activity_type
        WHERE {conditions}
        GROUP BY proj.customer, cust.customer_name, proj.name, proj.project_name
        ORDER BY proj.customer, total_hours DESC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    return columns, data
