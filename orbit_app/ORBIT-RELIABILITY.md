# ORBIT reliability and context upgrade

The supervisor plans requests; typed application operations own the actual changes. A successful chat turn is not a successful media production. Actual jobs, saved stage outputs and upload receipts remain authoritative.

## Implemented

- Stable `project_agent_roles` bindings connect stage keys to exact agent IDs. Names, custom titles and avatars are presentation. Renaming an agent does not change its execution role. Archived bound agents are missing roles, not silent invitations to create replacements.
- `app_capabilities.py` supplies current project capabilities, role bindings, active jobs, recent failures and timestamps. The same facts reach the supervisor's fresh context and the operator's **Állapot** panel. No credentials enter this catalogue.
- `project_role_save` explicitly rebinds a missing role to an active agent in the same project. Duplicate production-role assignments and cross-project bindings are rejected.
- Common read-only status questions use actual application state without model-generated facts or mutation. The current status request excludes itself from its own work report.
- Existing durable supervisor checkpoints and action journal remain in use. Routine in-app changes and production starts execute under the operator's standing authorization. Side effects already completed are not replayed to fix a later stage.
- A rejected editorial plan citing missing visual observations can request one bounded, checkpointed pass over the actual proposed shots. Only returned, timestamp-matching observations enter the evidence. The editorial quality gate is not bypassed.
- Body/chat text uses local IBM Plex Mono; pixel headings use Pixelify Sans. Both fonts include Hungarian accents and are packaged with their open-font licenses.

## Design sources reviewed

- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence — durable thread state versus cross-thread knowledge; persistence through interruption.
- Agents SDK context: https://openai.github.io/openai-agents-js/guides/context/ — application context and capabilities are managed explicitly rather than assumed to be model knowledge.
- Conductor durable human tasks: https://docs.conductor-oss.org/devguide/ai/human-in-the-loop.html — selective, state-preserving review rather than restarting a workflow.

These sources informed the design; no unverified performance advantage or universal correctness is claimed. ORBIT keeps its existing local SQLite/job architecture and provider independence instead of introducing a second competing workflow runtime.

## Validation boundaries

Tests cover agent renaming, changed display roles, archival and explicit replacement, scoped role validation, truthful status reads without model calls, missing-shot evidence sampling, disclosure persistence, typography loading and responsive UI. External source availability and semantic editing quality still depend on the actual input and provider outputs. Earlier failures remain in history with their real cause.

## 2026-10-26 reliability pass

Observed causes: 95 scheduled producer-dialogue timeouts; a local-only configuration while both model inventories were empty; AppleDouble sidecars in the external SSD manifest directory causing Ollama's manifest scan to fail. All five SSD models reappeared after quarantining the 12 verified sidecars and restarting the model service. Actual Qwen 9B and automatic Groq calls succeeded. Existing provider credentials and context-sharing authorization were reused; no new service or subscription was created.

Changes:
- Producer video requests are admitted to the typed production chain; descriptive questions and other agents stay conversations. Stable role IDs survive renaming.
- Origin receipts are stored atomically with production jobs. Retries after a crash, queued-request replay and simultaneous submissions reuse the same production. Research source reservations also persist their origin.
- Automation failures back off from the actual job finish time. Model planning allows three delayed retries, then preserves the request for explicit continuation instead of spinning indefinitely. Manual cancellation does not count as repeated failure.
- Cloud attempts leave time for local fallback; a slow local model cannot consume the entire multi-model budget. Manual model selections remain explicit.
- Research normalizes literal escaped whitespace, rechecks cached article dates and saves its selected evidence before handing it to production. Topic and freshness requirements remain enforced.
- Long videos provide bounded, adjacent sentence windows across start/middle/end. Temporal validation and independent semantic review remain required; failed reviews can repair rather than publish an arbitrary cut.
- Automation maps receive actual dependency edges and the complete planned production team. Repeated-failure waiting is visible.
- The SSD service quarantines only proven AppleDouble sidecars on startup. Actual model manifests/blobs are untouched; sidecars remain recoverable under ORBIT backups.

