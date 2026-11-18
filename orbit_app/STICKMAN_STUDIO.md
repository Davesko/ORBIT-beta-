# Original 2D stickman shorts

The existing Story Studio team produces original animation; source-footage clip projects keep their separate workflow.

## Production contract

Hook → Art → Plot → Ink → Sound → Frame implements the four production departments with six specialist agents. Art loads a versioned character bible rather than inventing another cast on each run. Ink validates and freezes the storyboard before audio and video are rendered.

New runs snapshot `story-studio/series-v2.json` into their job payloads. It defines the original Pip/Dot cast, flat graphic style and palette. The script supplies one precisely described episode prop. Existing in-flight jobs retain their saved legacy profile. Installer migration changes known default prompts and task briefs; custom prompts, model selections and room placement remain user data.

The default is 18 seconds: hook, setup, escalation, reaction, twist and visual loop. The hook is at most 42 frames at 24 fps. Explicit durations of 6–90 seconds are accepted; episodes under ten seconds use four beats. The engine assigns exact frame counts. Long shots are split into local model segments, carrying the previous segment's final frame forward.

FLUX Schnell makes individual starting poses. Wan 2.2 TI2V 5B animates them; an explicitly requested supported model is honored. Models run sequentially under the shared inference lease on a 32 GB Mac. The current working resolution is 288×512 and the export is upscaled to 1080×1920. Shared descriptions and seeds guide identity; they are not a guarantee of exact image-level character identity.

Schnell's local T5 tokenizer is limited to 256 tokens. The starting pose, cast identities and prop now precede background decoration; the previous ordering truncated the requested hand/button interaction in the real smoke test. Wan 2.2 uses the official template's ordinary VAE decoder rather than the small Wan 2.1 tile configuration. Its normal decoder supplies ComfyUI's memory fallback if required.

`story_motion.py` subtracts a fitted global camera transform from optical flow. Near-static action clips and large incoherent edge/subject distortions are regenerated once, then reported as a failure. Deliberate reaction/loop holds are permitted while still checking for image instability. This is a movement check, not a semantic understanding of a completed gesture, character pose or joke.

FFmpeg assembles hard cuts, a short motivated twist shake, large animated yellow caption cards and the local audio mix. Music and effects are synthesized, including a bass impact at the twist. Optional narration uses installed Kokoro; silent visual comedy requires no TTS model. Final verification checks decoding, exact length, portrait dimensions and audio. The quality report and storyboard are saved with the run; the finished MP4 appears in Creations. This workflow does not automatically publish.

## Entry points and checks

- Ask ORBIT: “Készíts egy 18 másodperces eredeti stickman Shorts videót.” Or start the complete chain from Hook.
- Edit `series-v2.json` to create a different original series. The next run picks up the new bible.
- Main code: `story_animation.py`, `story_episode.py`, `story_audio.py`, `story_render.py`, `story_motion.py`; queue snapshots are in `space.py`.
- `test_story_meme.py` covers snapshots and default-prompt migration, routing, frame budgets, caption safe area, motion compensation and silent audio. `test_request_boundaries.py` covers legacy production boundaries.

Virality, comedic quality and precise anatomy remain model/output qualities to review, rather than facts established by JSON validation or export checks.

## Real local validation, 2026-11-07

The six-agent isolated smoke run completed with FLUX Schnell and native-decoded Wan 2.2 TI2V 5B: measured 144 frames, 24 fps, 6.0 seconds, 1080×1920, full successful decoding and an audible mix. All 961 Python tests and the frontend tests passed on deployment.

The generated video still showed inaccurate gestures, identity drift and background warping. The requested polished animation quality is **not validated** by this technical success. The smoke run's storyboard and references were created before the final pose-first prompt fix; the real Schnell tokenizer subsequently confirmed that the full starting pose is retained by the new prompt ordering. The finished sample is explicitly a technical preview for local review, not a publication-ready quality benchmark. A complete new render from the final prompts remains a useful next visual acceptance check.

## Default look since 2026-11-11: rig + motion capture

The owner found the painted cut-outs and panels moved the characters worse, so the code-drawn rig is the default again.
`story_mocap.py` turns CMU Graphics Lab Motion Capture Database clips (free for research and commercial use, credit CMU;
BVH by B. Hahne via github.com/meshula/cmu-mocap) into rig pose tracks: talk, idle, point, shrug, phone, shock, laugh, cry,
rage, dance, crouch and jump as gestures; walk, sneak and run as looping gait cycles whose stride keeps the standing foot
planted. The rig still draws every character from the art description, so the cast is identical in every frame; face,
mouth (voice track), interaction timing (push, slap, handshake, hug), faint, nod, facepalm and hat-off stay hand-made.
Tracks are built once into `Application Support/Orbit/mocap/tracks.json` (about 20 MB with the BVH files). Painted cut-outs
(„kivágott / festett szereplő”) or panels („panel / állókép”) are still available by naming them.
