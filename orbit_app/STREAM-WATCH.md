# Élő adás figyelő (Stream Watch) — implementation guide

Audience: another AI assistant that must understand, operate, extend or rebuild this subsystem of ORBIT.
Language rule of the app: internal contracts and code comments are English, everything the owner sees is Hungarian.

## 1. What it does

It watches the live broadcasts of the biggest streamers while they play **Grand Theft Auto VI** (launch 2026-11-19), finds the
moments their **chat exploded at** (no picture analysis, no model), cuts those moments out of the broadcast's own recording,
and hands each clip to the Clip Farm's Short pipeline, which makes a 1080x1920 Short (facecam on top, game below, word-highlight
captions). **Nothing is uploaded by itself**: finished Shorts wait for the owner in the Publikálás page (see §9).

Idea source: VodMine. Disk stays free because nothing is recorded continuously: only the chat counts are stored, and the clip is
downloaded from the platform's recording of the running broadcast (yt-dlp download ranges).

## 2. Files

| File | Role |
|---|---|
| `orbit_app/stream_watch.py` | Backend module: config, detection (pure), moment table, status machine, Short hand-off, title rule, UI snapshot, `dispatch` ops. |
| `orbit_app/stream_watch_runtime.py` | Three small processes: `listen` (chat), `probe` (who is live), `fetch` (download a window). Standard library for `listen`; media-runtime Python for `probe`/`fetch` (needs yt-dlp + imageio_ffmpeg). |
| `orbit_app/web/stream_watch_ui.js` | The "Élő adás figyelő" project app (channels, settings, moments list, chat chart). |
| `orbit_app/test_stream_watch.py` | Unit tests (detection, window, title rule, defaults). |
| hooks in other files | `scheduler_services.py` calls `stream_watch.tick` every cycle; `assist_jobs.py` routes `task=watch_fetch` jobs to `run_job`; `autonomous.py` uses `stream_watch.campaign(data)` (render step) and `stream_watch.streamer_title` (metadata step); `autonomy.py` lists the watcher on the Önműködés page and honours the master pause; `raw_footage.py` accepts the clip as owner footage; `project_apps.py` maps project kind `streamwatch` to app `watch`. |

Project kind `streamwatch` (created once by `ensure`; a deleted one is not recreated, see `project_trash`). Per-project folders:
`<Orbit>/stream-watch/<pid>/` (runtime state) and `<Orbit>/projects/<pid>/workspace/watch.json` (config), clips in
`projects/<pid>/sources/moments/`.

## 3. Processes and data flow

```
scheduler tick (every cycle, rate-limited to 10 s per project)
 ├─ probe (media python, spawned if live.json older than 150 s, at most every 120 s)  -> stream-watch/<pid>/live.json
 ├─ listen.json (updated every tick: channels to listen to + YouTube video ids)        -> stream-watch/<pid>/listen.json
 ├─ listener (system python, spawned if heartbeat older than 45 s)                      -> chat.sqlite (5 s buckets)
 ├─ detect() on each active channel's last 15 minutes of buckets                        -> stream_moments rows (status 'found')
 ├─ advance(): best 'found' moment whose recording has caught up -> job watch_fetch     -> status 'fetching'
 │     run_job(): `fetch` subprocess downloads the window -> sources/moments/*.mp4 (+ .source.json) -> status 'ready'
 └─ produce() (if auto_produce) -> Clip Farm short run (origin 'watch:<moment id>')      -> status 'producing'
```
The listener ends by itself when `listen.json` is not refreshed for 600 s (app stopped / watcher disabled). A newer listener takes
over by writing its pid into `listener.pid`.

### 3.1 probe (`stream_watch_runtime.py probe`)
Input (stdin JSON): `{channels: [...], out: <live.json path>}`; at most 60 channels. Output file: `{checked, channels:[{channel, live, started, title, vod, vod_duration, vod_started, game, ...}]}`.
- **Twitch** channel `name`: yt-dlp `extract_info('https://www.twitch.tv/<name>')` → `is_live`, `timestamp` (start), title. Then the newest archive
  (`/videos?filter=archives&sort=time`, 1 entry) is the broadcast's own recording if its `timestamp` is within 120 s of the start or it is live.
  `vod` = numeric video id, `game` = the last chapter title of the recording.
- **YouTube** channel `yt:<handle>`: yt-dlp on `https://www.youtube.com/@<handle>/live`; "not currently live" / "will begin" / premiere = not live.
  `vod` = the 11-character video id of the live itself (it is its own recording), `started` = `release_timestamp` or `timestamp`.
  YouTube has **no game category**: `game` is set to `Grand Theft Auto VI` only if the title/description matches `GAME` (`grand theft auto 6|vi`, `gta 6|vi`).
