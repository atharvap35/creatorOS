# Creator OS

Your daily operating system for turning content into a creator business — multi-tenant, account-scoped, and ready to deploy.

IF YOU ARE A CREATOR, SEE: [docs/CREATOR_GUIDE.md](https://github.com/atharvap35/creatorOS/blob/main/docs/CREATOR_GUIDE.md)

## The rule this product is built on

Every recommendation, answer, and number comes from a record the creator owns. The
product has no access to analytics platforms, follower counts, engagement rates, or
market benchmarks, and it will not estimate what it cannot see. When it does not have
enough information, it says so instead of producing a confident-sounding guess.

Three labels appear throughout the UI and are enforced in code:

| Label | Means |
| --- | --- |
| `user-entered` | A figure the creator typed themselves |
| `system-derived` | Computed deterministically from the creator's own rows |
| `ai-generated` | Text a configured AI provider drafted, from creator-supplied material only |

## What it does

### The daily loop

- **Today 3.0** — one decision, not a dashboard. The screen opens with a single "do this
  first" recommendation and its reasoning, followed by exactly three ranked next moves.
  Every move is stated as **What / Why / Impact / Effort / If it slips**, and carries an
  inline action. The rest of the page is money, capacity, and what needs attention.
- **Attention Center** (`/attention`) — everything that is slipping, waiting, or decaying,
  grouped by severity rather than by page. A payment overdue on an invoice is one item,
  not one item per surface it appears on: a deal-level "overdue" row is collapsed when
  the same money already appears as an unpaid payment.
- **Plan my week** (`/workflow/plan`) — a *proposal*, fitted to the hours the creator
  actually said they have. Nothing is scheduled until it is accepted, and items that do
  not fit are left out rather than silently overfilling a day. When the week is
  overcommitted it offers candidates to defer; it never reschedules anything unasked.
- **Timeline** (`/timeline`) — the creator's real history, written by the service layer
  when something actually happened: an idea converted, content published, a deal changed
  stage, a deliverable completed, a derivative created, a payment received. Nothing is
  generated retrospectively.
- **Reviews** — the weekly review answers what worked, what didn't, what slipped, which
  decisions were made, and what next week's focus is. `/reviews/business` is the CEO
  view: revenue and its sources, the content engine and series health, brand portfolio
  concentration, business risks, recorded decisions, and ranked priorities.

### The business model

- **Brands** — a relationship, not a logo: every deal, contact, lifetime value, and days
  since last touch, in one record.
- **Series** — a commitment, with published-vs-target progress and the next missing
  episode filled in automatically.
- **Offers** — what the creator actually sells, with the economics attached. An offer that
  has never been attached to a deal is surfaced as money on the table.
- **Deals** — lead to paid, with deliverables, follow-up dates, estimated hours, and
  profitability derived from the creator's own figures.
- **Money** — recorded revenue, outstanding balances with days outstanding, source mix,
  and a rate card.

### The content engine

- **Content pipeline** — idea to published, with briefs, production tasks, pillars, and
  series membership.
- **Atomization** — turn one published piece into many candidate atoms, grouped into
  core ideas, hooks, short-form, carousels, text posts, and stories. Atoms are extracted
  from the creator's own hook, script, and caption. Selected atoms become real drafts in
  the pipeline and **stop at the idea stage**; nothing is ever published automatically.
- **Ideas** — an explainable score built only from fields the creator set, with one-click
  conversion into a content plan, a brief, and a first task.

### Creator Copilot

The copilot answers questions about the creator's own records. Intent routing and the
answer skeleton are deterministic, so the same question against the same data produces
the same structure every time. It handles "what should I do", "what am I forgetting",
"which deal needs attention", "how much money am I waiting for", "what should I post",
"which ideas should I prioritize", "why is my workload too high", "what can I repurpose",
"my biggest opportunity", "what happened this week", "prepare me for tomorrow", and
"am I on track".

Asked something it cannot know — an engagement rate, a follower count, a market rate —
it refuses and explains why. Every exchange is stored with its intent, the records it
cited, and whether it was grounded.

### Voice

The microphone button in the corner starts a voice command, on every screen. Answers
are read back, and grounding is preserved: when the copilot refuses, the refusal is
spoken too, so it is never mistaken for an answer. Speech input uses the browser Web
Speech API, so it adds **no runtime dependency** and the product is fully usable
without it — Firefox has no speech input and gets a typing box instead.

One press opens **one** recognition session and holds it open, so a pause while you
think cannot make the microphone reopen or lose what you said. The session is never
restarted underneath you, which is what previously left the mic light on with no audio
arriving.

Speech is wired to the product's own actions, so a spoken command can never do more
than the button beside it. `"clear my day"` and `"rebalance my week"` run the
deterministic triage and capacity handlers — read-only, so they run immediately.
`"plan my week"` writes a plan record and is confirmed first, as is any capture.
Anything that writes asks and waits for a spoken or clicked yes.

Voice posts to `/api/actions/run`, which dispatches the same slug as the on-screen
button and takes `user_id` from the session, never the form. The numbers spoken back
come from the same deterministic service that fills the page.

### Money on the table

One ranked list of concrete, already-identified routes to money, each with a value, an
effort estimate, and a reason: unpaid invoices, agreed-but-uninvoiced deals, stalled
deals, unused offers, and open opportunities. No projections — every figure is attached
to a real record.

## Everything is optional AI

With no API key set, a deterministic built-in writer handles hooks, outlines, scripts,
captions, repurposing plans, follow-ups, and summaries entirely offline. Nothing is
auto-saved: output is a draft you review and copy yourself. If a configured provider
fails, the action reports the failure and **your data is unchanged**.

## Stack

FastAPI · SQLAlchemy 2 · SQLite (Postgres-ready via `DATABASE_URL`) · Jinja2 · server-rendered HTML

No frontend framework and no build step. Voice uses the browser's own Web Speech API, so
it contributes no dependency and nothing to install — where the browser does not support
it, the feature degrades to typing rather than failing.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:8000 → you'll be sent to `/register`. Create an account and the workspace is yours, seeded with a realistic starter dataset.

## Configuration

Copy `.env.example` to `.env`. Everything is optional in development:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///creator_os.db` | Point at Postgres in production |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address |
| `RELOAD` | `true` | Auto-reload in dev, `false` in production |
| `COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `PBKDF2_ITERATIONS` | `260000` | Password hashing cost |
| `SESSION_TTL_DAYS` | `30` | Login session lifetime |
| `AI_PROVIDER` | `builtin` | `openai` or `anthropic` to upgrade the writer |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — | Credentials and model for `AI_PROVIDER=openai` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | — | Credentials and model for `AI_PROVIDER=anthropic` |

With no AI variables set the app is fully functional offline; the built-in writer returns the same structure for the same request every time.

## Architecture

| Layer | Location | Responsibility |
| --- | --- | --- |
| Routes | `app/routes/` | One module per area, POST-redirect-GET, ownership enforced on every query |
| Services | `app/services/` | `brain`, `attention`, `actions`, `copilot`, `atomize`, `activity`, `insights`, `health`, `recommender`, `reviews`, `search`, `ai`, `seed` — all pure data, no HTTP concerns |
| Models | `app/models/` | 31 tables, every business row carrying `user_id` |
| Database | `app/database.py` | Engine, `Base`, `get_db`, additive SQLite migrations |
| Templating | `app/templating.py` | Jinja2 environment plus the `money` / `currency_symbol` globals |

`brain.snapshot()` is the single read that the new surfaces share: preferences, capacity,
money, deals, brands, content pulse, gaps, atomizable content, series, money-on-the-table,
and goals. Today, the Attention Center, the Copilot, and the business review all build on
that one snapshot rather than re-querying, so a number shown in two places is the same
number computed once.

Scoring lives in services rather than templates so a number is never produced without the
reason for it. `recommender.generate` returns the what/why/impact/effort/consequence
structure plus a score breakdown and a list of runnable action slugs; `attention.attention_center`
returns an item only when a record proves it, deduplicated so one obligation is reported
once; `copilot.ask` returns an intent, citations, and a `grounded` flag, and stores the
exchange. `actions.DISPATCH` maps a slug to a real mutation or a reviewable draft, and
every handler scopes to the session's `user_id`.

Voice talks to the product through exactly two JSON routes, both of which call the same
service function as the corresponding HTML route and both scoped by the same
`get_current_user` dependency:

| Route | Calls | Purpose |
| --- | --- | --- |
| `POST /api/copilot/ask` | `copilot.ask` | A grounded answer as JSON |
| `POST /api/actions/run` | `actions.run` | An action result as JSON |

Neither is a second implementation. `actions.run` takes the same slug and parameters the
button does and returns the same message the page would show, so a spoken answer can
never be more capable — or more inventive — than the typed one.

## Security model

- Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib) — plaintext is never stored.
- Logins issue a random 256-bit session token stored in `session_tokens` and set as an `HttpOnly`, `SameSite=Lax` cookie. Logout deletes the row server-side.
- Unauthenticated browser requests to protected pages redirect to `/login?next=…`; post-login redirects are restricted to an allowlist of known app paths, so `next` cannot be used as an open redirect.
- Every query filters on `user_id`, including deletes, status updates, and detail lookups, so cross-account tampering returns "not found" behavior rather than leaking data.
- Search, the command palette, insights, and health all take a `user_id` and query within it — there is no unscoped read path.

## Documentation

[`docs/CREATOR_GUIDE.md`](docs/CREATOR_GUIDE.md) is the end-user walkthrough: 21 sections
covering every screen, with 59 screenshots of the running application in
`docs/screenshots/`. It includes a grounded copilot answer, an honest refusal, a proposed
week awaiting acceptance, a generated follow-up draft, 21 atoms extracted offline from
a single published piece, the voice dock listening, answering, refusing, and asking for
confirmation before it changes anything, and a second workspace built from a real public
YouTube channel feed.

Regenerate it with a seeded demo workspace:

```bash
python make_demo.py                    # builds demo.db from app/services/seed.py
python -m uvicorn app.main:app --port 8077
python capture.py                      # every screen  -> docs/screenshots/
python capture_states.py               # working states -> docs/screenshots/
```

A second workspace, `beyounick`, is built from a real public YouTube channel feed:

```bash
python seed_beyounick.py               # 62 records, idempotent
python -m uvicorn app.main:app --port 8078
python capture_beyounick.py            # that workspace -> docs/screenshots/
```

Its 15 published videos, series, and sponsor are real, read from the channel's own
public RSS feed; every figure involving money is a labelled placeholder, because
creator rates are not public. Instagram returned a login wall and yielded nothing, so
no Instagram data was invented.

## Currency

Each account has a preferred currency (Settings → Profile). It is applied to **every** amount in the product — dashboard tiles, deal values, revenue rows, forecasts, rate cards, and opportunity estimates — so switching USD → INR updates the whole app immediately. Formatting lives in `app/currency.py` (symbol map, thousands separators, Indian digit grouping for INR, compact `₹1.2K` form for charts) and is exposed to templates as the `money` / `money_compact` globals. Preference is loaded per request by middleware and scoped to the signed-in account, so two accounts can use different currencies at the same time.

## Multi-tenancy

Tenancy is row-level (`user_id` foreign key on every business table) inside one database. This is the right trade-off versus one database file per account: it keeps queries, migrations, and backups to a single operational surface while providing the same isolation guarantees at the application layer. To move to a database-per-account later, point `DATABASE_URL` at Postgres and add a schema-per-tenant resolver in `app/database.py` — the route layer needs no changes.

Existing SQLite databases are migrated in place on startup: `app/database.py:_apply_sqlite_migrations` adds missing tables and missing columns (including `user_id`) with `ALTER TABLE`. The 2.0 expansion was additive only — no existing column is rewritten or dropped, so upgrading from an earlier version preserves your data. Legacy rows without an owner stay invisible to every account.

## Legacy routes

The original URLs still work, so bookmarks and any external links keep functioning: `/dashboard` → `/today`, `/tasks` → `/workflow`, `/revenue` → `/money`, `/opportunities` → `/growth/opportunities`. The corresponding `POST` endpoints (`/tasks`, `/revenue`, `/opportunities`) are kept as aliases of their new handlers, and `/tasks/{id}/complete` and `/tasks/{id}/delete` are aliases of the workflow equivalents.

## Capacity comes from the creator, not a constant

Every load, overload, and rebalancing number in the product is derived from fields the
creator sets in **Settings → Your working rhythm** (`POST /settings/capacity`), stored on
`creator_preferences`:

| Field | Effect |
| --- | --- |
| `working_days` | Which weekdays the creator works. Stored as names (`Mon,Tue,…`) and parsed with `CreatorPreference.working_day_list()`, which also accepts legacy numeric indexes so rows written before the settings page still resolve. |
| `hours_per_day` | Hours available on each of those days. Clamped to 0–24. |
| `peak_hour` | The hour the creator says they work best. Optional, 0–23. |
| `monthly_revenue_target` | The creator's own revenue target, used by goals and money-on-the-table. No benchmark is substituted. |
| `series_length_default` | Default target episode count when creating a series. |
| `timezone` | One of the supported zones in the picker. |

`brain.capacity` then reports `available_hours`, `planned_hours`, `capacity_pct`,
`over_capacity`, and `overload_hours` as `system-derived`. Un-ticking every weekday falls
back to Monday–Friday rather than dividing by zero, so an empty selection cannot produce a
nonsensical capacity figure or a crash.

## Testing

```bash
pytest -q
```

100 tests across four files. The suite is slow by design: password hashing uses PBKDF2
at production cost, and each test rebuilds the whole schema. That cost is not lowered
for test speed.

- `tests/test_dashboard.py` and `tests/test_creator_os.py` — the 2.0 contract, all 36
  tests, still passing unchanged: registration, auth, cross-account isolation and tamper
  attempts, CRUD, status transitions, filters, per-account currency, every page
  rendering, legacy URLs resolving, idea→content conversion, recommendations being
  deterministic and explainable, and the AI path degrading safely.
- `tests/test_creator_os_3.py` — the 3.0 contract: every new page renders for both a
  realistic creator and a genuinely empty one; attention items are evidence-backed, the
  same obligation is never double-counted, and two genuinely separate obligations of the
  same amount are both still reported; the copilot answers from records, cites them,
  and refuses to invent engagement rates, follower counts, or market rates; drafting
  actions return text and change nothing while executing actions persist real records;
  an action naming another creator's id fails; atomization never publishes and refuses
  cross-tenant content; reviews carry the full CEO structure and match the underlying
  rows; the timeline records each real mutation; the week planner proposes, accepts,
  and dismisses without scheduling anything before acceptance; capacity is computed
  from the creator's own working rhythm rather than any hard-coded constant; and the
  JSON action endpoint voice posts to returns the same result as the button, refuses
  unknown slugs, rejects anonymous callers, and stays scoped to one account. Two more
  tests pin the revenue source mix: every grouped source returns a real integer count,
  and the shares sum to a full 100. The first exists because an unlabelled
  `func.count` is named `count_1` internally, so reading it as `row.count` fell through
  to a Row class-level accessor and rendered a repr of a bound method — literally
  `Sponsorship (<function Row._special_name_accessor...>)` — in the page.
- `tests/test_voice_browser.py` — the voice dock in a real browser: one press opens
  exactly one recognition session and it is never restarted, the microphone is released
  when speech arrives, interim words appear live, `no-speech` offers the typing box
  instead of looping, each command routes correctly, and the mutating verbs confirm
  first. Speech recognition and `speechSynthesis` are read-only in Chromium, so the
  tests redefine them with a stub that records every session constructed — which is what
  makes a restart storm visible as a count instead of as a vague "it didn't work".

  These need Playwright **and a server running on port 8078**:

  ```bash
  pip install playwright && playwright install chromium
  python -m uvicorn app.main:app --port 8078
  pytest tests/test_voice_browser.py -q
  ```

  Without Playwright installed the file skips itself, so the default `pytest -q` run
  stays browser-free.

## Deployment

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000     # no reload in production
```

Set `DATABASE_URL`, `COOKIE_SECURE=true`, and `RELOAD=false`. `GET /health` returns `{"status": "ok"}` for load balancers. Schema creation and migrations run on startup via the FastAPI lifespan handler, so a fresh deployment needs no manual migration step.
