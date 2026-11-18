# ORBIT local editing engine — creative v2

Internal operation is English; operator UI and replies are Hungarian.

## Real execution path

Research and source download → word-timed transcription and sampled visual evidence
→ event-scoped director and independent semantic review → content-aware framing
→ assembly-plan.json → orbit.edit.v1 frame contract → local FFmpeg montage
→ local Remotion word captions → original continuous mixed audio mux
→ full export decode and geometry/timing checks → existing publication queue.

`auto` is the default local renderer. The advanced production settings also offer
`ffmpeg` and `remotion` (with an ASS fallback). No cloud renderer is required.
Remotion 4.0.539, React 19.0.0 and their resolved dependencies are pinned by the
package and pnpm lock files. Build with `node build.cjs` inside `remotion/` after
installing dependencies; prepare the official headless browser at setup time.
Production renders do not download new LLMs or call a model API for graphics.

The model selects existing transcript/catalog IDs. It cannot supply shell commands,
React code, arbitrary filter expressions or unverified timestamps. The compiler
derives 30 fps output boundaries, source intervals and caption timing. Each export
has a `.timeline.json` sidecar describing the actual renderer contract. Exact source
paths remain project-scoped and are resolved by the native backend.

## Editorial behavior

One understandable event: hook, necessary context, development, real payoff and
resolution. Compare real openings by clarity and relevance. Interest in the first
three seconds is a creative target, not a guaranteed platform rule. Never fabricate
dialogue, chronology, sarcasm or facial reactions. Sentence boundaries, pauses and
visual events guide cuts. Preserve a pause when it is the joke. No mandatory change
every two seconds, constant zoom, forced loop, canned laughter or automatic black
fade at the ending. Keep gameplay and demonstrations understandable.

Captions use actual output word times, readable 72–80px content profiles and the
saved safe box. They never cover the bottom app controls by default. Font/color/
animation profiles are bounded. Invalid timing fails before rendering.

## Optional assets

`synthesize_speech` creates an English WAV using local Kokoro v1 through the existing
Sherpa-ONNX runtime. The model is stored under the configured SSD model root in
`audio/kokoro-multi-lang-v1_0`. It uses no cloud TTS. Source speech is not silently
replaced. Narration must be transcribed/aligned before planning a narrated video.
The tool is available on enabled agents; generated WAVs appear in Creations.

`search_stock_video` and `download_stock_video` use Pexels only when the operator
adds/enables a key in Connections. They retain source credit and accept only fixed
provider/CDN hosts. Analyze downloaded clips before choosing illustrative cutaways.
Stock and generated FLUX images are illustrations, not evidence of a news event.
Existing FLUX generation is retained; no paid image or rendering API is enabled.

## Recovery and evaluation

A failed Remotion graphics pass is replaced by timed ASS captions on the same
verified base video. The fallback is recorded in export metadata. Source gathering,
transcription and story planning are not restarted for a graphics error.
Cancellation kills the render process group; CPU concurrency is limited to two.
Frozen-image observations are not automatically labelled errors: a static original
scene can be valid. Decoder failures and invalid output dimensions/timing block
completion. Semantic approval and existing publication preferences remain required.

Existing analytics and experiments compare sufficiently observed videos with similar
topics, durations and ages. Missing metrics are not zeros; observational differences
are not causal proof. No virality, monetization or revenue guarantee is made.

## Creative v2 implementation

creative_direction.py compiles provenance-bearing finite effect events. Editorial
review can select a wipe at a real context boundary; it is an 8-frame overlay, not
a source overlap, and does not retime audio. Four caption themes use existing local
system fonts, measured in Chromium before render; gaming adds an active-word pill
and energetic adds a word underline. No new paid services or model downloads.

Zooms have a short attack/hold/release instead of whole-shot oscillation. A reaction
focus restores the same observed split composition, and screen/facecam evidence
supports a PIP layout. Local synthesized accents are sidechain-ducked under speech.
ASR word ordering/deduplication occurs before strict contract validation; output
timestamps use the renderer's cumulative frame budgets. Full-source understanding
and approved essential context/outcome remain upstream requirements.

Known limits: visual evidence is sampled, not continuous active-speaker inference.
Font choices currently use macOS system fonts, not a new downloadable font pack.
ASS fallback may omit decorative wipes/pill treatments. These are measurable editing
improvements, not guaranteed audience results or perfect semantic understanding.

## Own raw footage, humor and the social formula (2026-11-07)

- `raw_footage.py`: `start_shorts` with `files` (a chat-attached video, a named Mac path or project media) skips
  search and download. Outside files are copied into the Shorts project's `inputs/media`. The run uses
  `edit_goal=highlight`: the full-content survey looks for the single strongest self-contained bit (setup,
  punchline, reaction) instead of summarizing the whole recording. Project media cards have a
  "Short a legjobb pillanatból" button.
- `comedy.py`: measured humor cues per catalog unit (laughter words, a loud reaction within 2.5 s, a comic pause
  before the last words, a turn word, a surprise exclamation) and the hook/joke guide given to the director,
  the survey and the editor. Cues are timing evidence, not proof of humor.
- `comedy.social_polish`: after editorial approval, sound accents on real beats only: a bass hit (or a record
  scratch for a pure turn) on the punchline's last word, a riser into the payoff cut, a rewind after a cold-open
  hook, a whoosh on wipes, a pop on a laughing reaction. A preserved pause stays silent. `edit_formula:
  restrained` in the style turns it off. No footage is added, removed or reordered.
- `sfx.py`: nine FFmpeg-synthesized effects (pop, whoosh, boom, riser, ding, scratch, rewind, glitch, shutter),
  no downloads or licenses; mixed under speech with the existing sidechain duck.