- Do **not** use Twitch's private web GQL client id (the auto-mode classifier refuses it); yt-dlp probing or the owner's own Helix key are the allowed routes.

### 3.2 listen (chat counting)
- **Twitch**: anonymous IRC over TLS `irc.chat.twitch.tv:6697`, `CAP REQ :twitch.tv/tags`, `NICK justinfan<N>`, JOIN up to 15 channels per 20 s check, PONG on PING.
  Message time = `tmi-sent-ts` tag.
- **YouTube**: a daemon thread (`youtube_chats`) follows `listen.json["videos"]` (channel -> video id). Per video `yt_poll`: GET
  `https://www.youtube.com/live_chat?is_popout=1&v=<id>`, extract `INNERTUBE_API_KEY` and the first continuation from `ytInitialData`, then POST
  `youtubei/v1/live_chat/get_live_chat?key=...` with `{context:{client:{clientName:'WEB',...}}, continuation}` every `timeoutMs` (1–5 s). Items:
  `liveChatTextMessageRenderer` / `liveChatPaidMessageRenderer`; text from `message.runs` (emoji id or shortcut). **This path was written
  but never run against a real live chat** (an attempt was denied by the auto-mode classifier). Treat it as untested.
- Both feed one `Counter`: 5-second buckets per channel (`BUCKET = 5`). A user counts at most **2 messages per bucket** (anti-spam). Stored per bucket:
  `n` (counted messages), `users` (distinct people), and counts of reactions matched by regexes: `funny` (lul/lol/kekw/😂…), `hype` (pog/w/letsgo/🔥…),
  `shock` (wtf/omg/bro/😱…), `fail` (f/rip/oof…), `clip` (someone writes "clip it"). **No usernames or texts are stored.** Buckets are written every 5 s
  after they can no longer change (+3 s), rows older than 6 h are deleted. Table: `buckets(channel,t,n,users,funny,hype,shock,fail,clip, PRIMARY KEY(channel,t))`.

### 3.3 fetch (`stream_watch_runtime.py fetch`)
Input: `{vod, start, duration, out, platform}`; `platform='youtube'` switches id validation (`[\w-]{11}`), URL (`watch?v=`), format
(`bv*[height<=720]+ba/b[height<=720]/b`, `live_from_start`, mp4 merge). Twitch: `best[height<=720]/best`. Both use `download_ranges`.
Rules: 5–180 s per clip; refuses below 3 GB free disk; if the recording is shorter than `start+duration-2` (not a live YouTube) it answers
"A felvétel még nem ér el eddig a pillanatig." and `run_job` puts the moment back to `found` (retry later) while it is < 1 h old. Job timeout 600 s
(`A letöltés időkerete lejárt.` → status `failed`; the owner/assistant may reset a failed strong moment to `found` to retry).

## 4. Detection algorithm (`detect`, pure function, unit tested)

Input: one channel's buckets. Steps:
1. Build a gapless 5 s timeline; `rate[i]` = messages in the last 15 s (3 buckets).
2. Baseline per point: the previous **10 minutes ending 20 s earlier** (`rate[i-124 : i-4]`); needs ≥ 36 samples (3 min) else the point is not judged.
   `m` = median, `mad` = median absolute deviation × 1.4826, spread = `max(mad, max(1.5, 0.25·m))`; `z = (rate − m)/spread`.
3. A peak starts at a point with `z ≥ sensitivity` **and** `rate ≥ max(6, 1.6·m)`. The moment's start extends back while `z ≥ 1.5`; its end extends forward while `z ≥ 1.5`; `top` = highest z.
4. A peak still rising at the end of the data (and < 20 s old) is skipped this round (decided later, so its end is real).
5. Needs `people ≥ 4` (max distinct users in the span). `kind` = the dominant reaction if it is ≥ max(3, 12 % of messages) else `peak`.
6. `score = z_top · log10(10 + people) · (1 + min(0.5, dominant/total)) + min(3, clip_calls·0.5)`.
7. Output moments: `at` (start − 2 buckets), `end`, `score`, `kind`, `z`, `rate`, `normal`, `people`, `clip_calls`, `reactions`.

`window()` converts a moment to a recording offset: `begin = at − LEAD(8 s) − before − started`, `finish = end − LEAD + after − started`,
length clamped to **20–90 s**. `started` is the recording's start (`vod_started`).

