"""Install ORBIT separately; preserve MiLLIONS and every existing project/account."""
import json
import os
import plistlib
import re
import shutil
import time
import subprocess
from pathlib import Path

def install():
    source=Path(__file__).resolve().parent
    root=Path.home()/'Library/Application Support/Orbit'
    core=root/'core';core.mkdir(parents=True,exist_ok=True)
    for name in ('ORBIT-OBJECTIVES.md','updater.py','writer_models.py','EDITING-ENGINE.md','TOPIC-RESEARCH.md','edit_contract.py','creative_direction.py','conversation_intake.py','content_survey.py','youtube_discovery.py','transcript_quality.py','short_metadata.py','reaction_framing.py','narration.py','stock_media.py','remotion_runtime.py','render_quality.py','missions.py','enterprise.py','venture.py','venture_build.py','strategy_lab.py','launch.py','product_check.py','site_recorder.py','concierge.py','design_studio.py','design_post.py','project_apps.py','workspace_app.py','gta6.py','project_trash.py','etsy.py','etsy_runtime.py','etsy_files.py','chat_sessions.py','canvas.py','chat_attachment.py','chat_video_preview.py','app_search.py','memory_brain.py','assist_jobs.py','model_finder.py','generation_downloads.py','local_video.py','story_animation.py','story_episode.py','story_render.py','story_audio.py','story_motion.py','story_identity.py','story_puppet.py','story_mocap.py','browser_web.py','intent_router.py','autopilot_hub.py','story_illustrate.py','story_cutout.py','kobold_link.py','kobold_brain.py','trading_agents.py','media_posters.py','musicvideo.py','autonomy.py','activity_now.py','kobold_orbit_schema.json','sim_short.py','sim_tools.py','szim_engine.py','szim_recipes.py','szim_run.py','szim_trendhang.py','szim_teljesitmeny.py','szim_megszakitas.py','szim_app.py','skill_library.py','story_captions.py','story_reference.py','story_music.py','music_trends.py','story_voices.py','sfx_library.py','sfx_generate.py','asset_library.py','email_hub.py','first_run.py','email_brief.py','orbit_server_base.py','voice.py','daily_report.py','self_heal.py','housekeeping.py','revenue.py','storage_guard.py','scheduler_services.py','editorial_schemas.py','semantic_boundaries.py','editing_memory.py','edit_review.py','story_director.py','smart_framing.py','model_evaluation.py','editing_experiments.py','audio_context.py','assembly_plan.py','short_project_files.py','source_quality.py','model_manifest.py','workflow_health.py','app_capabilities.py','editorial_evidence.py','google_trends_source.py','clip_farm.py','PIXEL_WORKSHOP.md','pixel_layout.py','source_policy.py','assistant_context.py','growth.py','publication.py','publish_hub.py','align_runtime.py','scene_objects.py','scene_events.py','scene_quality.py','scene_templates.py','scene_production.py','story_contract.py','publish_library.py','publish_score.py','publish_learn.py','publish_plan.py','publish_reach.py','thumb_runtime.py','social_runtime.py','stream_watch.py','stream_watch_runtime.py','story_series.py','trend_radar.py','stickman_rig.py','stickman_fx.py','stickman_render.py','stickman_audio.py','stickman_studio.py','editorial-requirements.lock','supervisor_runtime.py','inference_gate.py','automations.py','project_registry.py','action_journal.py','assistant_resilience.py','execution_queue.py','short_prompt_contract.py','short_recovery.py','short_feedback.py','telegram_control.py','editorial.py','studio.py','reply_stream.py','assistant_tools.py','conversation_state.py','assistant_skills.py','skill_api.py','SKILL-LEARNING.md','project_scope.py','request_intent.py','mail_search.py','resource_monitor.py','personal_graph.py','memory_graph.py','sfx.py','comedy.py','raw_footage.py','quick_status.py','self_improve.py','computer.py','computer_agent.py','automation_intent.py','story_quality.py','hands.py','OrbitHands.swift','tool_benchmark.py','model_locator.py','services.py','seed_projects.py','mobile_server.py','space.py','progress.py','bridge.py','worker.py','media_tools.py','video_intelligence.py','media_inference.py','render_tools.py','video_render.py','youtube.py','youtube_runtime.py','clip_sources.py','clip_runtime.py','autonomous.py','gallery.py','commander.py','model_hub.py','model_router.py','language_bridge.py','ssd_server.py','short_style.py','montage.py','connections.py','ai_runtime.py','inference_stream.py','research.py','public_web.py','notifications.py','image-requirements.lock','media-requirements.lock','tracking-requirements.lock','README.md'):shutil.copy2(str(source/name),str(core/name))
    shutil.copytree(source/'vendor',core/'vendor',dirs_exist_ok=True)
    shutil.copytree(source/'kobold_contract',core/'kobold_contract',dirs_exist_ok=True)
    shutil.copytree(source/'remotion',core/'remotion',dirs_exist_ok=True,symlinks=True)
    app=Path('/Applications/ORBIT.app')
    if app.exists():
        metadata=plistlib.loads((app/'Contents/Info.plist').read_bytes())
        if metadata.get('CFBundleIdentifier')!='hu.orbit.studio':raise ValueError('Másik alkalmazás található a célhelyen.')
    binary=app/'Contents/MacOS';binary.mkdir(parents=True,exist_ok=True)
    shutil.copy2(str(source/'runtime/Orbit'),str(binary/'Orbit'))
    resources=app/'Contents/Resources';resources.mkdir(parents=True,exist_ok=True)
    shutil.copytree(str(source/'web'),str(resources/'Studio'),dirs_exist_ok=True)
    shutil.copytree(str(source/'mobile'),str(core/'mobile'),dirs_exist_ok=True)
    # The public build's starting projects (agents and prompts only), loaded into an empty ORBIT.
    if (source/'seed').is_dir():shutil.copytree(str(source/'seed'),str(core/'seed'),dirs_exist_ok=True)
    icon=source/'runtime/Orbit.icns'
    if not icon.exists():icon=source/'assets/Orbit.icns'
    if icon.exists():shutil.copy2(str(icon),str(resources/'Orbit.icns'))
    metadata={'CFBundleIdentifier':'hu.orbit.studio','CFBundleName':'ORBIT','CFBundleDisplayName':'ORBIT','CFBundleExecutable':'Orbit','CFBundlePackageType':'APPL',
        'CFBundleShortVersionString':'2.5.0','CFBundleVersion':'24','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication','CFBundleIconFile':'Orbit.icns'}
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(metadata))
    subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(app)],check=True)
    # Where this ORBIT was installed from, so it can update itself later (updater.py).
    try:version=re.search(r"ORBIT_VERSION='([^']+)'",(source/'web/settings_ui.js').read_text()).group(1)
    except (OSError,AttributeError):version=''
    try:build=(source/'BUILD').read_text().strip()
    except OSError:build=''
    update_source=(os.environ.get('ORBIT_UPDATE_SOURCE') or '').strip()
    (root/'install.json').write_text(json.dumps(dict(checkout=os.environ.get('ORBIT_CHECKOUT') or str(source.parent),version=version,build=build,source=update_source,branch='main',installed_at=time.time())))
    print('Installed:',app);print('Data:',root)

if __name__=='__main__':install()
