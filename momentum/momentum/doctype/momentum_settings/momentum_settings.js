frappe.ui.form.on("Momentum Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Backfill Snapshots"), () => {
			frappe.prompt(
				[
					{
						fieldname: "from_date",
						fieldtype: "Date",
						label: __("From Date"),
						reqd: 1,
						default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
					},
					{
						fieldname: "to_date",
						fieldtype: "Date",
						label: __("To Date"),
						reqd: 1,
						default: frappe.datetime.get_today(),
					},
				],
				(values) => {
					frappe.call({
						method:
							"momentum.momentum.doctype.momentum_settings.momentum_settings.backfill_snapshots",
						args: values,
						freeze: true,
						freeze_message: __("Rebuilding snapshots..."),
						callback(r) {
							frappe.show_alert({
								message: r.message || __("Backfill complete"),
								indicator: "green",
							});
						},
					});
				},
				__("Backfill Snapshots"),
				__("Run")
			);
		});
	},
});
