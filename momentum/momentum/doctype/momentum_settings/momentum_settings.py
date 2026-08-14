import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, getdate


class MomentumSettings(Document):
	pass


@frappe.whitelist()
def backfill_snapshots(from_date, to_date):
	"""Rebuild snapshot rows for every date in [from_date, to_date]."""
	frappe.only_for(("System Manager", "Momentum Manager"))

	from_date = getdate(from_date)
	to_date = getdate(to_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	settings = frappe.get_single("Momentum Settings")
	companies = frappe.get_all("Company", pluck="name")
	if not companies:
		frappe.throw(_("No Company found on this site"))

	from momentum.momentum.aggregation.manufacturing import rebuild_operation_efficiency_snapshot
	from momentum.momentum.aggregation.services import (
		rebuild_project_snapshot,
		rebuild_utilization_snapshot,
	)

	days = date_diff(to_date, from_date) + 1
	current = from_date
	while current <= to_date:
		for company in companies:
			if settings.enable_services_pack:
				rebuild_project_snapshot(str(current), company)
				rebuild_utilization_snapshot(str(current), company)
			if settings.enable_manufacturing_pack:
				rebuild_operation_efficiency_snapshot(str(current), company)
		current = add_days(current, 1)

	return _("Rebuilt snapshots for {0} day(s).").format(days)
