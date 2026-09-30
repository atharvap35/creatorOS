# Creator OS — the complete creator guide

A walkthrough of every screen, written against the running application. Every figure
quoted below is one the app computed from the demo creator's own records, and every
screenshot is a real capture of that page.

> **The one rule everything else follows**
> Every number, recommendation and answer in this product comes from a record the
> creator owns. Creator OS has no access to YouTube, Instagram or any analytics
> platform. It does not know your follower count, your engagement rate, or what the
> market pays. Where it cannot answer from your records, it says so.

**Contents**

1. [Getting in](#1-getting-in)
2. [Set your working rhythm first](#2-set-your-working-rhythm-first)
3. [The daily loop](#3-the-daily-loop)
4. [The Attention Center](#4-the-attention-center)
5. [The Creator Copilot](#5-the-creator-copilot)
6. [Workflow, focus, and planning your week](#6-workflow-focus-and-planning-your-week)
7. [The content engine](#7-the-content-engine)
8. [Ideas](#8-ideas)
9. [Deals, brands, and offers](#9-deals-brands-and-offers)
10. [Money](#10-money)
11. [Growth and opportunities](#11-growth-and-opportunities)
12. [Goals](#12-goals)
13. [Reviews: weekly, monthly, business](#13-reviews-weekly-monthly-business)
14. [Timeline](#14-timeline)
15. [Library, calendar, assistant, search](#15-library-calendar-assistant-search)
16. [Actions: what "do it" actually does](#16-actions-what-do-it-actually-does)
17. [Settings](#17-settings)
18. [Your first week, step by step](#18-your-first-week-step-by-step)
19. [Screen reference](#19-screen-reference)

---

## 1. Getting in

Registration seeds a realistic starter workspace so the app is useful immediately, and
so nothing you read below is a screenshot of an empty database.

![Login](screenshots/01-login.png)

![Register](screenshots/02-register.png)

Once signed in you land on **Today**. Your workspace name sits in the sidebar
(`USD workspace` in these captures — currency is per-account, see §18), and
`Ctrl K` opens search and the command palette from anywhere.

---

## 2. Set your working rhythm first

This is the one setup step worth doing before anything else, because Creator OS never
guesses how much you can work. Every over-capacity warning, the week planner, and the
"why is my workload too high" answer all read from these numbers.

![Settings](screenshots/33-settings.png)

In **Settings → Your working rhythm** you set:

| Field | What it drives |
| --- | --- |
| **Working days** | Which weekdays you work. Tick Mon–Fri for a normal week, or Mon/Tue only if that is your reality. |
| **Hours available per working day** | The ceiling for the week. Clamped to 0–24. |
| **Peak working hour** | Optional, 0–23. The hour you say you work best. |
| **Monthly revenue target** | Your target, used by goals and money-on-the-table. No benchmark is substituted for it. |
| **Default series length** | Target episode count applied when you start a series. |
| **Timezone** | Used for dates across the app. |

The panel above the form shows the live result — `10.8h planned against 20.0h
available this week (54% of capacity)` — and updates as soon as you save.

Un-ticking every day falls back to Monday–Friday rather than dividing by zero, so an
empty selection can never produce a nonsense number or a crash.

---

## 3. The daily loop

**Today** is built to answer one question: *what do I do first?* It is not a dashboard
of everything you own.

![Today](screenshots/03-today.png)

The page has four bands:

1. **Do this first** — a single recommendation, with a "fits in ~10 min" effort hint and
   the full reason. In the demo this is *"Follow up with GadgetCo — USD 8000 overdue"*,
   because the payment is 2 days past its due date. There is a **Why this ranked first**
   disclosure showing the score breakdown.
2. **Then, in this order** — exactly three more moves, ranked by urgency, impact and
   effort. Each expands into `WHAT / WHY / IMPACT / EFFORT / IF IT SLIPS`.
3. **Needs attention** — the top of the Attention Center (§4), with money at risk.
4. **Money**, **This week**, and **Recently** — the numbers and the newest activity.

The header line is your real position: `5 need attention now · $23,890.00 unpaid`.

Every recommendation carries a runnable action, not just advice — **Draft follow-up**,
**Draft invoice**, **Draft reminder**, **Mark received**, **Open**, **Mark done**.

---

## 4. The Attention Center

One list of everything slipping, waiting, or decaying, grouped by severity. The premise
is that an item only appears when a **record proves it**.

![Attention Center](screenshots/04-attention.png)

In the demo workspace this is 20 items: 5 high, 9 medium, 6 low.

**High**
- Overdue task: Outline Notion vs Obsidian follow-up
- GadgetCo campaign deadline passed 4 day(s) ago
- Overdue task: Send GadgetCo the final invoice
- USD 8,000 unpaid — Winter Bundle
- Nova Labs has no follow-up scheduled

**Medium** — past-due content, unpaid invoices, a deal invoiced but not recorded as
received, more overdue tasks.

**Low** — 32 captured ideas never turned into content, two goals behind target, three
offers never used in a deal.

Each item shows a provenance badge (`user-entered` / `system-derived` / `ai-generated`),
its age, and a real action button: **Complete Task**, **Draft Reminder**, **Draft Follow
Up**, **Mark Paid**, **Create Content Plan**, **Create Opportunity**.

You can filter by kind — content, deal, goal, idea, offer, payment, task — and the
footer shows this week's capacity.

**One obligation is one row.** If a payment and a deal describe the same money, you see
the payment (the more precise record) and the deal still appears for its *other*
problems. But two genuinely separate invoices of the same amount are both shown —
matching is on the counterparty *and* the amount, never the amount alone.

---

## 5. The Creator Copilot

Ask a question, get an answer computed from your records — or an honest refusal.

![Copilot](screenshots/05-copilot.png)

The header states the contract plainly: *Answers from your own records — or an honest
"I don't know."* Twelve suggested questions are offered, or type your own.

**When it can answer**, it cites what it used:

![Copilot answer](screenshots/44-copilot-answer.png)

> *What am I forgetting?*
>
> You have 20 thing(s) worth attention:
> - **Overdue task: Outline Notion vs Obsidian follow-up** — Was due 2026-09-24, 6 day(s) ago.
> - **GadgetCo campaign deadline passed 4 day(s) ago** — 'Winter Bundle' was due 2026-09-26 and is still open.
> - **USD 8,000 unpaid — Winter Bundle** — Overdue by 0 day(s)…
>
> *(tagged `What Am I Forgetting` · `Grounded In Your Data` · `6 record(s) cited`)*

**When it cannot**, it refuses rather than inventing a metric:

![Copilot refusal](screenshots/45-copilot-refusal.png)

> *what is my engagement rate*
>
> I don't have enough information to answer that. I can only answer from records you
> have entered — content, deals, payments, tasks, goals and your preferences. I won't
> guess, and I don't have access to external data like follower counts, engagement
> rates, or market benchmarks.
>
> *(tagged `Unanswerable` · `Not Enough Data`)*

Intent routing is deterministic, so the same question against the same data always
produces the same answer. Every exchange is saved to your history with its intent, the
records it cited, and whether it was grounded.

---

## 6. Workflow, focus, and planning your week

**Workflow** is your task list: what is open, what is overdue, what is due.

![Workflow](screenshots/07-workflow.png)

**Focus mode** narrows to the single thing you are doing now.

![Focus mode](screenshots/08-workflow-focus.png)

**Plan my week** is labelled *A proposal, not an order.* It fits your open tasks,
deliverables with deadlines, and repurposeable content into the hours you declared in
§2. **Nothing is scheduled until you accept.**

![Week plan](screenshots/09-workflow-plan.png)

Press **Propose my week** and you get a real schedule:

![Week proposed](screenshots/46-week-proposed.png)

> **Proposed week — 12 items placed**
> - MON 28 Sep — Chase Acme Brand on the summer invoice · 10 min · urgent
> - MON 28 Sep — Record Ship in Public 04 · 90 min · high
> - MON 28 Sep — Edit AI Tools Nobody Talks About · 120 min · high
> - TUE 29 Sep — Publish the 30 minute workflow newsletter · 30 min · high
> - TUE 29 Sep — Send TechCorp the laptop review draft · 45 min · high
> - TUE 29 Sep — Atomize "The honest cost of running a channel" · 20 min · medium
> - … and six more
>
> **Accept this week** / **Not this week**

Accepting records the plan day against your own tasks and deliverables. It creates and
deletes nothing. Dismissing discards the proposal and changes nothing at all.

If a week is over-committed, the Copilot can produce a rebalance, and applying it moves
work rather than dropping it.

---

## 7. The content engine

**Content** lists every piece you own with its stage.

![Content](screenshots/10-content.png)

**Pipeline** is the same records as a board, for moving items between stages.

![Pipeline](screenshots/11-content-pipeline.png)

**Pillars** are your recurring themes.

![Content pillars](screenshots/12-content-pillars.png)

### Atomize — one piece into many

Open any published piece and choose **Atomize**. Atoms are extracted from *that item's
own text* — its hook, script, and caption.

![Atomize](screenshots/40-atomize.png)

Before generating, the page states the rules: only text you wrote is used, each atom is
a candidate rather than a commitment, and selected atoms become drafts **at the idea
stage — nothing is published**.

Press **Generate repurposing plan** and it works offline with no API key:

![Atomize generated](screenshots/48-atomize-generated.png)

> **21 atoms** across six groups — CAROUSEL, CORE IDEA, FUTURE IDEA, HOOK, SHORT FORM,
> STORY, TEXT POST. Each is a title drawn from your own material, e.g.
> *"The single argument this piece makes, stated in one sentence"*,
> *"I tested 5 Productivity Apps I Actually Use for 30 days — here's what actually worked"*.
>
> **Create selected drafts** — *Creates content records at the idea stage. Nothing is
> published.*

If you have configured an AI provider, **Regenerate with AI** will rephrase your own
material. **Regenerate offline** always works.

### Content detail

![Content detail](screenshots/39-content-detail.png)

### Repurpose

![Repurpose](screenshots/41-repurpose.png)

---

## 8. Ideas

Ideas are captured fast and scored explainably — the score is built only from fields you
set, never from an engagement guess.

![Ideas](screenshots/13-ideas.png)

Open one:

![Idea detail](screenshots/43-idea-detail.png)

The highest-leverage action here is **turn into content**, which creates a real content
record, a brief, and a first task. The Attention Center flags the pile-up: in the demo,
*"32 captured idea(s) never turned into content."*

---

## 9. Deals, brands, and offers

### Deals

![Deals](screenshots/14-deals.png)

A deal is a campaign with a stage, a value, a currency, a deadline, a payment status,
deliverables, and a follow-up date.

![Deal detail](screenshots/35-deal-detail.png)

**A deal is a business relationship, not a logo.** That is why brands exist as their own
record.

### Brands

![Brands](screenshots/15-brands.png)

A brand holds every deal, contact, lifetime value, and days since last touch.

![Brand detail](screenshots/36-brand-detail.png)

### Offers

An offer is something you *sell* — a productised service with a price. Defining them is
how the app can tell you an offer has never been used in a deal.

![Offers](screenshots/16-offers.png)

![Offer detail](screenshots/37-offer-detail.png)

An unused offer gets a **Find it someone** action, which creates an opportunity in one
click.

### Series

A series is a named body of work with a target episode count, so you can see where a
recurring format actually stands.

![Series](screenshots/17-series.png)

![Series detail](screenshots/38-series-detail.png)

When a series is short of its target, the detail page offers **Plan episode N** as a
real action.

---

## 10. Money

**Money** is the payment tracker: what came in, what is still owed, and what your own
records project forward.

![Money](screenshots/18-money.png)

> THIS MONTH $320.00 *(last month $9,640.00)* · YEAR TO DATE $28,540.00 ·
> OUTSTANDING $23,890.00 *(3 unpaid items)* · RECURRING $0.00

Every row has a status you can set — **Pending**, **Received**, **Overdue** — and a due
date, which is what makes "overdue by N days" possible in the Attention Center.

![Payments](screenshots/19-money-payments.png)

### Rate card

![Rate card](screenshots/20-rate-card.png)

What each deliverable costs you, with three price points so you can negotiate a range.
This is *your* number, not a market benchmark.

**Marking a payment received is a one-click action**, and the Attention Center's
`USD 6,000 invoiced but not recorded as received` item exists precisely to catch the
case where you forgot.

---

## 11. Growth and opportunities

**Money on the table** is one ranked list of concrete, already-identified routes to
money — unpaid invoices, agreed-but-uninvoiced deals, stalled deals, unused offers, and
open opportunities. Each carries a value, an effort estimate, and a reason.

![Growth](screenshots/22-growth.png)

Opportunities you are tracking:

![Opportunities](screenshots/21-opportunities.png)

![Opportunity detail](screenshots/42-opportunity-detail.png)

An opportunity can be converted to a real deal in one click.

---

## 12. Goals

![Goals](screenshots/23-goals.png)

Progress is computed live from your records — revenue this month is the sum of your
received rows, published items counts your published content, and so on. The Attention
Center flags anything behind target with a deadline, e.g. *"Behind target: Earn 12,000
this month."*

---

## 13. Reviews: weekly, monthly, business

### Weekly

![Weekly review](screenshots/24-reviews-weekly.png)

The CEO loop for one week: what moved, what slipped, the decisions you made, capacity,
what needs attention, and a ranked focus list.

### Monthly

![Monthly review](screenshots/25-reviews-monthly.png)

### Business review

The whole business at once.

![Business review](screenshots/26-reviews-business.png)

> **Revenue** (system-derived) — THIS MONTH $320.00 · −97% vs last month ·
> YEAR TO DATE $28,540.00 · OUTSTANDING $23,890.00 ($8,000.00 overdue),
> broken down by month and by source.
> **Content engine** — series health.
> **Brand portfolio** — concentration share, so you can see over-dependence on one
> sponsor.
> **Business risks** · **Decisions you made** · **Priorities** — each priority carries
> a runnable action (Draft Invoice, Pursue Opportunity, Draft Reminder).

---

## 14. Timeline

A chronological record of real activity, grouped by day.

![Timeline](screenshots/06-timeline.png)

Only real mutations appear. Drafting a message creates no timeline entry, because it
changes nothing.

---

## 15. Library, calendar, assistant, search

**Library** — your reusable assets, templates, and briefs.

![Library](screenshots/29-library.png)

**Calendar** — everything with a date, in one month view.

![Calendar](screenshots/28-calendar.png)

**Assistant** — the writing tool: hooks, outlines, scripts, captions, repurposing plans,
summaries. Works fully offline. Output is a draft you review and copy; nothing is
auto-saved.

![Assistant](screenshots/30-assistant.png)

**Search and the command palette** — one box across every record type, reachable with
`Ctrl K` from anywhere.

![Search](screenshots/31-search.png)

**Quick capture** — drop an idea or task without leaving what you were doing.

![Quick capture](screenshots/32-quick.png)

---

## 16. Voice

The microphone button in the corner starts a voice command. Answers are read back to
you, and everything works silently if you turn spoken replies off.

![Voice](screenshots/50-voice-answer.png)

**How it works.** One press opens one recognition session and holds it open. You
speak, pause, and the command runs — the microphone is never reopened underneath you,
so a long pause will not make it go quiet or lose what you said. In-progress words
appear in the panel as they are heard, so you can tell the moment the mic is picking
you up.

**Say things like:**

| Say | What happens |
| --- | --- |
| "what should I do" | Copilot answers from your own records |
| "what am I forgetting" | Everything overdue or stalled |
| "how much money am I waiting on" | Cash you are owed, and how overdue |
| "clear my day" | Sorts today's work into must do / should do / can wait |
| "rebalance my week" | Says whether you are over capacity, and what could move |
| "plan my week" | Builds a week plan from your deadlines and working days |
| "capture an idea about hook structures" | Saves an idea, after you confirm |
| "remind me to email Acme" | Saves a task, after you confirm |
| "go to money", "open deals" | Moves you there |
| "search for Acme" | Searches everything |
| "read this page" | Reads the page aloud |
| "stop" | Cuts off the spoken reply |

**Nothing changes without your say-so.** Anything that writes — capturing a task,
planning your week — asks first and waits for "yes" or a click. Anything that only
reads — clearing your day, checking your week — runs straight away, because it changes
nothing.

**The numbers you hear are yours.** Voice does not calculate, rank, or estimate. It
calls the same handler the button beside it calls, and reads back what that handler
returned. If the answer is not grounded in your records, it says so instead of
guessing.

**If the microphone does not hear you.** Voice input needs a secure connection — use
`localhost` or `https`, not `http://` on a LAN address — and it needs permission for
this site (padlock in the address bar → Microphone). Chrome also streams your audio to
Google to transcribe it, so a proxy, VPN, or strict firewall will stop it working even
when the microphone itself is fine. If it cannot hear you, a typing box appears in the
panel so you are never stuck, and spoken output keeps working regardless.

Firefox has no speech input; it will offer the typing box instead.

---

## 17. Actions: what "do it" actually does

Buttons throughout the app are not decoration. They POST to `/action/{slug}` and run a
real handler, which is either:

**An executing action** — creates or changes a real record: complete a task, mark a
payment received, create drafts from atoms, convert an opportunity to a deal, plan the
next episode, accept a week plan, rebalance a week.

**A drafting action** — returns text for you to review and send yourself. Nothing is
sent, and nothing is saved:

![Draft follow-up](screenshots/47-attention-draft.png)

> ✓ **Follow-up drafted for Nova Labs.**
> *written by builtin*
>
> ```
> Subject: Following up — follow up: Nova Labs about Beta Access — the campaign deadline is 09 Nov
>
> Hi there,
>
> Shooting a quick note about follow up: Nova Labs about Beta Access — the campaign
> deadline is 09 Nov. Last time we spoke, the conversation was still open, and I
> wanted to check in rather than go quiet.
>
> Where things stand on my side:
> • I can turn this around within the agreed window
> • I've included a short outline so you can see exactly what you'd get
>
> If the timing isn't right, a quick 'not this month' is genuinely useful — I'll
> follow up when it makes sense.
>
> Would either of the next two weeks work for a quick call?
> ```
>
> **Nothing was sent or saved. Edit it, then send it yourself.**

You can see the full catalogue:

![Actions](screenshots/27-actions.png)

Every action handler is scoped to your signed-in account, so an action naming another
creator's record id fails rather than acting on it.

---

## 18. Settings

![Settings](screenshots/33-settings.png)

- **Your profile** — display name, phone, niche, bio, timezone, and **preferred
  currency**. Currency is per-account and applied to *every* amount in the product;
  switching USD → INR updates the whole app immediately, including Indian digit
  grouping.
- **Your workspace** — live counts of everything you own, and a button to load starter
  data.
- **Your working rhythm** — see §2.

---

## 19. Your first week, step by step

A realistic order of operations for someone opening this for the first time.

**Day 1 — set the ground truth**
1. **Settings → Your profile**: set your name, timezone, and currency. Everything you
   see afterwards is formatted correctly from this point.
2. **Settings → Your working rhythm**: tick your real working days and hours. Skip this
   and every capacity number will be wrong.

**Day 2 — record what already exists**
3. **Deals** — enter each live deal with its value, stage, deadline, and payment status.
4. **Brands** — one record per brand you work with, with a contact.
5. **Money** — log the payments you are waiting on, with due dates.
6. **Content** — add the pieces you have already published and the ones in flight.
7. **Rate card** — write down what your deliverables cost *you*.

**Day 3 — work the list**
8. Open **Today** and do the single "Do this first" item. Use its action button.
9. Work **Attention Center** top-down, highest severity first. Clear the high items —
   they are all either overdue money or deadlines that have already passed.
10. **Ideas** — convert your top five into content. The Attention Center will keep
    telling you about the rest until the pile is under control.

**Day 4 — plan ahead**
11. **Workflow / Plan → Propose my week**. Accept it, or dismiss it and clear the
    conflicts yourself.
12. **Attention Center → atomize** one published piece. Accept a handful of the
    generated atoms as drafts.

**Day 5 — review**
13. **Reviews / Weekly**. Read what slipped and what you decided. Act on the focus list.
14. **Copilot** — ask *"what should I do?"*, *"what am I forgetting?"*, and *"money
    waiting"*. Then ask something it genuinely cannot know, and confirm it refuses.
15. **Reviews / Business** — check brand concentration before it becomes a problem.

**Ongoing rhythm** — Today every morning, Attention Center whenever something feels
stuck, Weekly review every Friday, Business review monthly.

---

## 20. Screen reference

| Screen | Route | What it is for |
| --- | --- | --- |
| Login / Register | `/login`, `/register` | Getting in |
| **Today** | `/today` | The one thing to do first |
| **Attention Center** | `/attention` | Everything slipping, waiting, decaying |
| **Creator Copilot** | `/copilot` | Questions answered from your records |
| **Timeline** | `/timeline` | Chronological record of real activity |
| Workflow | `/workflow` | Open, overdue, and due tasks |
| Focus | `/workflow/focus` | One thing at a time |
| Plan my week | `/workflow/plan` | Propose → accept or dismiss |
| Content | `/content` | Every piece and its stage |
| Pipeline | `/content/pipeline` | Board view of the same |
| Pillars | `/content/pillars` | Recurring themes |
| Ideas | `/ideas` | Captured ideas, scored explainably |
| Deals | `/deals` | Campaigns, values, deadlines |
| Brands | `/brands` | Relationships, contacts, lifetime value |
| Offers | `/offers` | What you sell, and whether you've sold it |
| Series | `/series` | Recurring formats and episode progress |
| Money | `/money` | What came in, what is owed |
| Payments | `/money/payments` | Status and due dates per payment |
| Rate card | `/rate-card` | Your price points |
| Growth | `/growth` | Money on the table |
| Opportunities | `/growth/opportunities` | Routes you are tracking |
| Goals | `/goals` | Live progress from your records |
| Weekly review | `/reviews/weekly` | The CEO loop for one week |
| Monthly review | `/reviews/monthly` | The month in review |
| Business review | `/reviews/business` | Revenue, engine, portfolio, risk |
| Actions | `/actions` | The catalogue of runnable actions |
| Calendar | `/calendar` | Everything with a date |
| Library | `/library` | Assets and templates |
| Assistant | `/assistant` | Offline writing tool |
| Search | `/search` | Search and command palette |
| Quick capture | `/quick` | Capture without leaving |
| Voice | any page, via the microphone | Spoken commands and read-back answers |
| Settings | `/settings` | Profile, currency, working rhythm |

**Legacy URLs still work.** `/dashboard` → Today, `/tasks` → Workflow, `/revenue` →
Money, `/opportunities` → Growth. The old `POST` endpoints are kept as aliases too, so
existing bookmarks and saved forms keep functioning.

![Legacy dashboard](screenshots/34-dashboard-legacy.png)

---

### Two things worth knowing before you trust a number

**Provenance is shown, not implied.** Every figure carries a badge: `user-entered` for
what you typed, `system-derived` for what was computed from your rows, `ai-generated`
for text a configured provider drafted from your material only.

**AI is optional and never authoritative.** With no API key set, a deterministic
built-in writer handles every writing task offline. If a provider fails, the action
reports the failure and your data is unchanged. Deterministic logic owns every
calculation, deadline, ranking, and state change; AI only ever drafts.