The current implementation uses SQLite transactions, stored stage state and independent control/production lanes. LangGraph's documented distinction between durable per-run state and shared memory remains the architectural reference: https://docs.langchain.com/oss/python/langgraph/persistence . A second orchestrator was not introduced alongside the existing one.

Operational limits: an unavailable source, revoked credentials, exhausted external quota or insufficient story evidence can still prevent a video. A truthful, saved failure is preferable to an ungrounded publish. Disabled schedules stay disabled. Recommended next improvements are a curated set of source channels, measured editor evaluations on accepted/rejected clips, and a user-visible provider budget dashboard before expanding production volume.

## 2026-10-27 local execution preference

- `local` remains the default and is the selected live policy. Automatic model requests do not call cloud language models in this mode. Web search is an independent, explicitly enabled capability.
- Optional `local_first` tries local models first and only then configured cloud providers; `hybrid` preserves cloud-first behavior. Manual choices remain explicit. The settings screen labels all three policies and resets the main-chat selector to automatic on policy change.
- The local model lease serializes inference across agents, keeping a busy model's request in the durable queue instead of treating contention as permission to offload to the cloud.
- Source selection measures black intervals with FFmpeg before proposing a hook. Mostly blank units are excluded and a partly blank unit cannot be the opening shot. Actual reviewer evidence replaces generic repair notes.
- 359 regression tests passed, including local-only isolation, local-first fallback ordering, private-context filtering, manual-choice preservation and busy-model queuing.
- A real saved-footage production completed selection, layout, rendering, metadata and verification without publication. The revised output decoded fully at 1080×1920, 30 fps with stereo audio; no ≥1-second freeze or silence and no ≥0.35-second black interval were detected. These checks measure technical integrity, not viral performance or universal editing quality.

Local-only integration check: automatic selection, editorial layout, render, metadata and verification completed with cloud providers absent from the isolated test configuration. The test reused previously downloaded/transcribed footage; it was a technical pipeline check, not a new trend-research evaluation. Output: 31.53 seconds, 1080×1920 CFR 30, six shots, 117 timed caption words, stereo 48 kHz audio. Full decode succeeded with no detected ≥0.35-second black interval, ≥1-second freeze or ≥1-second silence at the configured thresholds. Nothing was published. All 34 live agent model selectors now use `auto`, replacing obsolete unavailable-model and explicit cloud pins, under the live `local` policy.

## Transcript-led narrative editing

The proposal editor, semantic reviewer and timing-repair reviewer now share one narrative contract: an evidenced opening hook at output zero, necessary context, coherent development, a real payoff and a completed ending. Speech context and visual evidence have different authority; the prompt forbids fabricated exchanges, invented identity or constant face zoom. Both Shorts projects received backed-up role-specific instructions for transcription, selection, layout, render and verification.

The catalogue samples complete sentence clusters across sources rather than cutting its bounded context in the middle of a clause. Short negations are retained. Immediate transcript continuations can be restored using existing catalogue IDs; absent continuations are never invented. Repaired intervals are presented for semantic review. Candidate search skips structurally incomplete alternatives instead of exhausting all candidate slots before reaching valid sources. A saved `storyboard.json` maps narrative phases to exact source and output times.

Captions use 72–80 px profiles with font-aware short word groups inside the existing social safe box. This changes future renders; it does not modify already exported files. The runtime remains local by default. Regression suite: 370 passing tests. Editorial meaning remains a model judgment, with grounded timing and media integrity checked separately.

Additional safeguards retain tiny final words using available silence for the render minimum, prevent unrelated cross-source short answers from fabricating dialogue, and store transcript quotations in the displayed outline separately from model commentary. Fallback compilations stay within one source; multiple source clips remain available for grounded editorial selection.

## ORBIT 2.5 — reviewable, local editing workbench

