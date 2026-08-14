"""
Unit tests for Momentum Services Pack Script Reports.
Run with: bench --site <site> run-tests --app momentum
"""
import unittest
from datetime import date, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase


class TestServicesReports(FrappeTestCase):
    """Tests for all 10 Services Pack reports."""

    @classmethod
    def setUpClass(cls):
        """Set shared filter values used across all tests."""
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

    # ── Report 1: Utilization Summary ────────────────────────────────────────────

    def test_utilization_summary_columns(self):
        from momentum.momentum.report.utilization_summary.utilization_summary import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["employee", "employee_name", "billable_hours", "utilization_percent", "target_percent"]:
            self.assertIn(f, fieldnames)

    def test_utilization_summary_returns_data(self):
        from momentum.momentum.report.utilization_summary.utilization_summary import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, "Expected utilization data from seeded timesheets")

    def test_utilization_summary_utilization_in_range(self):
        from momentum.momentum.report.utilization_summary.utilization_summary import execute
        columns, data = execute(self.base_filters)
        for row in data:
            self.assertGreaterEqual(row["utilization_percent"], 0)
            self.assertLessEqual(row["utilization_percent"], 100)

    def test_utilization_summary_department_filter(self):
        from momentum.momentum.report.utilization_summary.utilization_summary import execute
        dept = frappe.db.get_value("Department", {"department_name": "Engineering"}, "name")
        if not dept:
            self.skipTest("Engineering department not found")
        filters = {**self.base_filters, "department": dept}
        columns, data = execute(filters)
        for row in data:
            self.assertEqual(row["department"], dept)

    # ── Report 2: Bench Report ────────────────────────────────────────────────────

    def test_bench_report_columns(self):
        from momentum.momentum.report.bench_report.bench_report import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["employee", "employee_name", "utilization_percent", "idle_hours"]:
            self.assertIn(f, fieldnames)

    def test_bench_report_all_below_target(self):
        from momentum.momentum.report.bench_report.bench_report import execute
        target = frappe.db.get_single_value("Momentum Settings", "utilization_target_percent") or 75
        columns, data = execute(self.base_filters)
        for row in data:
            self.assertLess(row["utilization_percent"], target,
                msg=f"Bench report should only show employees below target ({target}%)")

    # ── Report 3: Project Cost vs Budget ─────────────────────────────────────────

    def test_project_cost_vs_budget_columns(self):
        from momentum.momentum.report.project_cost_vs_budget.project_cost_vs_budget import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["project", "budget_amount", "actual_cost", "variance", "budget_utilization_percent"]:
            self.assertIn(f, fieldnames)

    def test_project_cost_vs_budget_returns_data(self):
        from momentum.momentum.report.project_cost_vs_budget.project_cost_vs_budget import execute
        columns, data = execute(self.base_filters)
        self.assertGreater(len(data), 0)

    def test_project_cost_vs_budget_variance_correct(self):
        from momentum.momentum.report.project_cost_vs_budget.project_cost_vs_budget import execute
        columns, data = execute(self.base_filters)
        for row in data:
            expected_variance = round(row["actual_cost"] - row["budget_amount"], 2)
            self.assertAlmostEqual(row["variance"], expected_variance, places=1)

    # ── Report 4: Realization Rate ────────────────────────────────────────────────

    def test_realization_rate_columns(self):
        from momentum.momentum.report.realization_rate.realization_rate import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["project", "billable_hours", "standard_value", "actual_invoiced", "realization_rate_percent"]:
            self.assertIn(f, fieldnames)

    def test_realization_rate_returns_data(self):
        from momentum.momentum.report.realization_rate.realization_rate import execute
        columns, data = execute(self.base_filters)
        self.assertGreater(len(data), 0)

    def test_realization_rate_invoiced_projects_have_rate(self):
        """Projects with Sales Invoices should have a non-zero realization rate."""
        from momentum.momentum.report.realization_rate.realization_rate import execute
        columns, data = execute(self.base_filters)
        invoiced = [r for r in data if r.get("actual_invoiced", 0) > 0]
        for row in invoiced:
            self.assertGreater(row["realization_rate_percent"], 0)

    # ── Report 5: Unbilled Hours WIP ─────────────────────────────────────────────

    def test_unbilled_hours_wip_columns(self):
        from momentum.momentum.report.unbilled_hours_wip.unbilled_hours_wip import execute
        filters = {"company": self.company, "as_of_date": self.to_date}
        columns, data = execute(filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["project", "bucket_0_15", "bucket_16_30", "bucket_30_plus", "total_unbilled_hours"]:
            self.assertIn(f, fieldnames)

    def test_unbilled_hours_wip_returns_data(self):
        from momentum.momentum.report.unbilled_hours_wip.unbilled_hours_wip import execute
        filters = {"company": self.company, "as_of_date": self.to_date}
        columns, data = execute(filters)
        self.assertGreater(len(data), 0)

    def test_unbilled_hours_wip_buckets_sum_to_total(self):
        from momentum.momentum.report.unbilled_hours_wip.unbilled_hours_wip import execute
        filters = {"company": self.company, "as_of_date": self.to_date}
        columns, data = execute(filters)
        for row in data:
            bucket_sum = round((row["bucket_0_15"] or 0) + (row["bucket_16_30"] or 0) + (row["bucket_30_plus"] or 0), 2)
            self.assertAlmostEqual(bucket_sum, row["total_unbilled_hours"], places=1)

    # ── Report 6: Client Effort Distribution ─────────────────────────────────────

    def test_client_effort_distribution_columns(self):
        from momentum.momentum.report.client_effort_distribution.client_effort_distribution import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["project", "total_hours", "billable_hours", "non_billable_hours"]:
            self.assertIn(f, fieldnames)

    def test_client_effort_distribution_returns_data(self):
        from momentum.momentum.report.client_effort_distribution.client_effort_distribution import execute
        columns, data = execute(self.base_filters)
        self.assertGreater(len(data), 0)

    def test_client_effort_distribution_hours_consistent(self):
        from momentum.momentum.report.client_effort_distribution.client_effort_distribution import execute
        columns, data = execute(self.base_filters)
        for row in data:
            self.assertAlmostEqual(
                (row["billable_hours"] or 0) + (row["non_billable_hours"] or 0),
                row["total_hours"],
                places=1
            )

    # ── Report 7: Time Entry Compliance ──────────────────────────────────────────

    def test_time_entry_compliance_columns(self):
        from momentum.momentum.report.time_entry_compliance.time_entry_compliance import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["employee", "expected_days", "logged_days", "missing_days", "compliance_percent"]:
            self.assertIn(f, fieldnames)

    def test_time_entry_compliance_returns_data(self):
        from momentum.momentum.report.time_entry_compliance.time_entry_compliance import execute
        columns, data = execute(self.base_filters)
        self.assertGreater(len(data), 0)

    def test_time_entry_compliance_missing_days_correct(self):
        from momentum.momentum.report.time_entry_compliance.time_entry_compliance import execute
        columns, data = execute(self.base_filters)
        for row in data:
            expected = row["expected_days"] - row["logged_days"]
            self.assertEqual(row["missing_days"], expected)

    # ── Report 8: Activity Type Breakdown ────────────────────────────────────────

    def test_activity_type_breakdown_columns(self):
        from momentum.momentum.report.activity_type_breakdown.activity_type_breakdown import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["activity_type", "total_hours", "billable_hours", "non_billable_hours"]:
            self.assertIn(f, fieldnames)

    def test_activity_type_breakdown_returns_data(self):
        from momentum.momentum.report.activity_type_breakdown.activity_type_breakdown import execute
        columns, data = execute(self.base_filters)
        self.assertGreater(len(data), 0)

    def test_activity_type_breakdown_known_types_present(self):
        from momentum.momentum.report.activity_type_breakdown.activity_type_breakdown import execute
        columns, data = execute(self.base_filters)
        activity_types = {r["activity_type"] for r in data}
        for at in ["Development", "Design", "Support", "Management"]:
            self.assertIn(at, activity_types)

    # ── Report 9: Task Estimate vs Actual ────────────────────────────────────────

    def test_task_estimate_vs_actual_columns(self):
        from momentum.momentum.report.task_estimate_vs_actual.task_estimate_vs_actual import execute
        filters = {"company": self.company}
        columns, data = execute(filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["task", "subject", "project", "estimated_hours", "actual_hours", "variance_hours"]:
            self.assertIn(f, fieldnames)

    def test_task_estimate_vs_actual_returns_data(self):
        from momentum.momentum.report.task_estimate_vs_actual.task_estimate_vs_actual import execute
        filters = {"company": self.company}
        columns, data = execute(filters)
        self.assertGreater(len(data), 0)

    def test_task_estimate_vs_actual_variance_correct(self):
        from momentum.momentum.report.task_estimate_vs_actual.task_estimate_vs_actual import execute
        filters = {"company": self.company}
        columns, data = execute(filters)
        for row in data:
            expected_variance = round((row["actual_hours"] or 0) - (row["estimated_hours"] or 0), 2)
            self.assertAlmostEqual(row["variance_hours"], expected_variance, places=1)

    # ── Report 10: Margin Trend by Project ───────────────────────────────────────

    def test_margin_trend_columns(self):
        from momentum.momentum.report.margin_trend_by_project.margin_trend_by_project import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["project", "date", "total_cost", "margin_percent", "status_flag"]:
            self.assertIn(f, fieldnames)

    def test_margin_trend_returns_data(self):
        from momentum.momentum.report.margin_trend_by_project.margin_trend_by_project import execute
        columns, data = execute(self.base_filters)
        self.assertGreater(len(data), 0, "Expected snapshot data; run seed first")

    def test_margin_trend_ordered_by_project_and_date(self):
        from momentum.momentum.report.margin_trend_by_project.margin_trend_by_project import execute
        columns, data = execute(self.base_filters)
        if len(data) < 2:
            return
        for i in range(len(data) - 1):
            if data[i]["project"] == data[i + 1]["project"]:
                self.assertLessEqual(str(data[i]["date"]), str(data[i + 1]["date"]))
