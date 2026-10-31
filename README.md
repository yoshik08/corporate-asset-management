# Corporate Asset Management System

Track company assets (laptops, phones, vehicles, equipment) across their
whole lifecycle: employees, assignments, returns, maintenance, audit
history, plus a Python model that predicts when each asset will next need
maintenance.

## Stack

- **Backend:** Python 3 + Flask, SQLite (no server to install)
- **Frontend:** single-page dashboard (vanilla JS, no build step)
- **Prediction:** ridge regression in numpy, trained on the maintenance
  history already in the database. Falls back to per-category median
  service intervals when there is too little history.

## Run it locally

```bash
cd asset-manager
python -m venv venv
venv/bin/pip install -r requirements.txt   # Windows: venv\Scripts\pip install -r requirements.txt
venv/bin/python app.py                      # Windows: venv\Scripts\python app.py
```

Open http://127.0.0.1:5000

First run auto-creates the database and seeds demo data (12 employees,
22 assets, active + returned assignments, 2 years of maintenance history).
To re-seed from scratch: delete `asset_manager.db` and run `python seed.py`,
or just run `python seed.py` (it wipes and re-seeds).

## Deploy (GitHub + Vercel)

The repo is https://github.com/yoshik08/corporate-asset-management and the
live deployment is on Vercel. The frontend is served statically from
`public/` and every `/api/*` request is routed to the Flask app in
`api/index.py` (see `vercel.json`).

Vercel note: the deployment filesystem is read-only except `/tmp`, so on
Vercel the SQLite database lives at `/tmp/asset_manager.db` and is built
fresh (seeded demo data) on each serverless instance's first request. That
means edits on the live demo reset when Vercel recycles the instance — it
is a demo, not durable storage. For durable data, point `db.py` at a hosted
database (e.g. Vercel Postgres) instead.

## What it does

| Area | Features |
|---|---|
| Assets | CRUD, filter by category/status, search by tag/brand/serial, condition + usage hours |
| Employees | CRUD, department/role |
| Assignments | assign only available assets, expected return dates, overdue flagging |
| Returns | return flow records condition; damaged/poor returns send the asset to maintenance |
| Maintenance | log preventive/corrective work with cost; logging a service clears `in_maintenance` |
| Predictions | per-asset next service date, days remaining, risk score (0-100) + risk level |
| Audit history | every create/update/assign/return/maintenance is logged with actor + details |

## API

All endpoints return JSON under `/api/`:

- `GET /api/stats` — dashboard counts
- `GET/POST /api/assets`, `GET/PUT/DELETE /api/assets/<id>`
- `GET/POST /api/employees`, `PUT/DELETE /api/employees/<id>`
- `GET/POST /api/assignments`, `POST /api/assignments/<id>/return`
- `GET /api/returns`
- `GET/POST /api/maintenance`
- `GET /api/predictions` — `{ predictions: [...], model: { method, training_samples, training_mae_days } }`
- `GET /api/audit?entity_type=&limit=`

## The predictor, briefly

For every pair of consecutive services on the same asset, the model learns
`days until next service` from asset age, days since last service, service
count and category. At prediction time it projects the next service date
from the last service (or purchase date if never serviced) and scores risk
from days remaining, condition, age and usage hours. The dashboard shows
the training sample count and mean absolute error so the prediction
quality is visible, not hidden.
