# SmartFit v2 — Private Fitness Prototype

Based on the team's original FastAPI SmartFit prototype. The original `smartfit.db` is retained **only as a legacy demo artifact**; this app uses `smartfit_private.db` by default. The legacy 100 demo records are **never shown** in personal dashboards.

## Included
- Email/password signup and login with Argon2 password hashing, signed HTTP-only session cookies and CSRF tokens.
- Google OpenID Connect sign-in **when OAuth credentials are configured**.
- One-time profile onboarding and later edits: age, height, current weight, optional target weight, goals, experience, schedule, equipment.
- Personal dashboard and per-account SQL queries; weight history; starter **rule-based** activity plans; workout log; recent activity dates; in-app reminders; achievements.
- Rule-based offline coach (not falsely presented as generative AI).
- Optional AI food-image **description** when OPENAI_API_KEY is provided; does not claim precise calories/macros and does not store photos.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# set SESSION_SECRET to a long random value (see .env.example)
uvicorn main:app --reload
```
Open http://127.0.0.1:8000 . **Do not commit real accounts or database files.**

## Google login setup
1. Create a Google Cloud OAuth client of type **Web application** and configure its consent screen.
2. Add `http://localhost:8000/auth/google/callback` as an authorized redirect URI (and your actual HTTPS deployment URL equivalent).
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` as environment variables. Never commit these credentials.
4. For Render, also set `SESSION_SECRET` and `HTTPS_ONLY=1` and ensure the app uses HTTPS.

## Deployment and persistence
`uvicorn main:app --host 0.0.0.0 --port $PORT` (on Render use a start command that expands PORT). SQLite on Render's ephemeral filesystem is **not durable**. For real users, migrate to a managed PostgreSQL database or configure a persistent disk before collecting accounts. Do not publish as production-ready until migration, account recovery, rate limiting, email verification, privacy notice, deletion and security review are completed.

## Feature status / limitations
- Google: fully coded but unavailable until Google credentials and redirect URI are configured.
- Plan: rules-based sample, not a medically personalized AI training plan.
- Coach: rules-based responses; generative chat is not yet implemented.
- Meal photo: optional vision model description; **not** verified nutrition estimation.
- Calendar: recent activity dates and scheduled reminders, not a full month-grid calendar.
- Reminders: in-app only; no background/push notifications.
- Achievements: session-count milestones.
- Personal data: stored in separate private tables; legacy `users` demo data not migrated.

## Quick checks
1. Sign up as A, complete profile, log a workout; log out.
2. Sign up as B; confirm A's workout and weight are not visible.
3. Log in as A; confirm workout still visible; edit profile and check history.
4. Set up Google credentials and test callback on registered redirect URL.
5. Create a backup before any migration. Use a persistent database before deploying to real users.

## V2 feature scope and limitations

- Private email/password accounts, Google OAuth sign-in (requires your own Google Cloud OAuth credentials), profile editing, private workout logs, rule-based plan generator, weight history, personal progress summaries, calendar, in-app reminders, achievements.
- Coach uses an AI API **only** if `OPENAI_API_KEY` is configured; otherwise uses clearly labelled offline responses.
- Meal photo description uses the API only when configured, and does **not** claim to measure calories or nutrition accurately.
- Reminders appear inside the dashboard; no push/email delivery.
- Google OAuth requires configuring your own authorized redirect URI: `/auth/google/callback` on the deployed domain (and local host for development). Do not commit credentials.
- A SQLite database on Render's ephemeral filesystem is not appropriate for persistent real user accounts. Configure persistent storage or migrate to PostgreSQL before deployment.
- No external end-to-end testing has been completed in this environment. Test registration, login, Google OAuth, profile isolation and AI endpoints before inviting real users.