## 5. Recording a moment (`record`)
- Skip if `score < min_score` (**quality gate**).
- Skip duplicates: same channel within 90 s of an existing moment's `at`.
- Per channel per hour at most `per_hour` moments; when full, a stronger one replaces the weakest still `found` one.
- Insert into `stream_moments(id, project, channel, vod, at, start, duration, score, kind, detail(json), status, file, job, production, error, created, game)`.

Status machine: `found → fetching → ready → producing` (and `failed`, `dismissed`). `advance` picks, best score first, `found` moments whose recording
has surely caught up (`now − at ≥ after + 150 s` while the broadcast still runs), one fetch at a time, only within 6 h. `prune` removes unused raw clips
after `keep_days`. `dismiss` deletes the unused file.

## 6. Configuration (`workspace/watch.json`, validated by `clean`)

| Key | Meaning | Default (code) | Value set for launch day |
|---|---|---|---|
| `enabled` | master switch (also off while the Önműködés master pause is on) | false | true |
| `channels` | Twitch names and `yt:<handle>` (YouTube); max 60; youtube.com/@x links are normalised | ~38 names | 38 |
| `game` | only watch a channel while it plays this ("" = any, rehearsal) | `Grand Theft Auto VI` | same |
| `not_before` | launch day; gate opens at the first midnight on Earth (UTC+13) = 2026-11-18 11:00 UTC. Before it nothing in the game's category is touched (could only be leaked footage) | 2026-11-19 | same |
| `sensitivity` | z threshold (1.5–10) | 2.0 | 2.0 |
| `min_score` | moments below this are not kept (0–40) | 15 | 15 |
| `per_hour` | per channel per hour (1–30) | 2 | 2 |
| `before` / `after` | seconds kept before the chat rose / after it calmed | 7 / 20 | same |
| `auto_fetch` | download clips by itself | true | true |
| `auto_produce` | start a Short by itself | true | true |
| `auto_post` | upload verified Shorts without approval | **false** | false |
| `keep_days` | unused raw clips live this long | 7 | 2 |

Channel list (Twitch): kaicenat, caseoh_, jynxzi, xqc, stableronaldo, jasontheween, plaqueboymax, zackrawrr, lirik, hasanabi, agent00, shroud, tarik,
ishowspeed, illojuan, rubius, ibai, auronplay, ludwig, valkyrae, sodapoppin, asmongold, tfue, nickmercs, timthetatman, esfandtv, mizkif, ohnepixel, summit1g.
YouTube: yt:ishowspeed, yt:kaicenat, yt:markiplier, yt:ludwig, yt:pewdiepie, yt:rubius, yt:valkyrae, yt:dream, yt:sidemen (`@illojuan` does not exist on YouTube).
Rationale: IlloJuan (233k) and Rubius (191k) led the August 2026 gameplay reveal co-streams; the others are the biggest English-speaking GTA streamers.

## 7. Making the Short (`produce`)
`produce(mid)` copies the clip into the Clip Farm project as owner footage (`raw_footage.resolve_files`, plus the `.source.json` sidecar) and calls
`execution_queue.submit_short(s, CLIP_FARM, brief, format, origin='watch:<mid>', local_files=...)`. Format = `gta6.FORMAT` with `min_seconds=12`
(1 source, montage, `portrait_framing='context'`, visual analysis + subject tracking, highlight `#FF5FA2`). `.source.json` carries
`origin='stream_watch', platform, channel, url, title, game, moment`. `campaign(data)` returns `{kind:'gta6_stream', platform}` for such clips, which makes the pipeline
use `gta6.stream_cut` (whole clip, no story model/director) and the **facecam-on-top, game-below** layout (the facecam is found from local face boxes in `gta6.py`, stack mode with `top_fraction .3`).
**Pitfall:** `submit_short` with `requirements` but without `source_handoff` *saves* those settings as the Clip Farm project's style. If `auto_post=true`,
`produce` adds `publish_to_youtube=True, review_before_upload=False` and thereby permanently switches the whole project to auto-upload and bakes it into every started run
(`short_runs.data.style`). Keep `auto_post` false; if it was ever on, reset `short_styles` and every `short_runs` row with origin `watch:%`.

