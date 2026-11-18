# ORBIT supervisor control

Requests are acknowledged and persisted before model discovery. The native bridge never waits for inference.

- `supervisor_runtime.py`: durable planning sessions and cumulative read evidence. Each claim performs one model planning slice. The next slice is queued; no wall-clock deadline discards the complete conversation. Repeated reads use saved evidence. An exhausted or ambiguous plan requires clarification rather than pretending to have executed.
- Explicit Shorts subjects or valid YouTube links are routed to the existing typed workflow, without an LLM discovery loop. Proper names, duration constraints and publication settings are preserved. Ambiguous requests still use the planner.
- `worker.py`: independent control (`command`, `control_apply`), execution and model-download lanes. Quick app mutations and job cancellation do not wait for rendering. `Studio.service_commands` does not recursively execute other jobs.
- `inference_gate.py`: an OS file lease serializes local model memory across processes, reentrant within a thread. Model contention is a queued state, never an availability error. Agent tool execution, image generation and local media inference hold the lease; nested calls reuse it. CPU video rendering does not own model memory.
- Model and network calls retain bounded internal limits. A pure planning timeout retains its session and waits with backoff. It does not replay application mutations or report a completed operation. Cancellation remains available.
- Approval consumption and creation of its execution job share a SQLite transaction. Action journals prevent replay of confirmed steps. Ambiguous interrupted mutations still require inspection. A resource lease is acquired before an image action opens its journal entry.
- `command_continue` resumes the original pure-planning job and its evidence with a selected model. It rejects requests that already contain actions. File/command review, project isolation, credential protections and publication checks are unchanged.

Deploy with an idle execution lane, back up the database and files, boot out the worker and wait for its PID to exit, atomically replace files, then bootstrap it once. Rebuild the native action allowlist when bridge actions change.
