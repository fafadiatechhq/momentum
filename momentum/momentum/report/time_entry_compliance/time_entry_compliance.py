"""
Report: Time Entry Compliance
Shows how many weekdays each employee logged time vs expected working days.
"""

from datetime import date, timedelta

import frappe
from frappe.utils import add_months, today


def _count_weekdays(from_date_str, to_date_str):
    """Count weekdays (Mon-Fri) between two ISO date strings, inclusive."""
    start = date.fromisoformat(str(from_date_str))
    end = date.fromisoformat(str(to_date_str))
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "employee",          "label": "Employee",          "fieldtype": "Link",    "options": "Employee",   "width": 120},
        {"fieldname": "employee_name",     "label": "Employee Name",     "fieldtype": "Data",                             "width": 150},
        {"fieldname": "department",        "label": "Department",        "fieldtype": "Link",    "options": "Department", "width": 120},
        {"fieldname": "expected_days",     "label": "Expected Days",     "fieldtype": "Int",                              "width": 110},
        {"fieldname": "logged_days",       "label": "Logged Days",       "fieldtype": "Int",                              "width": 100},
        {"fieldname": "missing_days",      "label": "Missing Days",      "fieldtype": "Int",                              "width": 110},
        {"fieldname": "compliance_percent","label": "Compliance %",      "fieldtype": "Percent",                          "width": 120},
        {"fieldname": "total_hours",       "label": "Total Hours",       "fieldtype": "Float",                            "width": 110},
    ]

    from_date = filters.get("from_date") or add_months(today(), -1)
    to_date = filters.get("to_date") or today()
    expected_days = _count_weekdays(from_date, to_date)

    extra_parts = []
    params = {
        "from_date": from_date,
        "to_date": to_date,
    }

    if filters.get("company"):
        extra_parts.append("ts.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        extra_parts.append("emp.department = %(department)s")
        params["department"] = filters["department"]

    extra_conditions = ""
    if extra_parts:
        extra_conditions = "AND " + " AND ".join(extra_parts)

    query = """
        SELECT
            ts.employee,
            emp.employee_name,
            emp.department,
            COUNT(DISTINCT DATE(tsd.from_time)) AS logged_days,
            ROUND(SUM(tsd.hours), 2) AS total_hours
        FROM `tabTimesheet` ts
        JOIN `tabTimesheet Detail` tsd ON tsd.parent = ts.name
        JOIN `tabEmployee` emp ON emp.name = ts.employee
        WHERE ts.docstatus = 1
          AND DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s
          {extra_conditions}
        GROUP BY ts.employee, emp.employee_name, emp.department
    """.format(extra_conditions=extra_conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    for row in data:
        logged = row.get("logged_days") or 0
        row["expected_days"] = expected_days
        row["missing_days"] = max(0, expected_days - logged)
        row["compliance_percent"] = round((logged / expected_days * 100) if expected_days else 0, 2)

    data.sort(key=lambda r: r["compliance_percent"])

    return columns, data
