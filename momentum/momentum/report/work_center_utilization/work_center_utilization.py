"""
Report: Work Center Utilization
Shows booked hours vs available capacity per work center per day.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "work_center",         "label": "Work Center",       "fieldtype": "Link",    "options": "Work Center", "width": 160},
        {"fieldname": "work_date",           "label": "Date",              "fieldtype": "Date",                              "width": 110},
        {"fieldname": "booked_hours",        "label": "Booked Hours",      "fieldtype": "Float",                             "width": 120},
        {"fieldname": "available_hours",     "label": "Available Hours",   "fieldtype": "Float",                             "width": 120},
        {"fieldname": "utilization_percent", "label": "Utilization %",     "fieldtype": "Percent",                           "width": 120},
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
            jc.workstation AS work_center,
            DATE(jctl.from_time) AS work_date,
            ROUND(SUM(jctl.time_in_mins) / 60.0, 2) AS booked_hours,
            COALESCE(wc.capacity, 8) AS available_hours,
            ROUND(SUM(jctl.time_in_mins) / 60.0 / NULLIF(COALESCE(wc.capacity, 8), 0) * 100, 2) AS utilization_percent
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        LEFT JOIN `tabWork Center` wc ON wc.name = jc.workstation
        WHERE {conditions}
        GROUP BY jc.workstation, DATE(jctl.from_time)
        ORDER BY work_date DESC, work_center
    """.format(conditions=conditions)

    data = frappe.db.sql(query, params, as_dict=True)
    return columns, data
