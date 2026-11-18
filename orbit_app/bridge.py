"""JSON-only native bridge. No listener, external credentials or arbitrary shell."""
import base64
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path
from studio import Studio,ROOT,TOOLS,local_api,MODEL_PATTERN,text,uid,now

LABEL='hu.orbit.studio-worker'
def worker_ensure():
    label='gui/'+str(os.getuid())+'/'+LABEL
    if subprocess.run(['/bin/launchctl','print',label],capture_output=True).returncode==0:return
    plist=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist');plist.parent.mkdir(parents=True,exist_ok=True)
    (ROOT/'logs').mkdir(parents=True,exist_ok=True)
    plist.write_bytes(plistlib.dumps({'Label':LABEL,'ProgramArguments':['/usr/bin/python3',str(ROOT/'core/worker.py')],
        'WorkingDirectory':str(ROOT/'core'),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':15,
        'EnvironmentVariables':{'PYTHONDONTWRITEBYTECODE':'1'},
        'StandardOutPath':str(ROOT/'logs/worker.stdout.log'),'StandardErrorPath':str(ROOT/'logs/worker.stderr.log')}))
    subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(plist)],check=True,capture_output=True)

def dispatch(request, studio=None):
    s=studio or Studio();action=request.get('action');pid=request.get('project','universe')
    if action=='snapshot' and studio is None:
        # A new Mac: the background worker is installed by the app's first request.
        try:
            from services import ensure_worker
            ensure_worker()
        except Exception:pass
    if action in ('telegram_status','telegram_pair','telegram_unpair'):
        import telegram_control as tg
        if action=='telegram_status':return dict(ok=True,**tg.status(s))
        if action=='telegram_pair':return dict(ok=True,**tg.pair(s))
        tg.unpair(s);return dict(ok=True)
    if action=='venture_folder':
        # Opens only an Autopilot product folder, chosen by its idea id, in Finder.
        import venture_build
        idea=str(request.get('idea_id') or '').lower()
        if not re.fullmatch(r'[a-z0-9]{1,16}',idea):raise ValueError('Ismeretlen termék.')
        path=s.safe_path(venture_build.PID,venture_build.folder(dict(idea_id=idea)));path.mkdir(parents=True,exist_ok=True)
        subprocess.run(['/usr/bin/open',str(path)],check=False,capture_output=True);return {'ok':True,'path':str(path)}
    if action in ('voice_status','voice_transcribe','voice_speak'):
        # Hungarian voice for the main assistant; audio stays in Orbit/voice on this Mac.
        import voice
        if action=='voice_status':return dict(ok=True,**voice.status())
        if action=='voice_transcribe':return dict(ok=True,**voice.transcribe(request.get('path')))
        return dict(ok=True,**voice.speak(text(request.get('text'),20000)))
    if action=='venture_try':
        # Runs the product's own code and smoke requests in the sandbox, on the owner's click.
        import venture_build,product_check
        idea=str(request.get('idea_id') or '').lower()
        if not re.fullmatch(r'[a-z0-9]{1,16}',idea):raise ValueError('Ismeretlen termék.')
        path=s.safe_path(venture_build.PID,venture_build.folder(dict(idea_id=idea)))
        if not path.is_dir():raise ValueError('Ennek a terméknek még nincs elkészült fájlja.')
        if 'api_index' in request:
            return dict(ok=True,result=product_check.try_api(path,request['api_index'],request.get('body')))
        check=product_check.run(path);return {'ok':True,'summary':product_check.summary(check),'check':check}
    if action=='connections_agents_auto':
        count=s.db.execute("UPDATE agents SET model='auto' WHERE id NOT IN (SELECT id FROM agent_archive)").rowcount;s.db.commit();return dict(ok=True,count=count)
    if action=='connections_status':
        from connections import status
        return dict(ok=True,**status(s.root))
    if action=='connections_save':
        from connections import save
        return dict(ok=True,**save(request.get('settings',{}),s.root))
    if action=='connections_test':
        from connections import test
        return test(request.get('provider'),s.root)
    if action=='ensure':worker_ensure();return {'ok':True}
    if action=='snapshot':
        result=s.snapshot(pid)
        result['jobs']=[j for j in result['jobs'] if j['kind'] not in ('command','command_apply','control_apply','assist')]
        # A project kind with its own workshop view (MiLLIONS for trading projects).
        result['project_app']=__import__('project_apps').describe(s,pid)
        from media_tools import media_models
        # The model list is extra; projects and jobs must load even when a model disk fails.
        try:result['media_models']=media_models(s.root)
        except OSError:result['media_models']=[]
        try:age=now()-(s.root/'worker.heartbeat').stat().st_mtime
        except OSError:age=float('inf')
        result['worker_alive']=age<20
        if 20<=age<90 and s.root==ROOT:
            try:result['worker_alive']=subprocess.run(['/usr/bin/pgrep','-f',str(ROOT/'core/worker.py')],capture_output=True,timeout=1).returncode==0
            except (OSError,subprocess.TimeoutExpired):pass
        result['resources']=__import__('resource_monitor').snapshot()
        try:result['storage']={k:v for k,v in json.loads((s.root/'storage-health.json').read_text()).items() if k in ('free_bytes','low_threshold','admission_paused','observed_at')}
        except (OSError,ValueError):result['storage']=None
        try:result['health']=__import__('self_heal').summary(s)
        except Exception:result['health']=None
        # Things only the owner can fix, shown as a header warning (now: lost YouTube logins).
        try:
            from youtube import needs_reconnect
            names={r['id']:r['name'] for r in s.rows('SELECT id,name FROM projects')}
            result['attention']=[dict(kind='youtube',project=x['project'],name=names.get(x['project'],x['project']),text=x['error']) for x in needs_reconnect(s.root)]
        except Exception:result['attention']=[]
        return result
    if action=='models':
        try:
            models=local_api('ollama','api/tags').get('models',[])
            from ai_runtime import cloud_models
            models+=cloud_models()
            return {'ok':True,'models':[{'name':m['name'],'size':m.get('size',0),'family':m.get('details',{}).get('family',''),'storage':m.get('storage','Belső')} for m in models]}
        except Exception as exc:return {'ok':False,'models':[],'message':'Az Ollama nem elérhető: '+str(exc)}
    if action in ('model_evaluation_status','model_evaluation_start'):
        import model_evaluation as evaluation
        return dict(ok=True,**(evaluation.status(s,pid) if action=='model_evaluation_status' else evaluation.enqueue(s,pid,request.get('model'),request.get('suite','general'))))
    if action=='model_hub':
        from model_hub import status
        return dict(ok=True,**status())
    if action.startswith('command_'):
        from commander import schema,state,enqueue,approve,roots
        schema(s);s.project(pid)
        if action=='command_state':return dict(ok=True,**state(s,pid,bool(request.get('global')),request.get('session')))
        if action=='command_retry_agent':
            from commander import retry_agent
            return dict(ok=True,job=retry_agent(s,request.get('turn'),request.get('id')))
        if action=='command_overview':
            from commander import overview
            return dict(ok=True,**overview(s))
        if action=='command_memory_save':
            from commander import memory_save
            memory_save(s,request);return {'ok':True}
        if action=='command_memory_forget':
            s.db.execute('DELETE FROM assistant_memory WHERE key=?',(request.get('key'),));s.db.commit();return {'ok':True}
        if action=='command_preferences_save':
            from commander import preferences_save
            preferences_save(s,request.get('settings',{}));return {'ok':True}
        if action=='command_continue':
            from supervisor_runtime import continue_turn
            return dict(ok=True,job=continue_turn(s,request.get('turn'),request.get('model','auto')))
        if action=='command_send':
            # A chat of the owner's: a message without one starts a new chat. Other callers keep the shared history.
            session=None
            if 'session' in request:
                import chat_sessions
                session=chat_sessions.ensure(s,request.get('session'),request.get('prompt'))
            return dict(ok=True,job=enqueue(s,pid,request.get('prompt'),request.get('model',''),request.get('image'),bool(request.get('global')),spoken=bool(request.get('spoken')),session=session,open_file=request.get('open_file'),workspace=request.get('workspace') is True,attachment=request.get('attachment'),attachments=request.get('attachments')),session=session)
        if action=='command_approve':return dict(ok=True,job=approve(s,pid,request.get('id'),bool(request.get('global'))))
        if action=='command_reject':
            s.db.execute("UPDATE command_turns SET status='rejected' WHERE id=? AND status='review' AND (project=? OR (? AND id IN (SELECT turn_id FROM command_global)))",(request.get('id'),pid,int(bool(request.get('global')))));s.db.commit();return {'ok':True}
        if action=='command_grant':
            path=Path(request.get('path','')).expanduser().resolve()
            if not path.is_dir() or path==Path('/'):raise ValueError('Konkrét munkamappát válassz.')
            s.db.execute('INSERT OR IGNORE INTO command_roots VALUES(?,?)',(str(path),now()));s.db.commit();return {'ok':True}
        if action=='command_revoke':
            s.db.execute('DELETE FROM command_roots WHERE path=?',(request.get('path'),));s.db.commit();return {'ok':True}
        raise ValueError('Ismeretlen főchat-művelet.')
    if action=='engines':
        try:local_api('comfy','system_stats',timeout=2);return {'ok':True,'comfy':True}
        except Exception:return {'ok':True,'comfy':False}
    if action=='project_create':return {'ok':True,'project':s.create_project(request.get('name'),request.get('description',''))}
    s.project(pid)
    if action=='project_app':
        import project_apps
        return dict(ok=True,**project_apps.dispatch(s,pid,str(request.get('op') or ''),request.get('args') if isinstance(request.get('args'),dict) else {}))
    if action in ('enterprise_status','enterprise_save'):
        if request.get('scope')=='business_lab' or request.get('settings',{}).get('scope')=='business_lab':
            import venture
            if action=='enterprise_status' and request.get('refresh_metrics'):
                import launch,revenue,venture_build
                idea=request.get('idea_id')
                focus=venture_build.focus_for(s,idea) if idea else None
                if focus:launch.refresh(s,venture_build.folder(focus),root=s.root)
                revenue.refresh(s)
                return dict(ok=True)
            # The /ma Telegram summary in the app (passed through the existing action, so no native change).
            if action=='enterprise_status' and request.get('day_summary'):
                from daily_report import today
                return dict(ok=True,text=today(s))
            # An earlier project opened from the Autopilot page's project list.
            # (Its own key: the web layer fills 'project' with the open ORBIT project.)
            if action=='enterprise_status' and request.get('idea_id'):return dict(ok=True,project=venture.project(s,request['idea_id']))
            if action=='enterprise_status' and request.get('head') is True:return dict(ok=True,mission=venture.status_head(s))
            if action=='enterprise_status':return dict(ok=True,mission=venture.status(s,compact=request.get('compact') is True))
            return dict(ok=True,**venture.configure(s,request.get('settings',{})))
        import enterprise
        if action=='enterprise_status':return dict(ok=True,mission=enterprise.status(s,pid))
        return dict(ok=True,**enterprise.configure(s,pid,request.get('settings',{})))
    if action in ('mission_save','mission_start','mission_resume','mission_pause','mission_list'):
        import missions
        if action=='mission_list':return dict(ok=True,**missions.listing(s,detail=True))
        if action=='mission_resume':return dict(ok=True,**missions.resume(s,pid,request.get('id')))
        if action=='mission_start':return dict(ok=True,**missions.start(s,pid,request.get('id')))
        if action=='mission_pause':return dict(ok=True,**missions.pause(s,pid,request.get('id'),request.get('cancel') is True))
        mid=missions.save(s,pid,request.get('mission'),request.get('_origin'))
        if request.get('start') is True:missions.start(s,pid,mid)
        return dict(ok=True,id=mid)
    if action.startswith('automation_'):
        import automations as auto
        if action=='automation_tasks':return dict(ok=True,**auto.task_directory(s))
        if action=='automation_context':return dict(ok=True,**auto.task_context(s,pid))
        if action=='automation_toggle':return dict(ok=True,**auto.toggle(s,pid,request.get('id'),request.get('enabled')))
        if action=='automation_list':return dict(ok=True,**auto.listing(s,pid))
        if action=='automation_save':return dict(ok=True,id=auto.save(s,pid,request.get('automation',{})))
        if action=='automation_run':return dict(ok=True,**auto.launch(s,pid,request.get('id'),manual=True))
        if action=='automation_stop':
            auto.stop(s,pid,request.get('id'),bool(request.get('archive')),bool(request.get('cancel')));return dict(ok=True)
        raise ValueError('Ismeretlen automatizációs művelet.')
    if action in ('editing_review','editing_feedback','editing_preferences','editing_revise'):
        from edit_review import detail,revise
        from editing_memory import save,preferences
        if action=='editing_review':return dict(ok=True,**detail(s,pid,request.get('id')))
        if action=='editing_feedback':return dict(ok=True,feedback=save(s,pid,request.get('id'),request.get('tag'),request.get('note','')))
        if action=='editing_preferences':return dict(ok=True,feedback=preferences(s,pid,request.get('notes','')))
        return dict(ok=True,**revise(s,pid,request.get('id'),request.get('kind'),request.get('request_id')))
    if action.startswith('growth_'):
        import growth
        if action=='growth_list':return dict(ok=True,**growth.listing(s,pid))
        if action=='growth_save':return dict(ok=True,settings=growth.save(s,pid,request.get('settings',{})))
        if action=='growth_refresh':return dict(ok=True,**growth.enqueue(s,pid,'growth_metrics' if request.get('kind')=='metrics' else 'growth_research'))
        if action=='growth_produce':return dict(ok=True,**growth.start_topic(s,pid,request.get('id')))
        raise ValueError('Ismeretlen elemzési művelet.')
    if action in ('publication_list','publication_approve','publication_settings'):
        import publication
        if action=='publication_list':return dict(ok=True,**publication.listing(s,pid))
        if action=='publication_settings':return dict(ok=True,style=publication.settings(s,pid,request.get('mode')))
        return dict(ok=True,**publication.approve(s,pid,request.get('id'),request.get('title'),request.get('description'),request.get('made_for_kids'),retry=request.get('retry') is True,confirmed_absent=request.get('confirmed_absent') is True))
    if action=='production_resume':
        from short_recovery import resume
        return dict(ok=True,**resume(s,pid,request.get('id')))
    if action=='project_role_save':
        from app_capabilities import assign_role
        return dict(ok=True,capabilities=assign_role(s,pid,request.get('role'),request.get('agent')))
    if action=='app_status':
        from app_capabilities import status
        return dict(ok=True,**status(s))
    if action=='gallery_list':
        from gallery import page
        return dict(ok=True,**page(s,pid,request.get('folder'),request.get('offset',0)))
    if action=='short_cancel':
        from clip_sources import schema
        schema(s)
        s.db.execute('UPDATE short_automation SET enabled=0 WHERE project=?',(pid,));s.db.commit()
        for row in s.rows("SELECT id FROM jobs WHERE project=? AND status IN ('running','queued') AND json_extract(payload,'$.auto_step') IS NOT NULL",(pid,)):s.cancel(row['id'])
        return {'ok':True}
    if action=='short_start':
        if request.get('files'):
            # The owner's own raw footage (chat attachment, picked file or project media).
            from raw_footage import submit as footage_submit
            return dict(ok=True,**footage_submit(s,pid,request['files'],request.get('query',''),request.get('requirements'),request.get('_origin'),request.get('from_project')))
        if request.get('sources'):
            from source_policy import bundle,submit
            return dict(ok=True,**submit(s,pid,bundle(s,pid,request['sources'],request.get('query','Direct video sources')),request.get('requirements'),request.get('_origin')))
        from clip_farm import start_research
        from clip_sources import youtube_id
        researched=None if youtube_id(request.get('query','')) or request.get('source_mode')=='topic' else start_research(s,pid,request.get('query'),request.get('requirements'))
        if researched is not None:return dict(ok=True,**researched)
        from execution_queue import submit_short
        return dict(ok=True,**submit_short(s,pid,request.get('query'),request.get('requirements'),request.get('_origin')))
    if action=='short_automation_save':
        if request.get('requirements'):
            from short_style import save as save_style
            save_style(s,pid,request['requirements'])
        from autonomous import save_settings
        save_settings(s,pid,request.get('query'),request.get('enabled',False),request.get('interval',180),request.get('daily_limit',3),request.get('plan'),request.get('daily_goal'));return {'ok':True}
    if action=='youtube_status':
        from youtube import read_state
        return dict(ok=True,**read_state(s.root,pid))
    if action=='youtube_config':
        from youtube import save_config
        save_config(s.root,pid,request.get('content',''));return {'ok':True}
    if action=='youtube_connect':
        from youtube import connect
        return {'ok':True,'auth_url':connect(s.root,pid)}
    if action=='youtube_disconnect':
        from youtube import folder
        folder(s.root,pid)
        completed=subprocess.run([str(s.root/'media-runtime/bin/python'),str(Path(__file__).with_name('youtube_runtime.py')),'disconnect',str(s.root),pid],capture_output=True,text=True,timeout=15)
        return json.loads(completed.stdout)
    if action=='youtube_upload':
        from youtube import queue_upload
        return dict(ok=True,**queue_upload(s,pid,request.get('id'),request.get('title'),str(request.get('description','')),request.get('made_for_kids'),request.get('privacy','public')))
    if action=='job_detail':return {'ok':True,'job':s.job_detail(pid,request.get('id'))}
    if action=='story_frames':
        import story_animation
        return {'ok':True,'frames':story_animation.previews(s,pid,request.get('id'))}
    if action in ('agent_archive','agent_restore'):
        aid=request['id'];a=s.agent(aid)
        if a['project']!=pid:raise ValueError('Másik projekt ügynöke.')
        if action=='agent_archive':
            if s.db.execute('SELECT 1 FROM agent_archive WHERE id=?',(aid,)).fetchone():return {'ok':True}
            active=s.db.execute('SELECT count(*) FROM agents WHERE project=? AND id NOT IN (SELECT id FROM agent_archive)',(pid,)).fetchone()[0]
            if active<=1:raise ValueError('Legalább egy aktív ügynöknek maradnia kell a projektben.')
            s.db.execute('INSERT INTO agent_archive VALUES(?,?,?,?)',(aid,pid,json.dumps(a),now()))
            s.db.execute('UPDATE agents SET interval=0,next_run=0 WHERE id=?',(aid,))
            s.db.execute('UPDATE connections SET archived=1 WHERE project=? AND (source=? OR target=?)',(pid,aid,aid))
            for r in s.rows('SELECT id,agents FROM recipes WHERE project=?',(pid,)):
                if aid in json.loads(r['agents']):s.db.execute('UPDATE recipes SET interval=0,next_run=0 WHERE id=?',(r['id'],))
            for j in s.rows("SELECT id FROM jobs WHERE agent=? AND status IN ('queued','running') AND kind NOT IN ('command','command_apply','control_apply','model_pull')",(aid,)):s.cancel(j['id'])
        else:s.db.execute('DELETE FROM agent_archive WHERE id=? AND project=?',(aid,pid))
        s.db.commit();return {'ok':True,'id':aid}
    if action=='recipe_pause':
        changed=s.db.execute('UPDATE recipes SET interval=0,next_run=0 WHERE id=? AND project=?',(request['id'],pid)).rowcount
        if not changed:raise ValueError('Ismeretlen munkafolyamat.')
        s.db.commit();return {'ok':True}
    if action=='project_save':
        s.db.execute('UPDATE projects SET name=?,description=? WHERE id=?',(text(request.get('name'),80),str(request.get('description',''))[:1000],pid));s.db.commit();return {'ok':True}
    if action=='room_save':return {'ok':True,'id':s.save_room(pid,request['room'])}
    if action=='room_archive':s.archive_room(pid,request['id'],request.get('move_to'));return {'ok':True}
    if action=='room_restore':s.restore_room(pid,request['id']);return {'ok':True}
    if action=='connection_save':return {'ok':True,'id':s.save_connection(pid,request['connection'])}
    if action=='connection_archive':s.archive_connection(pid,request['id']);return {'ok':True}
    if action=='graph_run':return dict(ok=True,**s.enqueue_graph(pid,request['agent'],request.get('prompt'),video_model=request.get('video_model')))
    if action=='agent_save':
        data=request['agent'];data['project']=pid
        return {'ok':True,'id':s.save_agent(data)}
    if action in ('chat','agent_run'):
        a=s.agent(request['agent'])
        if a['project']!=pid:raise ValueError('Másik projekt ügynöke.')
        prompt=request.get('prompt')
        if a['id'].startswith('story-'):
            from story_animation import DEFAULT_BRIEF, agent_ids, production_request
            if a['id']==agent_ids(pid)['hook']:
                saved_run=action=='agent_run' and not prompt
                if saved_run or (prompt and production_request(prompt)):
                    run=s.enqueue_graph(pid,a['id'],prompt or DEFAULT_BRIEF)
                    return dict(ok=True,job=run['jobs'][a['id']],**run)
        return {'ok':True,'job':s.enqueue(a['id'],prompt or a['prompt'])}
    if action=='job_cancel':
        row=s.db.execute('SELECT project,kind,payload FROM jobs WHERE id=?',(request['id'],)).fetchone()
        if not row or row['project']!=pid:raise ValueError('Ismeretlen feladat.')
        s.cancel(request['id'])
        if row['kind'] in ('command','command_apply','control_apply'):
            from commander import schema as command_schema
            command_schema(s);turn=json.loads(row['payload']).get('turn')
            for child in s.rows("SELECT id FROM jobs WHERE json_extract(payload,'$.turn')=? UNION SELECT job AS id FROM command_links WHERE turn_id=?",(turn,turn)):s.cancel(child['id'])
            s.db.execute("UPDATE command_turns SET status='cancelled' WHERE id=? AND status!='done'",(turn,));s.db.commit()
        return {'ok':True,'message':'Leállítás kérve. Új művelet már nem indul; a korábban befejezett módosítások megmaradnak.'}
    if action=='pipeline':return {'ok':True,'job':s.enqueue_pipeline(pid,request.get('agents',[]),request.get('prompt'))}
    if action=='recipe_save':return {'ok':True,'id':s.save_recipe(pid,request.get('name'),request.get('agents'),request.get('prompt'),request.get('interval',0),request.get('id'))}
    if action=='recipe_run':
        row=s.db.execute('SELECT * FROM recipes WHERE id=? AND project=?',(request.get('id'),pid)).fetchone()
        if not row:raise ValueError('Ismeretlen munkafolyamat.')
        return {'ok':True,'job':s.enqueue_pipeline(pid,json.loads(row['agents']),row['prompt'],row['id'])}
    if action=='model_pull':
        model=text(request.get('model'),120)
        if not re.fullmatch(MODEL_PATTERN,model) or '..' in model or model.startswith('/') or '://' in model:raise ValueError('Ollama modellnevet adj meg, ne URL-t vagy fájlútvonalat.')
        if s.db.execute("SELECT 1 FROM jobs WHERE kind='model_pull' AND status IN ('queued','running')").fetchone():raise ValueError('Már van folyamatban modellletöltés.')
        aid=s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,))[0]['id']
        return {'ok':True,'job':s.enqueue(aid,'Modell telepítése: '+model,'model_pull',payload={'model':model})}
    if action=='workflow_save':
        graph=request.get('graph');node=str(request.get('prompt_node',''));field=request.get('prompt_field','text')
        if not isinstance(graph,dict) or not 1<=len(graph)<=500 or len(json.dumps(graph))>2*1024*1024:raise ValueError('1–500 csomópontos ComfyUI API JSON szükséges.')
        if not all(isinstance(v,dict) and isinstance(v.get('inputs'),dict) and isinstance(v.get('class_type'),str) for v in graph.values()):raise ValueError('ComfyUI API formátumot exportálj (nem a szerkesztő vászonfájlját).')
        if node not in graph or not isinstance(graph[node]['inputs'].get(field),str):raise ValueError('A prompt csomópontja és szöveges mezője nem található.')
        wid=uid();s.db.execute('INSERT INTO workflows VALUES(?,?,?,?,?)',(wid,pid,text(request.get('name'),80),json.dumps({'graph':graph,'prompt_node':node,'prompt_field':field}),now()));s.db.commit()
        return {'ok':True,'id':wid}
    if action=='media_generate':
        row=s.db.execute('SELECT 1 FROM workflows WHERE id=? AND project=?',(request.get('workflow'),pid)).fetchone()
        if not row:raise ValueError('Előbb adj hozzá egy ComfyUI munkafolyamatot.')
        local_api('comfy','system_stats',timeout=2)
        aid=s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,))[0]['id']
        return {'ok':True,'job':s.enqueue(aid,text(request.get('prompt')),'media',payload={'workflow':request['workflow']})}
    if action=='import_media':
        if request.get('chat_attachment') is True:
            from chat_attachment import import_file
            return dict(ok=True,**import_file(s,pid,request.get('source',''),request.get('pdf_text')))
        from media_tools import import_media
        return {'ok':True,'name':import_media(s,pid,request.get('source',''))}
    if action=='media_analyze':
        from media_tools import MEDIA_TOOLS
        MEDIA_TOOLS=MEDIA_TOOLS|{'render_short'}
        operation=request.get('operation')
        if operation not in MEDIA_TOOLS:raise ValueError('Ismeretlen médiaeszköz.')
        agent=s.agent(request['agent'])
        if agent['project']!=pid or operation not in agent['tools']:raise ValueError('Válassz megfelelő médiaeszközzel rendelkező ügynököt.')
        args={'name':request.get('name'),'timestamps':request.get('timestamps',[0,5,10])}
        if operation=='render_short':
            args={key:request.get(key) for key in ('name','start','duration','layout','subtitle')}
            from render_tools import render_arguments
            render_arguments(s,pid,args)
        s.safe_path(pid,args['name'])
        return {'ok':True,'job':s.enqueue(agent['id'],operation+': '+args['name'],'media_analysis',payload={'operation':operation,'args':args})}
    if action=='import_file':
        filename=Path(text(request.get('name'),180)).name
        if Path(filename).suffix.lower() not in ('.txt','.md','.json','.csv','.py','.js','.html','.css','.svg','.xml','.yaml','.yml'):raise ValueError('Szöveges projektfájlt válassz.')
        raw=base64.b64decode(request.get('data',''),validate=True)
        if len(raw)>1024*1024:raise ValueError('Legfeljebb 1 MB-os szöveges fájl adható hozzá.')
        raw.decode('utf-8');path=s.safe_path(pid,'inputs/'+filename)
        if path.exists():raise ValueError('Már létezik ilyen nevű fájl.')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uid(),pid,filename,str(path),'text',now(),'import'));s.db.commit();return {'ok':True}
    if action in ('artifact','artifact_preview'):
        if action=='artifact':
            from workspace_app import app_id,bundle_path
            if request.get('id')==app_id(pid):return dict(ok=True,path=str(bundle_path(s,pid)))
        row=s.db.execute('SELECT * FROM artifacts WHERE id=? AND project=?',(request.get('id'),pid)).fetchone()
        if not row:raise ValueError('Ismeretlen alkotás.')
        path=Path(row['path']);base=(s.root/'projects'/pid).resolve()
        if base not in path.resolve().parents:raise ValueError('A fájl nincs a projektben.')
        if action=='artifact' and path.suffix.lower() in ('.html','.htm') and any(
            (base/'workspace'/name) in path.resolve().parents for name in ('product','app')):
            from workspace_app import bundle_path
            return dict(ok=True,path=str(bundle_path(s,pid,path.resolve(),row['id'])))
        if action=='artifact_preview':
            if row['kind']=='video':
                poster=path.with_suffix('.jpg')
                if poster.is_file() and base in poster.resolve().parents and poster.stat().st_size<2*1024*1024:return {'ok':True,'kind':'video','poster':'data:image/jpeg;base64,'+base64.b64encode(poster.read_bytes()).decode()}
            if row['kind']=='image' and path.stat().st_size<8*1024*1024:
                import mimetypes
                return {'ok':True,'image':'data:'+str(mimetypes.guess_type(path)[0])+';base64,'+base64.b64encode(path.read_bytes()).decode()}
            return {'ok':True,'content':path.read_text()[:24000] if row['kind']=='text' else '', 'kind':row['kind']}
        return {'ok':True,'path':str(path)}
    raise ValueError('Ismeretlen művelet.')

if __name__=='__main__':
    foreground=None
    try:
        raw=sys.stdin.read(3*1024*1024+1)
        if len(raw)>3*1024*1024:raise ValueError('Túl nagy kérés.')
        request=json.loads(raw)
        if sys.argv[1:]==['--foreground-generation'] and request.get('action')=='project_app' and request.get('op')=='finder_generation_pull':
            import generation_downloads
            s=Studio()
            key=(request.get('args') or {}).get('id')
            started=generation_downloads.enqueue(s,key,foreground=True)
            foreground=(s,started['job'],key)
            result=dict(ok=True,result=started)
        else:
            result=dispatch(request)
    except Exception as exc:result={'ok':False,'message':str(exc)}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
    if foreground:
        # Let the native bridge acknowledge the start while this same app-owned process downloads.
        os.close(sys.stdout.fileno())
        generation_downloads.run_foreground(*foreground)
