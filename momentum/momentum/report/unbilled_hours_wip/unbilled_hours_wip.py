"""
Report: Unbilled Hours WIP
Shows billable timesheet hours that have not yet been invoiced, bucketed by age.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "project",             "label": "Project",          "fieldtype": "Link",     "options": "Project",  "width": 150},
        {"fieldname": "project_name",        "label": "Project Name",     "fieldtype": "Data",                            "width": 180},
        {"fieldname": "customer",            "label": "Customer",         "fieldtype": "Link",     "options": "Customer", "width": 130},
        {"fieldname": "bucket_0_15",         "label": "0-15 Days",        "fieldtype": "Float",                           "width": 100},
        {"fieldname": "bucket_16_30",        "label": "16-30 Days",       "fieldtype": "Float",                           "width": 100},
        {"fieldname": "bucket_30_plus",      "label": "30+ Days",         "fieldtype": "Float",                           "width": 100},
        {"fieldname": "total_unbilled_hours","label": "Total Unbilled Hrs","fieldtype": "Float",                           "width": 130},
        {"fieldname": "unbilled_value",      "label": "Unbilled Value",   "fieldtype": "Currency",                        "width": 140},
    ]

    as_of_date = filters.get("as_of_date") or frappe.utils.today()
    params = {"as_of_date": as_of_date}

    extra_parts = []

    if filters.get("company"):
        extra_parts.append("ts.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("project"):
        extra_parts.append("proj.name = %(project)s")
        params["project"] = filters["project"]

    extra_conditions = ""
    if extra_parts:
        extra_conditions = "AND " + " AND ".join(extra_parts)

    query = """
        SELECT
            proj.name AS project,
            proj.project_name,
            proj.customer,
            ROUND(SUM(CASE WHEN DATEDIFF(%(as_of_date)s, DATE(tsd.from_time)) BETWEEN 0 AND 15
                THEN tsd.hours ELSE 0 END), 2) AS bucket_0_15,
            ROUND(SUM(CASE WHEN DATEDIFF(%(as_of_date)s, DATE(tsd.from_time)) BETWEEN 16 AND 30
                THEN tsd.hours ELSE 0 END), 2) AS bucket_16_30,
            ROUND(SUM(CASE WHEN DATEDIFF(%(as_of_date)s, DATE(tsd.from_time)) > 30
                THEN tsd.hours ELSE 0 END), 2) AS bucket_30_plus,
            ROUND(SUM(tsd.hours), 2) AS total_unbilled_hours,
            ROUND(SUM(tsd.hours * COALESCE(at.billing_rate, 0)), 2) AS unbilled_value
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        JOIN `tabProject` proj ON proj.name = tsd.project
        LEFT JOIN `tabActivity Type` at ON at.name = tsd.activity_type
        WHERE ts.docstatus = 1
          AND tsd.is_billable = 1
          AND DATE(tsd.from_time) <= %(as_of_date)s
          AND tsd.sales_invoice IS NULL
          {extra_conditions}
        GROUP BY proj.name, proj.project_name, proj.customer
        HAVING total_unbilled_hours > 0
        ORDER BY total_unbilled_hours DESC
    """.format(extra_conditions=extra_conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    return columns, data