## 8. Titles (`streamer_title`, applied in `autonomous.py` metadata step for `gta6_stream` campaigns)
Every title is `Streamer | line | GTA6` (≤ 90 chars, validator limit); **`GTA6` is only added when the clip's game really is GTA 6** (`stream_watch.is_gta(game)`; the moment's `game` travels in the `.source.json` as `game`) - a rehearsal clip from another game gets `Streamer | line` (a bug on 2026-11-18 labelled Zelda/WoW clips as GTA6): display name from `NAMES` (e.g. Kai Cenat, xQc, IShowSpeed, CaseOh), any
existing GTA 6 / streamer mention in the model's line is removed, the line is shortened first, `title_candidates` get the same rule, `#GTA6` is always the first hashtag.
Covers (Publikálás): `publish_library.cover_hook(title)` turns the title into `Streamer · line · GTA6` (≤ 60, middle dropped first) and the UI regenerates the covers when the title field is left.

## 9. Publishing policy (owner decision, 2026-11-18)
The owner posts by hand in the Publikálás page. `review_before_upload` must stay **true**; nothing in the watcher uploads. Source rights of stream clips are unverified (the owner knowingly accepts that).
Leaked / pre-release footage is refused everywhere (hence the date gate and the game filter).

## 10. Backend API (`stream_watch.dispatch`, called through the existing `project_app` bridge op, so no new Swift allow-list entry is needed)
`watch_snapshot {project?, channel?}` (settings, channels with live state, moments, chart of the focused channel, counts, gate/paused/listener flags),
`watch_save {patch}` (any key of `DEFAULT`), `watch_fetch {id}`, `watch_produce {id}`, `watch_dismiss {id}`.

## 11. Operating notes
- Verify the chain on a real broadcast: `live.json` shows `live:true` + `game`, `chat.sqlite` fills (`select channel,count(*) from buckets group by 1`), `stream_moments` rows appear, clips land in `sources/moments`.
- Tune quality with `min_score` (scores seen on launch day: 5.7–52.6; 15 kept ~9 of 56) and `per_hour`; tune earliness with `sensitivity`.
- The Clip Farm renders one run at a time, so throughput is limited by rendering, not by detection.
- Python tests: `python3 -m unittest test_stream_watch` (the full suite via `tools/deploy.py`). Deploy: `python3 tools/deploy.py --allow-dirty --no-push` during the day; deploy waits up to an hour for an idle gap in the worker.
- Known untested: YouTube live-chat reader and YouTube live-from-start clip download, launch-day behaviour at scale, UI in the native WKWebView.
- Do not scrape sites for which the auto-mode classifier refuses access; do not store chat texts or user names.

## 12. Score, ranking and automatic scheduling (Publikálás)

Files: `publish_score.py` (score), `publish_learn.py` (learning from real reach), `publish_plan.py` (`suggest`, `auto_tick`), `publish_library.py` (`runs`, `run_of`, `cover_hook`), `publish_hub.py` (`videos` adds `score`, `score_parts`, `score_basis`).
- A Short's real title/description/hashtags come from its run's `publishing-package.json` (stored in `short_runs.data.metadata`), found by the rendered file (`short_runs.data.render.saved`); the watcher moment via `origin = 'watch:<moment id>'`.
- **Score 0-100** = estimate (not a measurement): chat 40 (`40·(1−e^(−moment_score/20))`), format 20 (vertical, 20-45 s best), frame 15 (facecam `stack` layout 8 / `fit` 4, captions 7), title 15 (`Streamer | line | GTA6` = 15), check 10 (`quality-check.json` status `READY_*` + full decode passed), history 15 (only with real reach data, see below). Missing parts are left out and the rest scaled; without chat data the maximum is 70. Not checked or not GTA 6 → capped at 39.
- **history** (`publish_learn`): reach items of the connected accounts (`integrations/social/<key>/reach.json`, item `id` = `social_posts.external_id`, `views`) joined to the posts older than 12 h; per streamer mean views vs overall mean, shrunk with 2 pseudo-samples, needs ≥ 5 measured posts overall; factor 0.25-4.
- **Planner order**: `score × freshness` (clips lose half their pull every 48 h, floor 0.35); videos below `min_score` (default 55, `publish-auto.json`) are never proposed. Each channel has its own slots/daily limit (`publish_plan.settings`), a video goes to a channel once, copies on several channels are staggered ≥ 2 h.
- **Automatic scheduling** (`publish-auto.json`: `enabled` default **false**, `min_score`, `ahead_hours` 36): `publish_hub.tick` → `plan.auto_tick` every ≥ 10 min fills each channel's next slots within 36 h with the best proposals through `plan.apply` (status `scheduled`; the normal scheduler then uploads at the time). Switch: op `publish_auto {enabled, min_score}`. Single post can go out now with op `publish_now {id}`.
- Accounts: one channel = one account (`merge_duplicates` folds a re-connected channel into the oldest account).
