# A seven-agent suite: five defend a market, two run ops, no central brain

*Portfolio case study for coopernorman.dev. Public-safe: an operational risk system run at soft-launch scale; figures are design targets, not billed actuals; no realized P&L; no secrets.*

---

## TL;DR
ShareShark (a real-money, dual-currency sweepstakes prediction platform) prices off a model that only sees fresh market data during trading hours, but users could place entries overnight and on weekends, when the model is effectively **blind**. If material news broke during a blind window, a sophisticated user could take the other side of a stale, mispriced price. To defend that, I built a suite of **seven cooperating Claude-powered agents**: five watch company news, the macro tape, and the order flow 24/7 to protect the market, while two handle ops and growth (social posts and contest scoring). They coordinate *without* a central controller, treat every model output as untrusted, and run in production with a full decision audit trail behind every price move. No single LLM call is the clever bit here; what matters is the **systems design around the LLM.**

---

## The problem: a blind model is an exploitable model
On a prediction platform a price encodes a probability, so it is only as good as the data behind it. The pricing model refreshes from live options/market data during market hours, but entries stay open overnight, on weekends, and on holidays, when the model can't see anything new. The moment material news breaks in a blind window, the posted line is stale, and the first person to notice can print money off it. The whole agent suite exists to shrink that exploitable window.

## The system: seven agents, three jobs
I used AI **only where it earns its place**: several agents are plain statistical engines with an LLM *review gate*, not LLM-first.

- **Risk-defense (the core):**
  - **News Guardian:** 24/7 two-tier news monitor that pauses an individual stock when company-specific material news breaks.
  - **Adjustment Agent:** scans futures + per-ticker news during stale periods and applies *overlay* odds-multipliers for the macro/sector risk News Guardian deliberately ignores (it never touches the model itself).
  - **Activity Guardian:** watches aggregate trading volume for one-sided surges that signal coordinated or informed money.
  - **Sharp Guardian:** a statistical user-profiling engine that tiers users by ROI/win-rate and correlates their entries with subsequent news pauses to surface possible insider activity.
  - **Handle Agent:** a market-maker-style price-shading engine that nudges prices against detected order-flow imbalances (with an LLM gate for larger moves).
- **Growth:** **Shark Feed** drafts brand-voice social posts from the news feed.
- **Automation:** **Daily Shark** is a transparent scoring formula that picks the featured daily contest.

## The signature design: cheap triage, smart analysis
Almost every LLM agent runs the same cost-optimized pipeline:
- **Tier 1, Haiku triage:** one cheap batched call screens many candidates and returns just flags/indices.
- **Tier 2, Sonnet analysis:** expensive deep reasoning runs *only* on the handful Haiku flagged, returning a structured JSON decision.

The subtle part is the **safety net.** When entries are closed (market open, no exploitation risk), most flagged articles are auto-ignored after the cheap pass, *unless* Haiku tags an article `extreme`, or its headline matches a curated `EXTREME_KEYWORDS` list (death, fraud, delisting, halt, M&A…). That keeps routine triage cheap (the expensive deep pass only fires on the handful of articles that actually matter) without ever creating a blind spot on the dangerous tail.

## No central brain: separation of concerns
The hard part of a multi-agent system is stopping agents from fighting. An overnight war headline could trigger *both* News Guardian (pause the stock) and the Adjustment Agent (macro overlay), double-counting the same risk. I solved it without a central coordinator: each agent has an explicit scope encoded as hard "this is **not** your job" rules (News Guardian = company-specific only; Adjustment = macro/sector), and downstream agents are fed upstream agents' *recent decisions per ticker* so they skip anything already handled. Clean division of labor, fewer redundant data calls, no conflicting actions.

## The insight: tell the model exactly what it can't see
Rather than reacting to "futures are +0.5% vs. prior close," the system reasons about **what the pricing model could last observe.** A *staleness-tier* model encodes the data-freshness regime as a function of time-of-day / weekend / holiday, feeds that to Claude as context, and scales rule-based overlays by an absorption factor. It persists a **baseline snapshot** between runs so an adjustment measures the move *since the model went blind*, not the cumulative move it already priced in. It also encodes that US futures don't trade Fri 5pm–Sun 6pm, so a weekend futures % move isn't new information, a detail that's easy to miss.

## Treating the LLM as an untrusted financial actuator
Claude's JSON recommendations move the prices users play against, so its output is validated like hostile input: layered JSON extraction (whole-string → code-fence → brace-matching), enum validation, range **clamping** (e.g. multipliers bounded to [0.50, 1.10]), an invariant that the two sides of a market can never both exceed 1.0 (which would let users profit risk-free either way), and safe defaults (`MANUAL_REVIEW`) on any parse failure. **The agent can be wrong; it can never produce an unsafe or unparseable action.**

## Shipping it safely
Every decision is persisted to a full audit trail (*including the IGNOREs*), so I could tune prompts and study false positives against real production behavior. Heartbeats plus a watchdog fire an emergency alert if an agent goes silent, and alerts are environment-tagged across staging and prod.

## What this demonstrates
- **Production applied-AI engineering, not a chatbot wrapper:** cost architecture, guardrails, orchestration, and observability around the model.
- **LLM-as-untrusted-component discipline:** the thing that actually matters when AI touches money.
- **Multi-agent coordination without a central brain.**
- **Domain modeling:** market-time mechanics, data-staleness reasoning, market-maker-style price-shading.

## Scale & shape (production)
**14,600 lines of Python across 77 files**; **7 agents**; **2 Claude models** (Haiku 4.5 triage, Sonnet 4.6 analysis) plus the hosted web-search tool. News Guardian runs every 5 minutes, 24/7; 61–71 tickers scanned per macro run; 11 futures/indices monitored.

## Tech stack
Python 3.12 · Django / DRF · Celery + Beat / Redis · Anthropic Claude SDK (Haiku + Sonnet, web-search tool) · Marketaux / StockNewsAPI · yfinance · exchange_calendars (NYSE) · Discord alerting · AWS EC2 (staging + prod).

## Honest notes
ShareShark ran a year of free-to-play and a small real-money soft launch (~50 users), with these agents operating in production at that scale, so this is real but small-scale operation, not "battle-tested at large scale." Any cost characterizations are rough design targets from the code, not billed actuals. There is **no realized P&L** here: these are risk-*protection* systems, and the platform's pricing margin and risk caps are design parameters, not earnings. Heavy lifting is shared by the Anthropic SDK + hosted web-search, the news/market-data vendors, Celery, and Django; the contribution is the orchestration, prompts, guardrails, risk modeling, and operational hardening. Some roadmap items (real-time price nudge at placement, graph-based collusion detection, formal VaR) are scoped, not shipped.
