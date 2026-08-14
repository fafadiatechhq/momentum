"""
Report: Margin Trend by Project
Reads from Momentum Project Snapshot to show daily margin trends per project.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "project",                       "label": "Project",         "fieldtype": "Link",     "options": "Project",                    "width": 130},
        {"fieldname": "project_name",                  "label": "Project Name",    "fieldtype": "Data",                                              "width": 180},
        {"fieldname": "customer",                      "label": "Customer",        "fieldtype": "Link",     "options": "Customer",                   "width": 130},
        {"fieldname": "date",                          "label": "Date",            "fieldtype": "Date",                                              "width": 100},
        {"fieldname": "billable_hours",                "label": "Billable Hours",  "fieldtype": "Float",                                             "width": 120},
        {"fieldname": "total_cost",                    "label": "Total Cost",      "fieldtype": "Currency",                                          "width": 120},
        {"fieldname": "billed_amount_at_standard_rate","label": "Standard Value",  "fieldtype": "Currency",                                          "width": 150},
        {"fieldname": "actual_invoiced_amount",        "label": "Invoiced",        "fieldtype": "Currency",                                          "width": 140},
        {"fieldname": "margin_percent",                "label": "Margin %",        "fieldtype": "Percent",                                           "width": 110},
        {"fieldname": "status_flag",                   "label": "Status",          "fieldtype": "Data",                                              "width": 100},
    ]

    extra_parts = []
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("company"):
        extra_parts.append("mps.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("project"):
        extra_parts.append("mps.project = %(project)s")
        params["project"] = filters["project"]

    extra_conditions = ""
    if extra_parts:
        extra_conditions = "AND " + " AND ".join(extra_parts)

    query = """
        SELECT
            mps.project,
            proj.project_name,
            proj.customer,
            mps.date,
            mps.billable_hours,
            mps.total_cost,
            mps.billed_amount_at_standard_rate,
            mps.actual_invoiced_amount,
            ROUND(
                (mps.billed_amount_at_standard_rate - mps.total_cost)
                / NULLIF(mps.billed_amount_at_standard_rate, 0) * 100, 2
            ) AS margin_percent,
            mps.status_flag
        FROM `tabMomentum Project Snapshot` mps
        JOIN `tabProject` proj ON proj.name = mps.project
        WHERE mps.date BETWEEN %(from_date)s AND %(to_date)s
          {extra_conditions}
        ORDER BY mps.project, mps.date
    """.format(extra_conditions=extra_conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    return columns, data
