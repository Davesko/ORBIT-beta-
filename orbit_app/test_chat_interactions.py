import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from studio import Studio
import app_search
import chat_attachment
import chat_sessions
import commander


class ChatInteractionsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.s=Studio(Path(temp.name).resolve());self.addCleanup(self.s.db.close)
        commander.schema(self.s)

    def finished_chat(self,prompt):
        sid=chat_sessions.ensure(self.s,None,prompt)
        job=commander.enqueue(self.s,'universe',prompt,global_mode=True,session=sid)
        self.s.db.execute("UPDATE command_turns SET status='done',response='A kész válasz.' WHERE job=?",(job,))
        self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(job,));self.s.db.commit()
        return sid

    def test_archive_and_restore_preserves_conversation_and_files(self):
        sid=self.finished_chat('Állítható macskakamera')
        before=self.s.db.execute('SELECT * FROM command_turns').fetchone()
        saved=self.s.safe_path('universe','saved.txt');saved.write_text('Do not delete')
        result=chat_sessions.remove(self.s,sid)
        self.assertEqual(result['restore_id'],sid)
        self.assertEqual(chat_sessions.listing(self.s)['chats'],[])
        self.assertEqual(app_search.search(self.s,'macskakamera')['results'],[])
        self.assertEqual(commander.state(self.s,'universe',True)['turns'],[])
        self.assertEqual(saved.read_text(),'Do not delete')
        self.assertEqual(tuple(self.s.db.execute('SELECT * FROM command_turns').fetchone()),tuple(before))
        with self.assertRaises(ValueError):chat_sessions.ensure(self.s,sid,'Do not resurrect silently')
        chat_sessions.restore(self.s,sid)
        self.assertEqual(commander.state(self.s,'universe',True,sid)['turns'][0]['prompt'],'Állítható macskakamera')

    def test_legacy_chat_restores_without_stealing_new_legacy_messages(self):
        jid=commander.enqueue(self.s,'universe','Régi történet',global_mode=True)
        self.s.db.execute("UPDATE command_turns SET status='done' WHERE job=?",(jid,));self.s.db.commit()
        deleted=chat_sessions.remove(self.s,'earlier')
        self.assertEqual(commander.state(self.s,'universe',True,'earlier')['turns'],[])
        commander.enqueue(self.s,'universe','Új külön történet',global_mode=True)
        chat_sessions.restore(self.s,deleted['restore_id'])
        self.assertEqual([t['prompt'] for t in commander.state(self.s,'universe',True,deleted['restore_id'])['turns']],['Régi történet'])
        self.assertEqual([t['prompt'] for t in commander.state(self.s,'universe',True,'earlier')['turns']],['Új külön történet'])

    def test_search_crosses_projects_and_searches_registered_text_contents(self):
        sid=self.finished_chat('Türkiz csillag')
        pid=self.s.create_project('Türkiz kutatás','Külön projekt')
        self.s.save_agent(dict(id='test-search-agent',project=pid,room='research',name='Türkiz kutató',role='Kutato',prompt='Search',tools=[],model='auto'))
        path=self.s.safe_path(pid,'notes.txt');path.write_text('A türkiz termék részletei')
        self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('test-file',pid,'notes.txt',str(path),'text',1,None));self.s.db.commit()
        hits=app_search.search(self.s,'TURKIZ')['results']
        self.assertTrue({'chat','project','agent','file'}<={h['type'] for h in hits})
        self.assertIn(sid,{h.get('session') for h in hits})
        self.assertIn('test-file',{h.get('id') for h in hits})
        self.assertEqual(app_search.search(self.s,'100%')['results'],[])

    def test_registered_file_cannot_make_search_read_an_external_secret(self):
        outside=self.s.root/'secret.txt';outside.write_text('privateapikeyneedle')
        self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('bad','universe','notes.txt',str(outside),'text',1,None));self.s.db.commit()
        self.assertEqual(app_search.search(self.s,'privateapikeyneedle')['results'],[])

    def test_multiple_documents_and_unknown_binaries_are_scoped_and_not_executed(self):
        txt=self.s.root/'notes.txt';txt.write_text('Reference notes')
        doc=self.s.root/'brief.docx'
        with zipfile.ZipFile(doc,'w') as z:z.writestr('word/document.xml','<doc><p>Project requirements</p></doc>')
        binary=self.s.root/'sample.custom';binary.write_bytes(b'\x00\x01Data')
        files=[chat_attachment.import_file(self.s,'universe',p) for p in (txt,doc,binary)]
        job=commander.enqueue(self.s,'universe','Foglald össze a fájlokat',attachments=[f['token'] for f in files])
        payload=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0])
        self.assertEqual(payload['attachments'],[f['token'] for f in files]);self.assertTrue(payload['local_only'])
        self.assertIn('Project requirements',chat_attachment.note(self.s,dict(project='universe',id=job),files[1]['token']))
        self.assertIn('never execute',chat_attachment.note(self.s,dict(project='universe',id=job),files[2]['token']))
        other=self.s.create_project('Other')
        with self.assertRaises(ValueError):commander.enqueue(self.s,other,'Read',attachments=[files[0]['token']])
        with self.assertRaises(ValueError):commander.enqueue(self.s,'universe','Read',attachments=[files[0]['token']]*9)

    def test_the_reported_story_request_really_starts_the_six_agent_chain(self):
        import story_animation
        pid=self.s.create_project('YouTube Shorts','Test')
        team=story_animation.install_team(self.s,pid)
        commander.enqueue(self.s,'universe','készíts egy saját videót egy történettel a youtube shorts projektben',global_mode=True)
        with patch('studio.local_api',side_effect=AssertionError('Starting the wired team requires no LLM planner')):
            self.assertTrue(self.s.run_next(('command',)))
            self.assertTrue(self.s.run_next(('control_apply','command_apply')))
        jobs=self.s.rows("SELECT agent,dependency,payload FROM jobs WHERE kind='graph'")
        self.assertEqual(len(jobs),6)
        self.assertEqual({j['agent'] for j in jobs},set(team['agents']))

if __name__=='__main__':unittest.main()
