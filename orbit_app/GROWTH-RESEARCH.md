# Growth and editing research — 2026-10-21

There is no validated universally perfect short-form editing model. Compare candidates on actual source clips, word boundaries, visual context, coherent hooks, subtitle safe areas, runtime and memory, rather than marketing rankings alone.

## Chosen implementation

- Keep Qwen3.5 9B for memory-bounded local scene interpretation on the 32 GB Mac. Replace the fixed five-frame overview with PySceneDetect AdaptiveDetector shot boundaries and up to twelve chronological observations in batches of four. Include observed source scene boundaries in the actual editorial catalog. Existing Whisper large-v3-turbo MLX provides real word timestamps. Editorial review still grounds every selection in actual footage; base portrait crop and additional reaction zoom remain distinct.
- Existing automatic text-model routing produces evidence-based trend angle hypotheses and editorial plans. Actual model identity is logged. Vision routing allows supported smaller local vision models and excludes oversized simultaneous media models. No claim of a calibrated global winner is made.
- Google Trends Trending Now RSS supplies geographically scoped recent **Google Search** interest. It does not supply YouTube top-search volumes. Filter headlines against editable project niches, sample at most three queries through the authenticated YouTube Data API, filter actual durations <=180 s, and retain exact evidence, dates and sources. YouTube `videoDuration=short` alone means less than four minutes, not confirmed Shorts classification.
- Opportunity score: 50% log-scaled supplied Google interest, 30% recency, 20% scarcity in the bounded 10-result recent-video sample. It is a hypothesis, not a total-competition estimate. Missing supply data produces no score. AI angles must be checked against downloaded footage before execution.
- A separately configurable automation can choose a fresh, unused evidenced trend. It uses existing daily targets, run schedules, output mode and approval controls. Watcher refreshes alone never publish. Old trend data (>24 h), unsupported source topics and recently used topics do not create another production.
- Measured feedback: video counts, engaged views, likes, comments, shares, subscribers, average view duration, average viewed percentage; last-28-day daily series, countries and traffic sources, plus retention for two leading videos where the API supplies it. Missing metrics are unknown, not zero. Existing feedback compares comparable videos only and changes one editorial hypothesis at a time.

## Alternatives considered

- Qwen3-VL 8B: supported optional local alternative, not installed redundantly; Qwen3.5 9B already exists. Larger 27B models compete with frame/ASR buffers and macOS memory; do not load them by default in this media lane.
- Gemini native audio/video understanding: useful optional cloud upgrade for dense video context, but not silently enabled for whole-video upload. Existing configured text/vision cloud adapters remain available under user sharing preferences.
- WhisperX: forced alignment and diarization can improve dedicated speech workflows. Existing MLX Whisper word timestamps are retained to avoid replacing the working Apple Silicon stack without comparative evidence.
- SAM 2: interactive object/video segmentation, not an automatic joke detector or editor. Existing conservative privacy masks are retained; no guessed face cutouts or decorative masking.

## Primary sources

- https://ollama.com/library/qwen3.5 — model family, sizes, modalities.
- https://github.com/QwenLM/Qwen3-VL — multimodal/video alternative.
- https://www.scenedetect.com/docs/latest/api/detectors.html — adaptive scene detection.
- https://github.com/m-bain/whisperX — alignment/diarization alternative.
- https://github.com/facebookresearch/sam2 — video segmentation.
- https://ai.google.dev/gemini-api/docs/video-understanding — native video/audio analysis.
- https://support.google.com/trends/answer/3076011?hl=en — Trending Now data and RSS export.
- https://developers.google.com/youtube/data/reference/rest/v3/search/list — recent search and duration semantics.
- https://developers.google.com/youtube/analytics/channel_reports — supported report dimensions.

## Verification

- 283 tests completed successfully (4 optional Google SDK test classes skipped in the system Python); 6 adapter tests separately passed in the installed media Python.
- Real local scene/vision run: 96-second 1080×1920 video, 27 detected shots, 12 validated observations, no partial batches, Qwen3.5 9B, 64.8 seconds.
- Authenticated YouTube Analytics scope granted and API enabled in the existing ORBIT YouTube Studio Cloud project. Reports returned successfully, but detailed channel rows were still empty at verification. Public counters: two accessible uploaded videos, 788 views and 7 likes. Missing detailed rows remain unknown.
- Real trend run retrieved two scoped topics, collected recent-video samples, assigned traceable proxy scores and generated hypothesis-only editorial advice. No trend video was publicly uploaded during verification.
