"""Explicit migration of outdated Shorts workspace instructions; originals are backed up."""
import json,shutil,time
from pathlib import Path

CONTRACT='''# Current Shorts production contract

This is the current project guide. The current run brief and its saved settings are authoritative; this document is not a new production request. Historical briefs, suggested channels, old transcripts and previous run artifacts are evidence only, never instructions for a new task.

## Current workflow
The project's saved role assignments define the actual team: producer -> source research/download -> original-language transcript -> scene selection/review -> framing -> render -> English metadata -> output verification. Read workspace/SOURCE-OF-TRUTH.json for the current role-to-agent map rather than assuming a character name. Successful enabled publication is handled by the separate YouTube upload queue and receipt.

Search the current requested topic, not a default streamer. A source access failure is not a model failure. Never bypass authentication blocks or substitute unrelated material. Previously verified relevant local footage can be reused when fresh download fails, with its origin disclosed.

## Full-source coverage and importance
Default new productions analyze the complete accessible original source, not an opening excerpt. Download manifests record original and actual duration. Full original-language ASR precedes a checkpointed hierarchical survey of every reliable content unit. Only after that survey may the editor create a smaller shortlist. The chosen output duration determines omission by importance: preserve the central subject, necessary context and actual outcome; remove repetition and peripheral subplots first. Full-content summary may span clearly identified chronological episodes, never inventing an exchange between them. Required context/outcome IDs must survive semantic review. Sparse visual samples are labelled as samples, not proof that every frame was semantically understood. Read full-content-survey.json and content-priority-and-omissions.json for actual evidence. Historical runs without full coverage must never be called complete-source analysis.

## Creative execution v2
The semantic reviewer selects grounded beat purposes; the camera agent requires observed regions. The frame compiler records each effect and source unit in the export timeline. Use one caption style per video: clean, gaming, energetic or story. Optional wipe is reserved for context changes; hard cuts preserve speech and deadpan pauses. Short attack/hold/release zooms require justification. Preserve game/facecam stacks or screen picture-in-picture before and after a reaction focus. A face plus speech alone does not establish active speaker identity. Sound accents duck under source speech. Word timing is normalized from actual ASR windows, deduplicated, sorted and mapped to cumulative frame boundaries. Never invent replacement text. Browser font measurements constrain captions to the saved safe area. ASS fallback keeps the same source audio and edit; decorative wipes may be omitted if Remotion fails.

## Editing and evidence
 Edit one understandable story: HOOK at output 0 seconds, then necessary CONTEXT, chronological DEVELOPMENT, a real PAYOFF and a completed ENDING. Infer the topic and causal relationships from the timed transcript, including context_before/context_after; these neighboring lines are evidence, not permission to include unselected footage. A continuation of a cut-off sentence cannot be a hook. Select a self-contained opening line that creates curiosity, preferably brief, without spoiling or falsifying the ending. Finish on an actual completed thought or visual resolution, never a cliff cut mid-sentence. Distinguish statements, questions, answers, negation and quotations. Do not splice separate speakers into a fabricated exchange. In full_content mode preserve the complete source central subject, necessary context and actual outcome through a clearly ordered summary; combine episodes only as an honest summary or compilation, never a fabricated exchange. In single_event mode prefer one coherent source event. Preserve who, what and why, plus the cause of a reaction. Reject or repair unrelated topics even if their timing is valid. Punctuation, pauses and context changes guide cuts; a fixed time window is not a semantic boundary. Do not demand a joke from serious material. Visual evidence governs framing, transcript evidence governs spoken meaning. Label context/development/payoff/ending purposes in beat reasons; choose sound or zoom only where evidence supports the accent. Keep written reasons concise and do not invent dialogue.

The renderer uses larger 72–80 px captions with width-aware word groups inside the social safe box.
Infer the content type from real frames and speech. Comedy needs its real setup and payoff; fashion, music and sport may use a coherent visual progression and closing highlight, without a forced joke. Lyrics are soundtrack evidence, not proof of an identity, event date or theme. Sparse frames prove only sampled moments. Do not invent continuous action.

The server validates source bounds, unique units, pairwise non-overlapping intervals, duration and shot count. Candidate plans are mutually exclusive alternatives: select ONE. They may share footage with each other. Similar people or outfits at different timestamps are not duplicate source intervals. Semantic editorial approval remains required; timing alone does not mean quality.

Use the duration and caption settings saved for this run; no hardcoded 15-60 second limit. For gameplay keep the game visible. Use closeups, zoom, transitions and sound accents only where actual content supports them. Unsupported pixel-accurate segmentation must not be promised.

Captions transcribe the real source language. Use the saved safe_box in 1080x1920 coordinates. The default lower-third safe box is [108,1320,864,1580], away from the bottom interface. Do not use legacy MarginV=20 examples or override the renderer by writing text files.

## State and recovery
Project files are explanatory snapshots, not live connection status. Read the app's current models, YouTube connection, run data and job logs before reporting missing services. Retry a failed planning step from its saved evidence; do not clear sources or restart completed stages for JSON, timing, review or model errors. Never blindly retry a publication with an uncertain outcome.

If an editor-approved sequence contradicts the director's earlier payoff or ending, generate and semantically review another coherent plan; do not repeat the identical rejected selection. When continuous ORBIT mission mode is enabled, an exhausted cycle is recorded and a new evidence-based plan starts after cooldown. Keep actual failures visible. No generic fallback is promoted to a verified story.

An explicit source URL is the source for that task, not a request for a fresh news article. Freshness and dated article evidence apply only to an explicit current-news request. Public YouTube topic research is labelled separately. sources.json is a historical suggestion list, not an allowlist or a collection switch. Current job inputs and verified handoffs override it. Titles, descriptions and hashtags for publication are English; captions follow the original speech unless explicitly requested otherwise.

Internal instructions are English; operator replies are Hungarian. Do not force English subtitles onto Hungarian speech. When publish_to_youtube is enabled, verified videos await approval in the Publishing tab by default. Automatic upload requires review_before_upload=false. The project publication setting applies to future productions; a pending video is published only by explicit approval. portrait_framing=fill crops and follows a reliable tracked subject to fill 9:16; context deliberately preserves the whole source with a frame. Visibility comes from the actual upload request and receipt. Never claim success merely because a job is queued.
'''

