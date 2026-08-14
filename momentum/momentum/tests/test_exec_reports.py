"""
Unit tests for Momentum Shared / Exec reports (Section 7.3).
Run with: bench --site <site> run-tests --app momentum
"""
from datetime import date, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase


class TestExecReports(FrappeTestCase):
    """Tests for the 2 Shared/Exec reports."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = date.today()
        cls.from_date = str(cls.today - timedelta(days=90))
        cls.to_date = str(cls.today)
        cls.company = frappe.db.get_value("Company", {}, "name")
        cls.base_filters = {
            "from_date": cls.from_date,
            "to_date": cls.to_date,
            "company": cls.company,
        }

    # ── Report 1: Company Effort Heatmap (Project view) ──────────────────────────

    def test_heatmap_project_view_columns(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Project"}
        columns, data = execute(filters)
        fieldnames = [c["fieldname"] for c in columns]
        self.assertIn("department", fieldnames)
        self.assertIn("total_hours", fieldnames)

    def test_heatmap_project_view_returns_data(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Project"}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, "Expected heatmap rows from seeded timesheets")

    def test_heatmap_project_view_total_hours_correct(self):
        """total_hours must equal the sum of all col_N values in each row."""
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Project"}
        columns, data = execute(filters)
        col_fieldnames = [c["fieldname"] for c in columns
                          if c["fieldname"].startswith("col_")]
        for row in data:
            col_sum = sum(row.get(fn) or 0 for fn in col_fieldnames)
            self.assertAlmostEqual(row["total_hours"], col_sum, places=1)

    def test_heatmap_project_view_no_negative_hours(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Project"}
        columns, data = execute(filters)
        col_fieldnames = [c["fieldname"] for c in columns
                          if c["fieldname"].startswith("col_")]
        for row in data:
            for fn in col_fieldnames:
                self.assertGreaterEqual(row.get(fn) or 0, 0)

    def test_heatmap_department_filter(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        dept = frappe.db.get_value("Department", {"department_name": "Engineering"}, "name")
        if not dept:
            self.skipTest("Engineering department not found")
        filters = {**self.base_filters, "view_by": "Project", "department": dept}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)
        for row in data:
            self.assertEqual(row["department"], dept)

    # ── Report 1: Company Effort Heatmap (Work Center view) ──────────────────────

    def test_heatmap_work_center_view_columns(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Work Center"}
        columns, data = execute(filters)
        fieldnames = [c["fieldname"] for c in columns]
        self.assertIn("work_center", fieldnames)
        self.assertIn("total_hours", fieldnames)

    def test_heatmap_work_center_view_returns_list(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Work Center"}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)

    def test_heatmap_work_center_view_total_hours_correct(self):
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        filters = {**self.base_filters, "view_by": "Work Center"}
        columns, data = execute(filters)
        col_fieldnames = [c["fieldname"] for c in columns
                          if c["fieldname"].startswith("col_")]
        for row in data:
            col_sum = sum(row.get(fn) or 0 for fn in col_fieldnames)
            self.assertAlmostEqual(row["total_hours"], col_sum, places=1)

    def test_heatmap_defaults_to_project_view(self):
        """Omitting view_by should behave identically to view_by='Project'."""
        from momentum.momentum.report.company_effort_heatmap.company_effort_heatmap import execute
        cols_default, data_default = execute(self.base_filters)
        cols_explicit, data_explicit = execute({**self.base_filters, "view_by": "Project"})
        self.assertEqual(
            [c["fieldname"] for c in cols_default],
            [c["fieldname"] for c in cols_explicit],
        )

    # ── Report 2: At-Risk Projects and Work Orders ───────────────────────────────

    def test_at_risk_columns(self):
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["type", "reference", "reference_name", "company",
                  "budget_amount", "actual_amount", "overrun_percent", "status_flag"]:
            self.assertIn(f, fieldnames)

    def test_at_risk_returns_list(self):
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)

    def test_at_risk_type_values(self):
        """type column must be 'Project' or 'Work Order'."""
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        valid_types = {"Project", "Work Order"}
        for row in data:
            self.assertIn(row["type"], valid_types)

    def test_at_risk_status_values(self):
        """status_flag must be 'At Risk' or 'Over Budget'."""
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        valid_statuses = {"At Risk", "Over Budget"}
        for row in data:
            self.assertIn(row["status_flag"], valid_statuses)

    def test_at_risk_overrun_percent_positive(self):
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        for row in data:
            self.assertGreater(row["overrun_percent"], 0)

    def test_at_risk_sorted_over_budget_first(self):
        """Over Budget rows must appear before At Risk rows."""
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        seen_at_risk = False
        for row in data:
            if row["status_flag"] == "At Risk":
                seen_at_risk = True
            if seen_at_risk:
                self.assertNotEqual(
                    row["status_flag"], "Over Budget",
                    "Over Budget row found after At Risk row — sort order is wrong",
                )

    def test_at_risk_company_filter(self):
        from momentum.momentum.report.at_risk_projects_and_work_orders.at_risk_projects_and_work_orders import execute
        columns, data = execute(self.base_filters)
        for row in data:
            self.assertEqual(row["company"], self.company)