- Operator video feedback and free-form project editing preferences are stored in SQLite and supplied to future editing requests. Positive/negative labels remain operator judgments, separate from YouTube measurements.
- The Publishing page exposes a seekable storyboard with actual video thumbnails, selected transcript excerpts and phase labels. Full-story, hook-only, framing-only and caption-only revisions create new durable runs from saved sources. Original artifacts remain intact; revisions never publish automatically.
- A cached, evidence-bound director brief identifies an actual event, the viewer's question and its supported resolution before edit selection. Repair candidates preserve those anchors. Distant source episodes and promotional teasers cannot masquerade as one coherent story. Rejected events can trigger a bounded re-plan instead of repeating the same invalid narrative.
- Natural punctuation, voice changes, pauses and scene boundaries inform a finer render timeline. Original narration is retained for independently evidenced visual cutaways. Actual frame regions supported by two observations can use a portrait stack for gameplay/facecam or comparison subjects. Unsupported regions retain the normal portrait layout.
- Local Sherpa-ONNX 2.0.1 segmentation and embedding models were installed onto the SSD. Anonymous within-source voice labels and uncertainty/pause observations supplement existing MLX Whisper timestamps. These labels do not establish identity or map a voice to a visible face.
- Local model evaluations compare 18 fixed logic/control/code cases and record accuracy and latency. A separate editorial corpus grows from actual operator-labeled clips (up to 20; minimum 6 to compare); no synthetic audience or human quality ratings are fabricated. Routing can use measured purpose-specific results.
- Automation controls show worker/SSD/model-policy health, actual waiting reasons and safe continuation for saved planning steps. Benchmark jobs persist per-case results and resume after worker restart.
- One editorial experiment is assigned per project at a time, only after sufficiently supported channel feedback exists. Control/test assignments preserve the baseline settings and record actual edit traits with YouTube metrics. Small samples remain collecting; observed differences are not treated as causal proof.
- The main assistant receives the new editing/model-evaluation read contracts and can use the same typed revision/preference operations as the UI.

Validation includes the Python regression suite, native admission checks, 1440px and 900px frontend runs against an isolated real database, actual split-layout FFmpeg rendering, a cutaway test verifying that the original 440 Hz narration survives a visual source with 880 Hz audio, and real local speaker segmentation on a saved source. Local test videos were not uploaded. Existing exported videos are not silently rewritten.

Latest workbench validation: 400 Python tests pass. The frontend integration also waits for every storyboard thumbnail to decode before checking navigation and feedback. Pacing re-times sound accents to the final split fragment rather than inheriting an out-of-range delay from the unsplit sentence.

Semantic event hints now reuse the installed Qwen embedding model locally. A low text similarity alone cannot split a story: novel content also needs a source cut or a measured pause. On the genuine test transcript this separates the wasp scene from the subsequent voting episode. The numerical diagnostic vectors stay out of the chat context; the director receives compact event boundaries. These hints are not semantic ground truth. The full regression suite currently passes 400 tests.

Final narrative pass: independent sentences remain separately selectable instead of being packed into long blocks. Body beats follow source chronology after an optional teaser hook. Promotional channel teasers are rejected anywhere in the selected story. Local event ranking, director anchors and independent review use evidence-ID JSON grammars. The reviewer sees event-local timestamped frames, not unrelated whole-source scene summaries. One bounded same-event repair offers minimum complete windows before abandoning the event. The actual installed Qwen 3.5 9B completed 17 of 18 general task checks; this is not an aesthetic editing score.

Release check: automatic local selection on the saved mixed compilation produced a single 13.542-second wasp incident with hook, context, payoff and ending (4 render shots), excluding the subsequent voting episode. The final 1080x1920 export decoded completely (406 frames); FFmpeg found no frozen interval of at least 1.5 seconds and no silence interval of at least 1 second at the diagnostic thresholds. This is one verified case, not proof of universal semantic editing quality. ORBIT 2.5.0 was installed with backups; both Shorts teams received contract v5. All 34 agents remain on automatic model selection with local-only execution. The 1,960 existing artifacts and disabled schedule states were retained.