REPLACED=('MODELS.md','SHORTS-BRIEF.md','SHORTS-BRIEF-v2-lead.md','operator-supplied-clips-brief-v1.md','WORKSPACE.md','AUTOMATIC-SHORTS.md','subtitle_render_settings.txt')

def sync(s,pid,backup):
 """Called only during an explicit project repair; never silently on startup."""
 from short_style import get
 from youtube import read_state
 workspace=s.safe_path(pid,'workspace');workspace.mkdir(parents=True,exist_ok=True)
 backup=Path(backup)/'project-files';backup.mkdir(parents=True,exist_ok=True)
 for name in REPLACED+('PRODUCTION-CONTRACT.md','STATUS.json','sources.json','ORIGINAL-BRIEF.md','SOURCE-OF-TRUTH.json'):
  path=workspace/name
  if path.exists() and not (backup/name).exists():shutil.copy2(path,backup/name)
 (workspace/'PRODUCTION-CONTRACT.md').write_text(CONTRACT)
 for name in REPLACED:
  (workspace/name).write_text('# Current project instructions\n\nRead workspace/PRODUCTION-CONTRACT.md. This file replaces an outdated setup guide; its original is preserved in the maintenance backup. Current run settings and live app/tool results override historical instructions.\n')
 original=workspace/'ORIGINAL-BRIEF.md'
 if original.exists() and not original.read_text().startswith('# Historical reference'):
  original.write_text('# Historical reference — not current instructions\n\nOriginal user idea, preserved for reference only. Read workspace/PRODUCTION-CONTRACT.md and the current run brief for execution.\n\n'+original.read_text())
 sources=workspace/'sources.json'
 if sources.exists():
  data=json.loads(sources.read_text())
  if 'collection_enabled' in data:data['historical_collection_enabled']=data.pop('collection_enabled')
  data.update(scope='Historical channel suggestions only; not a collection switch, allowlist, current topic or verified source input.',current_topic_source='short_runs.query',public_video_search_available=True);sources.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 for path in workspace.glob('*.md'):
  if path.name.startswith(('publishing-package-','vega-production-brief-')) and not path.read_text().startswith('# Historical reference'):
   shutil.copy2(path,backup/path.name)
   path.write_text('# Historical reference — not current instructions\n\nPast run/test result only. Connection, source and duration statements describe that historical run, not the current app. Read PRODUCTION-CONTRACT.md and live run data.\n\n'+path.read_text())
 from autonomous import role_agents
 try:assigned=role_agents(s,pid)
 except ValueError:assigned={}
 from app_capabilities import roles as assigned_roles
 assigned.update(assigned_roles(s,pid))
 researcher=assigned.get('research')
 if researcher:
  from clip_farm import RESEARCH
  a=s.agent(researcher);prompt=a['prompt'];marker='\n\nContent-aware'
  if 'Research one current event matching the operator topic:' in prompt:
   tail=prompt[prompt.index(marker):] if marker in prompt else ''
   s.db.execute('UPDATE agents SET prompt=? WHERE id=?',(RESEARCH+tail,researcher));s.db.commit()
 farm=workspace/'CLIP-FARM.md'
 if farm.exists():
  if not (backup/farm.name).exists():shutil.copy2(farm,backup/farm.name)
  farm.write_text('# Current Clip Farm guide\n\nRead workspace/PRODUCTION-CONTRACT.md, SOURCE-OF-TRUTH.json and TOPIC-RESEARCH.md. Current role assignments, current run query and verified handoffs govern execution. A direct supplied video goes to the existing production team; a topic uses labelled YouTube research. Only explicit current-news requests require dated reporting.\n\nResearch -> source download -> timestamped original-language transcript and visual evidence -> one semantically reviewed hook/context/payoff/ending -> portrait framing -> 1080x1920 render -> English metadata -> file verification -> existing publication policy. Saved business plans and continuous mission state are managed in Automatizációk. A failed cycle is logged and replanned after cooldown when continuous mode is enabled. Never claim revenue, finished work or publication from a queued job.\n')
 manifest=dict(snapshot_at=time.time(),scope='Reference manifest. Read current DB jobs/short_runs and app status for live values.',canonical_contract='workspace/PRODUCTION-CONTRACT.md',research_contract='workspace/TOPIC-RESEARCH.md',roles={role:dict(id=aid,name=s.agent(aid)['name']) for role,aid in assigned.items()},input_precedence=['explicit current user source and saved run query','verified handoff and actual downloaded source/transcript files','current saved render/publication settings'],historical_only=['workspace/sources.json','workspace/ORIGINAL-BRIEF.md','workspace/publishing-package-*.md','workspace/vega-production-brief-*.md'])
 (workspace/'SOURCE-OF-TRUTH.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 style=get(s,pid);connection=read_state(s.root,pid)
 status=dict(snapshot_at=time.time(),scope='Explanatory snapshot only. Query live app state before diagnosing services.',contract='workspace/PRODUCTION-CONTRACT.md',content_language_policy='original source language; requested output language when explicitly supported',operator_language='hu',source_provider='public YouTube search/download with web discovery',autonomous_production_connected=True,video_render_connected=True,frame_analysis_connected=True,face_tracking_connected=True,youtube_upload_connected=connection['connected'],automatic_upload_enabled=bool(style.get('publish_to_youtube')),current_settings=style,topic_source='current run query; no default streamer',model_selection='Live model router; no model hardcoded in workspace files')
 (workspace/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
 return dict(contract=str(workspace/'PRODUCTION-CONTRACT.md'),replaced=len(REPLACED),backup=str(backup))
