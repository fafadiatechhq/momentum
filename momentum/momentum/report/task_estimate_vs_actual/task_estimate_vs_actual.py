"""
Report: Task Estimate vs Actual
Compares expected_time on tasks against actual hours logged in submitted timesheets.
"""

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "task",             "label": "Task",             "fieldtype": "Link",    "options": "Task",    "width": 130},
        {"fieldname": "subject",          "label": "Subject",          "fieldtype": "Data",                          "width": 200},
        {"fieldname": "project",          "label": "Project",          "fieldtype": "Link",    "options": "Project", "width": 130},
        {"fieldname": "project_name",     "label": "Project Name",     "fieldtype": "Data",                          "width": 160},
        {"fieldname": "estimated_hours",  "label": "Estimated Hours",  "fieldtype": "Float",                         "width": 130},
        {"fieldname": "actual_hours",     "label": "Actual Hours",     "fieldtype": "Float",                         "width": 110},
        {"fieldname": "variance_hours",   "label": "Variance Hours",   "fieldtype": "Float",                         "width": 110},
        {"fieldname": "completion_percent","label": "Completion %",    "fieldtype": "Percent",                        "width": 130},
    ]

    extra_parts = []
    params = {}

    if filters.get("company"):
        extra_parts.append("proj.company = %(company)s")
        params["company"] = filters["company"]
    else:
        # company is always filtered — if not provided use a no-op true condition
        pass

    if filters.get("project"):
        extra_parts.append("task.project = %(project)s")
        params["project"] = filters["project"]

    if filters.get("from_date") and filters.get("to_date"):
        extra_parts.append("DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s")
        params["from_date"] = filters["from_date"]
        params["to_date"] = filters["to_date"]

    extra_conditions = ""
    if extra_parts:
        extra_conditions = "AND " + " AND ".join(extra_parts)

    query = """
        SELECT
            task.name AS task,
            task.subject,
            task.project,
            proj.project_name,
            COALESCE(task.expected_time, 0) AS estimated_hours,
            COALESCE(SUM(tsd.hours), 0) AS actual_hours,
            COALESCE(SUM(tsd.hours), 0) - COALESCE(task.expected_time, 0) AS variance_hours,
            ROUND(
                (COALESCE(SUM(tsd.hours), 0) / NULLIF(task.expected_time, 0)) * 100, 2
            ) AS completion_percent
        FROM `tabTask` task
        JOIN `tabProject` proj ON proj.name = task.project
        LEFT JOIN `tabTimesheet Detail` tsd ON tsd.task = task.name
        LEFT JOIN `tabTimesheet` ts ON ts.name = tsd.parent AND ts.docstatus = 1
        WHERE 1=1
          {extra_conditions}
        GROUP BY task.name, task.subject, task.project, proj.project_name, task.expected_time
        HAVING estimated_hours > 0 OR actual_hours > 0
        ORDER BY variance_hours DESC
    """.format(extra_conditions=extra_conditions)

    data = frappe.db.sql(query, params, as_dict=True)

    return columns, data
