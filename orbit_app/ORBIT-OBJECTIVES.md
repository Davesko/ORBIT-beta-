# ORBIT — durable objective supervision

ORBIT is the global assistant, not a single project's producer agent. It can inspect every project, delegate work, create/update agents and rooms, and manage schedules through the existing validated application actions. New durable objectives connect those projects through explicit dependencies and saved evidence.

## Execution contract

`missions.py` owns objective definitions, immutable per-cycle plans, per-step receipts/results, bounded retry state and events in SQLite. `worker.py` has a separate admission lane for objectives. The scheduler does no model inference or remote I/O. The existing production engine remains responsible for actual video creation and its stage-level recovery.

Supported nodes:

| Kind | Actual behavior |
| --- | --- |
| `trends` | Queue the existing Google Trends/news/video-source research, preserving the project's topics. |
| `shorts` | Admit the existing verified production workflow once, using an origin receipt. `query_from` selects real, fresh, unused sources from a same-project trend predecessor and passes the verified source bundle directly. Explicit `query` can use a supplied subject/link. |
| `publication_wait` | Wait for the exact rendered run's public, successfully processed YouTube receipt. A private upload, unprocessed upload or unrelated channel video does not qualify. |
| `wait` | Store a dependency-relative due time; no sleeping model or busy loop. |
| `metrics` | Queue actual YouTube measurements; require a recent collection timestamp before proceeding. |
| `evaluate` | Read measured performance and its evidence-based experiment recommendation. Missing accounting data remains unknown. |
| `agent` | Delegate a read-only analytical deliverable with an immutable role/model/tool snapshot and explicit text/JSON output contract. Parent results are labelled data. |
| `control` | Use the existing action journal for project-scoped agent, room, link, renderer-setting and project edits. Agent changes keep before/after revisions. Shell execution and publication-policy changes are excluded. |
| `capital_review` | Cross-project decision-support handoff with the source measurements, unknown cash when unverified, and explicit no-transfer/no-trade flags. |

The complete Shorts team is checked for active role bindings, nonempty role instructions and required tools before admission; prompt hashes and actual model settings are recorded. ORBIT can inspect full prompts through the existing agent read and change them through typed actions. This is not proof that a natural-language prompt is semantically perfect. Critical editorial, source, render and publication checks remain server-side.

## Recovery and limits

- Dispatch completion means admission, not completed agent work. Actual child jobs, saved outputs and video-file/verification receipts determine success.
- Origin keys and atomic queue/receipt writes prevent duplicate admission after a restart. Source reservations are reused rather than silently selecting another already-used video.
- Read-only analytical agents may retry transient failures with backoff, at most three attempts. Existing Shorts recovery handles its stages. There is no blind replay of failed publication or ambiguous app mutations.
- Completed parents remain complete. Invalid JSON, missing sources, missing outputs, unavailable credentials and uncertain outcomes remain explicit; they do not become fabricated success.
- Per-cycle deadlines, daily cycle limits, total cycle limits and one active cycle per objective bound resource use. Waking a Mac does not replay every missed interval.
- Pause stops new admission and preserves the active cycle. Cancellation also stops tracked unfinished jobs. Resuming a paused cycle keeps receipts and extends its active-time deadline. A failed/uncertain objective requires a corrected plan or inspection; it is not silently restarted forever.
- The scheduler isolates schedules, growth, objectives and context refresh. Per-service failures are recorded in `scheduler-health.json`; the heartbeat means the process is alive, not that every integration works.

## Main assistant integration

The existing main chat supports `mission_save`, plus typed `mission_start`, `mission_pause` and `mission_resume` operations. Repair continuation preserves the same cycle and its successful parents. Read `app: missions` for plans, steps, events and receipts; read `app: economics` for measured performance and the accounting-data limits. Routine supported app actions retain the user's standing authorization. Saving an example/design request does not authorize running it. Publication remains subject to the existing project policy.

All internal task prompts and contracts are English; operator labels and replies are Hungarian. Local-only model policy and manual model selections are preserved. The planner receives a fresh, compact directory of **all** projects/agents, live jobs, actual measurements, objective state and supported operation names for every planning slice. Full details stay available through typed reads. The planning context budget was increased to 16K to accommodate compound objectives without replacing precise IDs with vague summaries.

Useful operator messages:

- `Célok állapota` — deterministic DB-backed status without model-generated numbers.
- `Mutasd meg az ORBIT-célok részletes tervét és az elakadás okát.`
- `Indítsd el a YouTube → mérés → tőkeáttekintés célt.`
- `Szüneteltesd ezt a célt; a már futó munkát hagyd befejeződni.`

## Revenue and financial boundary

Views and estimated YouTube revenue do not establish settled, spendable cash. This change does not add bank access, broker credentials, payouts, stock orders, copy trading or autonomous real-money decisions. `capital_review` is a truthful preparation/decision-support connector; it is **not** a paper-trading execution engine. Real trading/transfer decisions require human review and a separate integration. Profitability is `unknown` until actual revenue and costs can be reconciled; no return is promised.

The existing editing experiment mechanism already compares sufficiently supported, comparable measured videos and assigns one hypothesis at a time to future productions. The objective engine feeds actual measurement results into that loop; it does not invent viewers, causal success or financial returns.

## Validation and deployment

436 regression tests passed. Tests cover dependencies, cross-project routing, pause/cancel, immutable inputs, restart receipts, output validation, bounded retry, controls, publication-policy preservation, missing cash and scheduler failure isolation. A genuine local Qwen 3.5 9B main-chat test created a two-project objective as a draft through the real planner and action queue in an isolated database (46.99 seconds, no cloud or production start). The two-project objective was subsequently executed to completion in that isolated database. A genuine read-only local agent also completed its JSON task; this is a functional check, not a claim of universal model reasoning accuracy.

Before deployment, back up installed core and consistent SQLite state. Install only changed backend modules with the worker idle, then restart it once. Existing projects, prompts, agents, model settings, media and schedule-enabled flags must remain unchanged. A supplied workflow template remains a draft until explicitly started. The Mac and model service must remain available; source services, quotas and semantic model accuracy still have real operational limits.

Architectural references reviewed: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) distinguishes per-run checkpoints from shared memory; this implementation retains ORBIT's existing SQLite runtime instead of adding a competing orchestrator. [YouTube metric definitions](https://developers.google.com/youtube/analytics/metrics#estimatedRevenue) distinguish estimated revenue from other measurements; a metric is not a payout receipt.

Deployment: the installed runtime and a draft “YouTube → mérés → tőkeáttekintés” template are available. The template waits for real publication before its 24-hour audience window, then requests measurements for the exact uploaded video IDs. It preserves the existing project publishing mode and local model policy. No production or trading was started by installation.

Final reliability check (2026-10-28): draft objectives expose their full planned step count; repeated pause requests preserve the original pause time; large event previews remain valid labelled JSON rather than truncated JSON objects.

Verified input admission: analytical agents with project_files capability receive a backend-read inventory and a stored input_evidence receipt before inference. The prompt labels a bounded inventory preview and its limits. Model-written conclusions remain separately labelled model_analysis; they do not masquerade as tool results. This also works when a local model does not issue a tool call itself.
