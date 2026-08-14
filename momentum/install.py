"""App install hooks for Momentum."""

import os

import frappe

MOMENTUM_ROLES = (
	"Momentum Manager",
	"Momentum Services Viewer",
	"Momentum Manufacturing Viewer",
)


def ensure_momentum_roles():
	"""Create the three Momentum roles if they are missing."""
	for role_name in MOMENTUM_ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)
		print(f"[momentum] Created role: {role_name}")
	frappe.db.commit()


def assign_momentum_manager(user_name):
	"""Grant Momentum Manager to a user if they do not already have it."""
	if not frappe.db.exists("User", user_name):
		print(f"[momentum] User {user_name} not found — skipping role assignment")
		return
	user = frappe.get_doc("User", user_name)
	existing = {r.role for r in user.roles}
	if "Momentum Manager" in existing:
		return
	user.append("roles", {"role": "Momentum Manager"})
	user.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"[momentum] Assigned Momentum Manager role to {user_name}")


def after_install():
	ensure_momentum_roles()
	assign_momentum_manager("Administrator")


def after_migrate():
	"""Repair manufacturing demo data on sites that already ran the demo seed.

	Skipped on production installs (no `.momentum_seed_complete` sentinel) and
	when the setup wizard has not created a Company yet.
	"""
	sentinel = frappe.get_site_path(".momentum_seed_complete")
	if not os.path.exists(sentinel):
		return
	if not frappe.db.get_value("Company", {}, "name"):
		return
	from momentum.seed import seed_manufacturing_demo

	seed_manufacturing_demo()
