"""
Report: Realization Rate
Compares billable value at standard rates against actual invoiced amounts per project.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "project",                "label": "Project",              "fieldtype": "Link",     "options": "Project",  "width": 150},
        {"fieldname": "project_name",           "label": "Project Name",         "fieldtype": "Data",                            "width": 180},
        {"fieldname": "customer",               "label": "Customer",             "fieldtype": "Link",     "options": "Customer", "width": 130},
        {"fieldname": "billable_hours",         "label": "Billable Hours",       "fieldtype": "Float",                           "width": 120},
        {"fieldname": "standard_value",         "label": "Standard Value",       "fieldtype": "Currency",                        "width": 140},
        {"fieldname": "actual_invoiced",        "label": "Actual Invoiced",      "fieldtype": "Currency",                        "width": 140},
        {"fieldname": "realization_rate_percent","label": "Realization Rate %",  "fieldtype": "Percent",                         "width": 130},
    ]

    cond_parts = [
        "ts.docstatus = 1",
        "DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s",
        "tsd.is_billable = 1",
    ]
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("company"):
        cond_parts.append("ts.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("project"):
        cond_parts.append("proj.name = %(project)s")
        params["project"] = filters["project"]

    if filters.get("customer"):
        cond_parts.append("proj.customer = %(customer)s")
        params["customer"] = filters["customer"]

    conditions = " AND ".join(cond_parts)

    query = """
        SELECT
            proj.name AS project,
            proj.project_name,
            proj.customer,
            ROUND(SUM(CASE WHEN tsd.is_billable = 1 THEN tsd.hours ELSE 0 END), 2) AS billable_hours,
            ROUND(SUM(CASE WHEN tsd.is_billable = 1
                THEN tsd.hours * COALESCE(at.billing_rate, 0) ELSE 0 END), 2) AS standard_value,
            COALESCE((
                SELECT SUM(si2.base_grand_total)
                FROM `tabSales Invoice` si2
                WHERE si2.project = proj.name AND si2.docstatus = 1
            ), 0) AS actual_invoiced,
            ROUND(
                COALESCE((
                    SELECT SUM(si2.base_grand_total)
                    FROM `tabSales Invoice` si2
                    WHERE si2.project = proj.name AND si2.docstatus = 1
                ), 0)
                / NULLIF(SUM(CASE WHEN tsd.is_billable = 1
                    THEN tsd.hours * COALESCE(at.billing_rate, 0) ELSE 0 END), 0) * 100, 2
            ) AS realization_rate_percent
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        JOIN `tabProject` proj ON proj.name = tsd.project
        LEFT JOIN `tabActivity Type` at ON at.name = tsd.activity_type
        WHERE {conditions}
        GROUP BY proj.name, proj.project_name, proj.customer
        ORDER BY realization_rate_percent DESC
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    return columns, data
