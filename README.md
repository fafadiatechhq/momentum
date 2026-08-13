<p align="center">
  <img src="logo.png" alt="Momentum" width="300" />
</p>

# Momentum for ERPNext

Momentum turns the timesheets and job cards your team already logs in ERPNext into a live management intelligence layer — utilization rates, project profitability, billing leakage, and labor efficiency, all inside your existing ERPNext Desk. No new portal, no new login.

---

## What You Get

### Services Businesses
- **Utilization Dashboard** — see at a glance who is billable, who is on the bench, and how the team tracks against your target utilization %.
- **Project Cost vs Budget** — know in real time whether a project is on track, at risk, or over budget, before the invoice goes out.
- **Unbilled Hours (WIP)** — find billable hours that have not been invoiced yet, grouped by client and aged by how long they have been sitting.
- **Realization Rate** — compare what you billed against what your hours were worth at standard rates. Spot discounting and write-offs quickly.
- **Bench Report** — list every employee below your utilization target so you can act before idle time compounds.
- **Time Entry Compliance** — see which employees are missing or late on timesheets against expected working days.
- And more: Activity Type Breakdown, Task Estimate vs Actual, Client Effort Distribution, Margin Trend by Project.

### Manufacturing Businesses
- **Operation Efficiency Report** — actual time vs standard time per operation and work center.
- **Labor Cost Variance** — actual labor cost from Job Cards vs BOM standard costs.
- **Work Center Utilization** — booked hours vs available capacity per work center.
- **Operator Productivity** — efficiency % and output by employee.
- **Shift & Overtime Analysis** — hours by shift with overtime flags.

All reports appear inside Frappe's standard Report view. All dashboards appear inside Frappe's native Dashboard view. Nothing outside ERPNext Desk.

---

## Prerequisites

- ERPNext **v15** installed and running on your bench.
- Employees, Projects (for services) or Work Orders / Job Cards (for manufacturing) already being logged in ERPNext.
- Site Administrator access to run bench commands.

---

## Installation

Run the following on your bench server:

```bash
cd /path/to/your/bench

# 1. Download the Momentum app
bench get-app https://github.com/fafadiatech/momentum --branch main

# 2. Install it on your site
bench --site your-site.com install-app momentum

# 3. Run migrations
bench --site your-site.com migrate
```

---

## First-Time Setup (5 minutes)

After installation, complete these steps inside ERPNext:

### Step 1 — Open Momentum Settings
Search for **Momentum Settings** in the search bar (or go to **Awesome Bar → Momentum Settings**).

Configure the following:
| Setting | What it means | Suggested default |
|---|---|---|
| Standard Working Hours Per Day | How many hours counts as a full working day | 8 |
| Utilization Target % | Your firm's billable hours target | 75 |
| Cost Rate Source | Where Momentum reads employee cost rates from | Employee Cost Rate |
| Budget Overrun Threshold % | At what % of budget a project turns "At Risk" | 90 |
| Enable Services Pack | Turn on services reports and dashboard | ✓ |
| Enable Manufacturing Pack | Turn on manufacturing reports and dashboard | As needed |

### Step 2 — Backfill Historical Data
If you have existing timesheet history you want to see in Momentum dashboards, click the **Backfill Snapshots** button on Momentum Settings and enter your desired date range.

This is a one-time step. From then on, Momentum updates its snapshots automatically every night.

### Step 3 — Assign Roles
Go to **Setup → Users** and assign the appropriate Momentum role to each user:

| Role | Who gets it |
|---|---|
| **Momentum Manager** | Delivery heads, ops leads, finance — full access to all reports |
| **Momentum Services Viewer** | Project managers, consultants — read-only access to services reports |
| **Momentum Manufacturing Viewer** | Production supervisors — read-only access to manufacturing reports |

---

## Daily Operation

Once set up, Momentum runs on its own:

- **Every night**, it rebuilds the previous day's snapshot data automatically (utilization, project costs, operation efficiency).
- **Reports** can be run on demand from the Reports module — use date range, company, project, employee, or department filters to slice the data.
- **Dashboards** show rolling trend data based on the nightly snapshots.

---

## Troubleshooting

**Reports show no data**
Make sure timesheets are submitted (not saved as drafts) and that the date range you are filtering on has submitted timesheet rows.

**Dashboard charts are empty**
Run a Backfill Snapshots for the date range you want to see. Charts are driven by snapshot data, not live queries.

**I don't see the Momentum workspace**
Make sure your user has one of the three Momentum roles assigned. Log out and back in after role assignment.

**The nightly job did not run**
Check that the bench scheduler is running on your server (`bench scheduler status`). If it was stopped, restart it and the next night's job will run automatically.

---

## Support

For questions, bugs, or feature requests, contact [Fafadia Tech](mailto:customercare@fafadiatech.com).

---

## License

MIT
