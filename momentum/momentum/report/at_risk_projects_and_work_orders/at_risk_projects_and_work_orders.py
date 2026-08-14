"""
Report: At-Risk Projects and Work Orders
Surfaces projects and work orders that have breached the budget overrun
threshold configured in Momentum Settings.

Projects: pulled from Momentum Project Snapshot (status_flag At Risk / Over Budget).
Work Orders: pulled from Momentum Operation Efficiency Snapshot where actual cost
             exceeds standard cost by more than the threshold percent.
"""

import frappe
from frappe.utils import add_months, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"fieldname": "type",                "label": "Type",              "fieldtype": "Data",     "width": 100},
        {"fieldname": "reference",           "label": "Reference",         "fieldtype": "Data",     "width": 160},
        {"fieldname": "reference_name",      "label": "Name",              "fieldtype": "Data",     "width": 200},
        {"fieldname": "company",             "label": "Company",           "fieldtype": "Link",     "options": "Company", "width": 130},
        {"fieldname": "budget_amount",       "label": "Budget / Std Cost", "fieldtype": "Currency", "width": 140},
        {"fieldname": "actual_amount",       "label": "Actual Cost",       "fieldtype": "Currency", "width": 130},
        {"fieldname": "overrun_percent",     "label": "Overrun %",         "fieldtype": "Percent",  "width": 110},
        {"fieldname": "status_flag",         "label": "Status",            "fieldtype": "Data",     "width": 110},
    ]

    settings = frappe.get_single("Momentum Settings")
    threshold = settings.budget_overrun_threshold_percent or 90.0

    data = []
    data.extend(_at_risk_projects(filters, threshold))
    data.extend(_at_risk_work_orders(filters, threshold))

    # Sort: Over Budget first, then At Risk, then by overrun % desc
    _status_order = {"Over Budget": 0, "At Risk": 1}
    data.sort(key=lambda r: (_status_order.get(r["status_flag"], 2), -(r["overrun_percent"] or 0)))

    return columns, data


# ── Projects ──────────────────────────────────────────────────────────────────

def _at_risk_projects(filters, threshold):
    """
    Return one row per project whose most recent snapshot status_flag is
    'At Risk' or 'Over Budget'.  Actual cost = SUM of daily snapshot total_cost
    across the requested period.
    """
    extra_parts = []
    params = {
        "from_date": filters.get("from_date") or add_months(today(), -1),
        "to_date": filters.get("to_date") or today(),
    }

    if filters.get("company"):
        extra_parts.append("mps.company = %(company)s")
        params["company"] = filters["company"]

    extra = ("AND " + " AND ".join(extra_parts)) if extra_parts else ""

    # Aggregate cost over the period, bring in latest status_flag via subquery
    rows = frappe.db.sql("""
        SELECT
            mps.project,
            proj.project_name,
            mps.company,
            ROUND(SUM(mps.total_cost), 2) AS actual_amount,
            proj.estimated_costing AS budget_amount,
            ROUND(SUM(mps.total_cost) / NULLIF(proj.estimated_costing, 0) * 100, 2) AS overrun_percent,
            latest.status_flag
        FROM `tabMomentum Project Snapshot` mps
        JOIN `tabProject` proj ON proj.name = mps.project
        JOIN (
            SELECT project, status_flag
            FROM `tabMomentum Project Snapshot` inner_mps
            WHERE inner_mps.date = (
                SELECT MAX(date)
                FROM `tabMomentum Project Snapshot`
                WHERE project = inner_mps.project
            )
        ) latest ON latest.project = mps.project
        WHERE mps.date BETWEEN %(from_date)s AND %(to_date)s
          AND latest.status_flag IN ('At Risk', 'Over Budget')
          {extra}
        GROUP BY mps.project, proj.project_name, mps.company,
                 proj.estimated_costing, latest.status_flag
        ORDER BY overrun_percent DESC
    """.format(extra=extra), params, as_dict=True)

    result = []
    for r in rows:
        result.append({
            "type": "Project",
            "reference": r["project"],
            "reference_name": r.get("project_name") or r["project"],
            "company": r["company"],
            "budget_amount": r.get("budget_amount") or 0,
            "actual_amount": r.get("actual_amount") or 0,
            "overrun_percent": r.get("overrun_percent") or 0,
            "status_flag": r["status_flag"],
        })
    return result


# ── Work Orders ───────────────────────────────────────────────────────────────

def _at_risk_work_orders(filters, threshold):
    """
    Return one row per work order where the cumulative actual cost from
    Operation Efficiency Snapshots exceeds standard cost by more than
    the configured threshold percent.
    """
    extra_parts = []
    params = {
        "from_date": filters.get("from_date") or add_months(today(), -1),
        "to_date": filters.get("to_date") or today(),
        "threshold": threshold,
    }

    if filters.get("company"):
        extra_parts.append("moes.company = %(company)s")
        params["company"] = filters["company"]

    extra = ("AND " + " AND ".join(extra_parts)) if extra_parts else ""

    rows = frappe.db.sql("""
        SELECT
            moes.work_order,
            wo.production_item AS reference_name,
            moes.company,
            ROUND(SUM(moes.standard_cost), 2) AS budget_amount,
            ROUND(SUM(moes.actual_cost), 2) AS actual_amount,
            ROUND(SUM(moes.actual_cost) / NULLIF(SUM(moes.standard_cost), 0) * 100, 2) AS overrun_percent
        FROM `tabMomentum Operation Efficiency Snapshot` moes
        LEFT JOIN `tabWork Order` wo ON wo.name = moes.work_order
        WHERE moes.date BETWEEN %(from_date)s AND %(to_date)s
          {extra}
        GROUP BY moes.work_order, moes.company, wo.production_item
        HAVING overrun_percent > %(threshold)s
        ORDER BY overrun_percent DESC
    """.format(extra=extra), params, as_dict=True)

    result = []
    for r in rows:
        overrun = r.get("overrun_percent") or 0
        budget = r.get("budget_amount") or 0
        actual = r.get("actual_amount") or 0
        status = "Over Budget" if actual > budget else "At Risk"
        result.append({
            "type": "Work Order",
            "reference": r["work_order"],
            "reference_name": r.get("reference_name") or r["work_order"],
            "company": r["company"],
            "budget_amount": budget,
            "actual_amount": actual,
            "overrun_percent": overrun,
            "status_flag": status,
        })
    return result
