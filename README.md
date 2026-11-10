# Kasuwa

Daily grain prices for markets in **Kano, Kaduna and Katsina**, so farmers can sell and buyers can buy without a middleman setting the price.

Kasuwa collects price reports from market agents, traders and farmers, checks them against each other, and publishes one trusted price per commodity, per market, per day, with a low–high range and a confidence score.

> **Status:** starter code. The front end in `web/` still shows **sample data**; connecting it to the API is the next step (see [Roadmap](#roadmap)).

---

## What's in this repo

```text
kasuwa/
├── api/                    FastAPI back end (Python 3.12)
│   ├── app/
│   │   ├── main.py         app entry point
│   │   ├── config.py       settings from environment variables
│   │   ├── db.py           database connection
│   │   ├── models.py       database tables
│   │   ├── schemas.py      request/response shapes
│   │   ├── seed.py         loads 18 markets and 12 commodity grades
│   │   ├── routes/         /markets, /prices, /reports, /forecast, /engine
│   │   └── engine/
│   │       ├── model.py    the price model (pure functions)
│   │       └── run.py      publishes daily prices from reports
│   ├── tests/              pytest tests for the model and the API
│   ├── Dockerfile
│   └── requirements.txt
├── web/index.html          front end (single page, English + Hausa)
├── docker-compose.yml      PostgreSQL + API + front end, for local or Codespaces
├── .devcontainer/          GitHub Codespaces setup
├── .github/workflows/
│   ├── ci.yml              lint + test + build on every push; deploy on main
│   └── engine.yml          runs the price engine at 12:00 and 18:00 Lagos time
├── render.yaml             Render deploy settings (API + front end)
└── .env.example            environment variables template
```

## Markets and commodities

| State | Markets |
| --- | --- |
| Kano | Dawanau (anchor market), Singer, Bichi, Gwarzo, Kura, Wudil |
| Kaduna | Giwa, Makarfi, Zaria (Sabon Gari), Ikara, Saminaka, Kawo |
| Katsina | Charanchi, Funtua, Dandume, Malumfashi, Jibia, Katsina central |

Commodities: maize (white, yellow), sorghum (white, red), soybeans, sesame (white, mixed), beans (white, brown), millet, groundnut, rice paddy.

All prices are **naira per 100 kg bag**. Reports in mudu or 50 kg bags are converted automatically.

> The market trading days and mudu weights in `api/app/seed.py` are placeholders. Replace them with each market's real trading day and weights measured on site.

---

## Quick start: GitHub Codespaces (no local setup)

1. On the repo page click **Code → Codespaces → Create codespace on main**. Wait for it to finish installing (about 2–3 minutes).
2. In the terminal start the whole stack:

   ```bash
   docker compose up -d --build
   docker compose exec api python -m app.seed
   ```

3. Open the **Ports** tab:
   - port **8000** → add `/docs` to the URL to see and try every API endpoint
   - port **8080** → the front end
4. Send a test report from the `/docs` page (`POST /reports`), then open `GET /prices/today?commodity=maize-white`.
5. When you're done, stop the Codespace (**Codespaces** menu → **Stop current codespace**) so it doesn't use up your free hours.

## Running on your own computer

Needs Docker Desktop. Then the same commands:

```bash
git clone https://github.com/<your-username>/kasuwa.git
cd kasuwa
docker compose up -d --build
docker compose exec api python -m app.seed
```

API: http://localhost:8000/docs · Front end: http://localhost:8080

### Without Docker (API only)

```bash
cd api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                              # then edit DATABASE_URL
python -m app.seed
uvicorn app.main:app --reload
```

## Tests

```bash
cd api
pytest -q          # model + API tests (the API tests use a temporary SQLite file)
ruff check .       # lint
```

---

## API

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | Checks the API and database are up |
| GET | `/markets` | All markets |
| GET | `/commodities` | All commodity grades, English and Hausa names |
| POST | `/reports` | Submit a price; returns its status and the updated published price |
| GET | `/prices/today?commodity=maize-white&state=Kano` | Latest price in every market for one commodity |
| GET | `/prices/history?market=dawanau&commodity=maize-white&days=90` | Daily history for the trend chart |
| GET | `/forecast?market=dawanau&commodity=maize-white` | 7-day outlook with a 90% band |
| POST | `/engine/run` | Re-publishes all prices for a day. Needs header `X-Admin-Token` |

Example report:

```bash
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{"market_id":"dawanau","commodity_id":"maize-white","price":560,"unit":"mudu","reporter_type":"trader","phone":"08012345678"}'
```

## How a price is made

1. **Normalise** – every report is converted to ₦ per 100 kg (`bag100`, `bag50` or `mudu`, using the market's mudu weight).
2. **Remove outliers** – each report gets a robust z-score against the median of today's reports plus yesterday's price; reports with |z| > 3.5 are set aside.
3. **Combine** – a trust-weighted median of the accepted reports. Weights: verified sale 1.0, agent 0.9, trader 0.6, farmer 0.3, times the reporter's own trust score. The 25th–75th percentile is the low–high range.
4. **Hold big moves** – a change above 20% from yesterday is published only if an agent and at least two reporters confirm it.
5. **Score confidence** – 0–100, higher with more reporters and closer agreement, lower without an agent. High ≥ 70, Medium 40–69, Low < 40.
6. **Fill gaps** – with no usable reports, yesterday's price is carried forward and moved by today's change at Dawanau, labelled *estimated*. After 3 trading days without reports it shows *No recent data*.
7. **Forecast** – a damped trend of the last 28 days. Replace with a seasonal / machine-learning model after 12 months of history.

The model lives in `api/app/engine/model.py` and has no database code, so it is easy to read and test.

---

## Deploying (cloud only, free tiers to start)

Free tiers and prices change; check each provider's current plans. On free plans the API sleeps when idle and takes a little time to wake up – fine for the pilot, not for production.

### 1. Database – Neon

1. Sign up at neon.tech and create a project called `kasuwa` (pick the region closest to Nigeria).
2. Copy the connection string (`postgresql://...`).

### 2. API and front end – Render

1. Sign up at render.com with your GitHub account.
2. **New → Blueprint**, pick this repo. Render reads `render.yaml` and creates `kasuwa-api` and `kasuwa-web`.
3. When asked for `DATABASE_URL`, paste the Neon connection string.
4. After the first deploy, open the `kasuwa-api` **Shell** tab and run `python -m app.seed`.
5. Check `https://kasuwa-api.onrender.com/health` returns `{"status":"ok"}` (your URL may differ).

### 3. Automatic deploys and the daily price run – GitHub Actions

In the repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Where to get it |
| --- | --- |
| `RENDER_DEPLOY_HOOK` | Render → kasuwa-api → Settings → Deploy Hook |
| `API_URL` | Your API address, e.g. `https://kasuwa-api.onrender.com` |
| `ADMIN_TOKEN` | Render → kasuwa-api → Environment → `ADMIN_TOKEN` |

Now every push to `main` runs lint and tests, builds the Docker image, and deploys only if everything passed. `engine.yml` publishes prices at 12:00 and 18:00 Lagos time; run it by hand from the **Actions** tab to test.

### 4. Your own domain (optional)

Point `kasuwa.com.ng` at the `kasuwa-web` service and `api.kasuwa.com.ng` at `kasuwa-api` (Render → Settings → Custom Domains), then set `CORS_ORIGINS=https://kasuwa.com.ng` on the API.

## Environment variables

| Name | Purpose | Example |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@host/kasuwa` |
| `ADMIN_TOKEN` | Protects `POST /engine/run` | a long random string |
| `CORS_ORIGINS` | Which sites may call the API | `https://kasuwa.com.ng` |

Never commit real values. `.env` is in `.gitignore`.

---

## Roadmap

- [x] Price model and tests
- [x] API, database tables, seed data
- [x] Docker, Codespaces, CI/CD, scheduled price runs
- [ ] Connect `web/index.html` to the API (replace the sample-data generator with `fetch` calls)
- [ ] Alembic migrations (instead of creating tables on start-up)
- [ ] Phone-number login with SMS one-time codes; agent accounts with full weight
- [ ] Rate limiting on `POST /reports`; GPS check against market boundaries
- [ ] USSD menu and SMS alerts (Africa's Talking or similar)
- [ ] Monitoring: uptime check, Sentry, alert when a price run is missed
- [ ] Pilot in Dawanau, Giwa and Charanchi
- [ ] Android app (PWA / Capacitor) on Google Play
- [ ] Marketplace with escrow payments

## Contributing

1. Create a branch: `git checkout -b feature/short-name`
2. Make your change and add tests.
3. `ruff check . && pytest -q` in `api/`
4. Open a pull request; CI must pass before merging.
