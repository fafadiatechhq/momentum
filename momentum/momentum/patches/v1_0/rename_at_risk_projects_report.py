import frappe


def execute():
	old_name = "At-Risk Projects / Work Orders"
	new_name = "At-Risk Projects and Work Orders"
	if not frappe.db.exists("Report", old_name):
		return
	if frappe.db.exists("Report", new_name):
		frappe.delete_doc("Report", old_name, force=True, ignore_permissions=True)
	else:
		frappe.rename_doc("Report", old_name, new_name, force=True)
