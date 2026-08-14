"""
Report: Company Effort Heatmap
Pivot matrix of hours: rows = Department, columns = Project (services view)
or rows = Work Center, columns = Operation (manufacturing view).
Controlled by the 'view_by' filter.
"""

import frappe
from frappe.utils import add_months, today


def execute(filters=None):
    filters = filters or {}
    view_by = filters.get("view_by") or "Project"

    if view_by == "Work Center":
        return _work_center_view(filters)
    return _project_view(filters)


# ── Project view (Timesheet → department × project) ───────────────────────────

def _project_view(filters):
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

    if filters.get("department"):
        cond_parts.append("emp.department = %(department)s")
        params["department"] = filters["department"]

    conditions = " AND ".join(cond_parts)

    rows = frappe.db.sql("""
        SELECT
            COALESCE(emp.department, '(No Department)') AS row_key,
            COALESCE(tsd.project, '(No Project)') AS col_key,
            ROUND(SUM(tsd.hours), 2) AS hours
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        JOIN `tabEmployee` emp ON emp.name = ts.employee
        WHERE {conditions}
        GROUP BY emp.department, tsd.project
        ORDER BY emp.department, tsd.project
    """.format(conditions=conditions), params, as_dict=True)

    return _build_pivot(rows, row_label="Department", row_fieldname="department")


# ── Work Center view (Job Card → work_center × operation) ─────────────────────

def _work_center_view(filters):
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

    conditions = " AND ".join(cond_parts)

    rows = frappe.db.sql("""
        SELECT
            COALESCE(jc.workstation, '(No Work Center)') AS row_key,
            COALESCE(jc.operation, '(No Operation)') AS col_key,
            ROUND(SUM(jctl.time_in_mins) / 60.0, 2) AS hours
        FROM `tabJob Card` jc
        JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE {conditions}
        GROUP BY jc.workstation, jc.operation
        ORDER BY jc.workstation, jc.operation
    """.format(conditions=conditions), params, as_dict=True)

    return _build_pivot(rows, row_label="Work Center", row_fieldname="work_center")


# ── Pivot builder ─────────────────────────────────────────────────────────────

def _build_pivot(rows, row_label, row_fieldname):
    """
    Convert flat (row_key, col_key, hours) rows into a pivot table.
    Column fieldnames are col_0, col_1, … so they are always valid identifiers
    regardless of what the project/operation names contain.
    """
    # Collect ordered unique column values
    seen_cols = []
    for r in rows:
        col = r["col_key"]
        if col not in seen_cols:
            seen_cols.append(col)

    # Build column definitions
    columns = [
        {
            "fieldname": row_fieldname,
            "label": row_label,
            "fieldtype": "Data",
            "width": 180,
        }
    ]
    for i, col_name in enumerate(seen_cols):
        columns.append({
            "fieldname": f"col_{i}",
            "label": col_name,
            "fieldtype": "Float",
            "width": 120,
        })
    columns.append({
        "fieldname": "total_hours",
        "label": "Total Hours",
        "fieldtype": "Float",
        "width": 120,
    })

    # Build pivot dict
    pivot = {}
    for r in rows:
        row_val = r["row_key"]
        if row_val not in pivot:
            pivot[row_val] = {}
        pivot[row_val][r["col_key"]] = r.get("hours") or 0

    # Assemble data rows
    data = []
    for row_val in sorted(pivot.keys()):
        col_data = pivot[row_val]
        row_dict = {row_fieldname: row_val}
        total = 0.0
        for i, col_name in enumerate(seen_cols):
            h = col_data.get(col_name) or 0
            row_dict[f"col_{i}"] = h
            total += h
        row_dict["total_hours"] = round(total, 2)
        data.append(row_dict)

    return columns, data
