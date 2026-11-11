# Kasuwa

Daily grain prices for markets in **Kano, Kaduna and Katsina**, so farmers can sell and buyers can buy without a middleman setting the price.

Kasuwa collects price reports from market agents, traders and farmers, checks them against each other, and proposes one price per commodity, per market, per day, with a low–high range and a confidence score. **Nothing is public until an admin reviews and publishes it** from the admin dashboard.

> **Status:** pilot build. The front end reads live prices from the API. If the API can't be reached within about a minute, it shows clearly labelled demo data instead.

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
├── web/index.html          public app (single page, English + Hausa)
├── web/admin.html          admin dashboard: review, adjust and publish prices
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
| POST | `/reports` | Submit a price. It goes to the review queue; nothing is published |
| GET | `/prices/today?commodity=maize-white&state=Kano` | Latest price in every market for one commodity |
| GET | `/prices/all?days=120` | Every published price for the last N days (used by the web app on load) |
| GET | `/prices/history?market=dawanau&commodity=maize-white&days=90` | Daily history for the trend chart |
| GET | `/forecast?market=dawanau&commodity=maize-white` | 7-day outlook with a 90% band |
| POST | `/engine/run` | Recomputes all proposals for a day (scheduled job). Needs `X-Admin-Token` |

Admin endpoints (all need the `X-Admin-Token` header = `ADMIN_TOKEN`):

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/admin/check` | 200 if the password is right |
| GET | `/admin/queue?day=` | Every proposal for a day, with last published price, flags and status |
| GET | `/admin/reports?market=&commodity=&day=` | The reports behind one proposal (phone numbers masked) |
| POST | `/admin/reports/{id}/review` | `{"decision": "include" \| "exclude" \| "auto"}`, then recomputes the proposal |
| POST | `/admin/publish` | `{"day": "...", "items": [{"market_id", "commodity_id", "price"?, "note"?}]}`; `price` overrides the proposal |
| POST | `/admin/unpublish` | Removes a published price |
| POST | `/admin/propose?day=` | Recomputes every proposal for a day |
| GET | `/admin/log?days=14` | Publish and unpublish history, with proposed vs published price |

Example report:

```bash
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{"market_id":"dawanau","commodity_id":"maize-white","price":560,"unit":"mudu","reporter_type":"trader","phone":"08012345678"}'
```

## Admin dashboard: reviewing and publishing

Open `admin.html` on the same site as the app (for example `https://kasuwa-web.onrender.com/admin.html`, or http://localhost:8080/admin.html locally).

1. **Sign in** with the admin password: the `ADMIN_TOKEN` value in Render → kasuwa-api → Environment (locally: `dev-admin-token`). It is kept only for the browser tab you are using.
2. **Review queue**: one row per market and commodity with reports (or an estimate from the last published price). Flagged rows come first:
   - **Big move**: more than 20% away from the last published price
   - **Outliers**: reports the model set aside
   - **Estimated**: no usable reports today
   - **Low confidence**: few reporters or reports far apart
3. **Reports**: opens the reports behind a proposal. For each one choose *Let the model decide*, *Always use* or *Leave out*; the proposal is recalculated.
4. **Final price**: starts at the proposal. Type a different number to override it.
5. **Publish** one row, or tick several and **Publish selected**. Only then does the price appear in the public app.
6. **Unpublish** takes a price back down (click twice to confirm). **Publish log** lists every publish and unpublish, with proposed vs published prices.

The page itself is public, but every action needs the password. Use a long, random `ADMIN_TOKEN` and change it if it leaks.

## Brand and design

The design source is the Figma file **Kasuwa — Rebrand** (brand board, phone screens, web home and admin). Keep code and Figma in step: change Figma first, then the CSS variables at the top of `web/index.html` and `web/admin.html`.

| Token | Value | Use |
| --- | --- | --- |
| Sahel green | `#0B5D44` | primary, price cards, links |
| Night | `#0A1F18` | text, tab bar, footer, admin sidebar |
| Millet gold | `#F5A524` | buttons and actions |
| Kano indigo | `#2C3E8F` | Kaduna markets, data accent |
| Laterite | `#C4622D` | Katsina markets, warnings |
| Sand / Paper / Line | `#F7F3EA` / `#FFFFFF` / `#E4DDCC` | background, cards, borders |
| Up / Down | `#178A52` / `#C23B2A` | price changes |

- **Type:** Bricolage Grotesque (headings and prices), Manrope (everything else), from Google Fonts.
- **Pattern:** the Arewa zigzag, used behind the green price card and the agents panel, never behind numbers.
- **Logo:** an ear of grain between two price bars. `web/icons/logo-mark.svg` (green tile, gold grain) is the app icon; `web/icons/logo-mark-gold.svg` (gold tile, dark grain) is used on dark backgrounds (footer, admin). The wordmark is lowercase **kasuwa** set in Bricolage Grotesque. App icons (`icon-*.png`) are rendered from the SVG; the maskable icon keeps the mark inside the safe zone.

## Photos

- Brand photos are `web/images/img-01` … `img-14` (WebP, quality 75), plus `img-02-og-share.jpg` for link previews. See `web/images/CREDITS.md`.
- White sorghum, brown beans and rice still use the older stock-photo names; run `bash web/images/get-photos.sh` once to fetch them, or add brand photos with those names.
- If a photo is missing, the app shows a drawing instead, so nothing breaks.

## How the front end finds the API

`web/index.html` picks the API address automatically:

| Where the page is open | API it uses |
| --- | --- |
| `localhost` / `127.0.0.1` | `http://localhost:8000` |
| GitHub Codespaces (`…-8080.app.github.dev`) | the same Codespace on port 8000 (set port 8000 to **Public** in the Ports tab) |
| anywhere else (Render, your domain) | `https://kasuwa-api.onrender.com` |

To point it somewhere else, set `<meta name="kasuwa-api" content="https://your-api">` near the top of `web/index.html`.

On free hosting the API sleeps when idle, so the page shows "Connecting to the price server…" for up to a minute on the first visit.

## How a price is made

1. **Normalise** – every report is converted to ₦ per 100 kg (`bag100`, `bag50` or `mudu`, using the market's mudu weight).
2. **Remove outliers** – each report gets a robust z-score against the median of today's reports plus yesterday's price; reports with |z| > 3.5 are set aside.
3. **Combine** – a trust-weighted median of the accepted reports. Weights: verified sale 1.0, agent 0.9, trader 0.6, farmer 0.3, times the reporter's own trust score. The 25th–75th percentile is the low–high range.
4. **Hold big moves** – a change above 20% from yesterday is published only if an agent and at least two reporters confirm it.
5. **Score confidence** – 0–100, higher with more reporters and closer agreement, lower without an agent. High ≥ 70, Medium 40–69, Low < 40.
6. **Fill gaps** – with no usable reports, the last published price is carried forward and moved by today's change at Dawanau, labelled *estimated*. After 3 trading days without reports it shows *No recent data*.
7. **Review** – every result above is only a *proposal*. An admin checks it in `admin.html`, can include or leave out reports and override the price, then publishes.
8. **Forecast** – a damped trend of the last 28 days. Replace with a seasonal / machine-learning model after 12 months of history.

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
- [x] Connect `web/index.html` to the API (with demo fallback)
- [x] Admin review and publishing dashboard with audit log
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
