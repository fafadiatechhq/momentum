"""
Unit tests for Momentum Manufacturing Pack Script Reports.
Run with: bench --site <site> run-tests --app momentum
"""
import unittest
from datetime import date, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase


class TestManufacturingReports(FrappeTestCase):
    """Tests for all 5 Manufacturing Pack reports."""

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

    # ── Report 1: Operation Efficiency Report ────────────────────────────────────

    def test_operation_efficiency_columns(self):
        from momentum.momentum.report.operation_efficiency.operation_efficiency import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["work_order", "operation", "work_center", "standard_time_mins",
                  "actual_time_mins", "efficiency_percent"]:
            self.assertIn(f, fieldnames)

    def test_operation_efficiency_returns_data(self):
        from momentum.momentum.report.operation_efficiency.operation_efficiency import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)

    def test_operation_efficiency_work_order_filter(self):
        from momentum.momentum.report.operation_efficiency.operation_efficiency import execute
        work_order = frappe.db.get_value("Job Card", {"docstatus": 1}, "work_order")
        if not work_order:
            self.skipTest("No submitted Job Cards found")
        filters = {**self.base_filters, "work_order": work_order}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)
        for row in data:
            self.assertEqual(row["work_order"], work_order)

    def test_operation_efficiency_work_center_filter(self):
        from momentum.momentum.report.operation_efficiency.operation_efficiency import execute
        wc = frappe.db.get_value("Work Center", {}, "name")
        if not wc:
            self.skipTest("No Work Centers found")
        filters = {**self.base_filters, "work_center": wc}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)

    # ── Report 2: Labor Cost Variance Report ─────────────────────────────────────

    def test_labor_cost_variance_columns(self):
        from momentum.momentum.report.labor_cost_variance.labor_cost_variance import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["work_order", "operation", "work_center", "standard_cost",
                  "actual_cost", "cost_variance"]:
            self.assertIn(f, fieldnames)

    def test_labor_cost_variance_returns_data(self):
        from momentum.momentum.report.labor_cost_variance.labor_cost_variance import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)

    def test_labor_cost_variance_work_center_filter(self):
        from momentum.momentum.report.labor_cost_variance.labor_cost_variance import execute
        wc = frappe.db.get_value("Work Center", {}, "name")
        if not wc:
            self.skipTest("No Work Centers found")
        filters = {**self.base_filters, "work_center": wc}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)

    def test_labor_cost_variance_cost_variance_computed(self):
        from momentum.momentum.report.labor_cost_variance.labor_cost_variance import execute
        columns, data = execute(self.base_filters)
        for row in data:
            expected = round((row["actual_cost"] or 0) - (row["standard_cost"] or 0), 2)
            self.assertAlmostEqual(row["cost_variance"], expected, places=1)

    # ── Report 3: Work Center Utilization ────────────────────────────────────────

    def test_work_center_utilization_columns(self):
        from momentum.momentum.report.work_center_utilization.work_center_utilization import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["work_center", "work_date", "booked_hours", "available_hours",
                  "utilization_percent"]:
            self.assertIn(f, fieldnames)

    def test_work_center_utilization_returns_data(self):
        from momentum.momentum.report.work_center_utilization.work_center_utilization import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)

    def test_work_center_utilization_work_center_filter(self):
        from momentum.momentum.report.work_center_utilization.work_center_utilization import execute
        wc = frappe.db.get_value("Work Center", {}, "name")
        if not wc:
            self.skipTest("No Work Centers found")
        filters = {**self.base_filters, "work_center": wc}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)
        for row in data:
            self.assertEqual(row["work_center"], wc)

    # ── Report 4: Operator Productivity ──────────────────────────────────────────

    def test_operator_productivity_columns(self):
        from momentum.momentum.report.operator_productivity.operator_productivity import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["employee", "work_center", "operation", "actual_time_mins",
                  "efficiency_percent"]:
            self.assertIn(f, fieldnames)

    def test_operator_productivity_returns_data(self):
        from momentum.momentum.report.operator_productivity.operator_productivity import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)

    def test_operator_productivity_unassigned_label(self):
        """Rows with no employee should show '(Unassigned)' as employee_name."""
        from momentum.momentum.report.operator_productivity.operator_productivity import execute
        columns, data = execute(self.base_filters)
        for row in data:
            if not row.get("employee"):
                self.assertEqual(row["employee_name"], "(Unassigned)")

    def test_operator_productivity_work_center_filter(self):
        from momentum.momentum.report.operator_productivity.operator_productivity import execute
        wc = frappe.db.get_value("Work Center", {}, "name")
        if not wc:
            self.skipTest("No Work Centers found")
        filters = {**self.base_filters, "work_center": wc}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)

    # ── Report 5: Shift & Overtime Analysis ──────────────────────────────────────

    def test_shift_overtime_analysis_columns(self):
        from momentum.momentum.report.shift_overtime_analysis.shift_overtime_analysis import execute
        columns, data = execute(self.base_filters)
        fieldnames = [c["fieldname"] for c in columns]
        for f in ["work_center", "work_date", "shift", "total_hours", "overtime_hours"]:
            self.assertIn(f, fieldnames)

    def test_shift_overtime_analysis_returns_data(self):
        from momentum.momentum.report.shift_overtime_analysis.shift_overtime_analysis import execute
        columns, data = execute(self.base_filters)
        self.assertIsInstance(data, list)

    def test_shift_overtime_analysis_shift_values(self):
        """shift column must be one of the three defined buckets."""
        from momentum.momentum.report.shift_overtime_analysis.shift_overtime_analysis import execute
        columns, data = execute(self.base_filters)
        valid_shifts = {"Morning", "Afternoon", "Evening/Night"}
        for row in data:
            self.assertIn(row["shift"], valid_shifts)

    def test_shift_overtime_analysis_overtime_non_negative(self):
        from momentum.momentum.report.shift_overtime_analysis.shift_overtime_analysis import execute
        columns, data = execute(self.base_filters)
        for row in data:
            self.assertGreaterEqual(row["overtime_hours"], 0)

    def test_shift_overtime_analysis_work_center_filter(self):
        from momentum.momentum.report.shift_overtime_analysis.shift_overtime_analysis import execute
        wc = frappe.db.get_value("Work Center", {}, "name")
        if not wc:
            self.skipTest("No Work Centers found")
        filters = {**self.base_filters, "work_center": wc}
        columns, data = execute(filters)
        self.assertIsInstance(data, list)
