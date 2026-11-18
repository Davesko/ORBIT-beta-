import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import stream_watch as sw
import stream_watch_runtime as rt

def quiet(start,count,n=6,users=5):
 return [dict(t=start+i*5,n=n+(i%3),users=users,funny=0,hype=0,shock=0,fail=0,clip=0) for i in range(count)]

class DetectTests(unittest.TestCase):
 cfg=sw.clean(dict(sw.DEFAULT))
 def test_peak_is_measured_against_the_channels_own_normal(self):
  b=quiet(1000,120)                       # ten quiet minutes
  for i,n in enumerate((14,40,55,38,12)):b.append(dict(t=1600+i*5,n=n,users=n-2,funny=n//2,hype=0,shock=0,fail=0,clip=2 if i==2 else 0))
  b+=quiet(1625,12)
  found=sw.detect(b,self.cfg)
  self.assertEqual(len(found),1);m=found[0]
  self.assertEqual(m['kind'],'funny');self.assertLessEqual(m['at'],1600);self.assertGreaterEqual(m['at'],1585);self.assertGreater(m['end'],1615);self.assertEqual(m['clip_calls'],2)
 def test_a_big_chat_does_not_flag_everything_and_a_quiet_one_needs_people(self):
  self.assertEqual(sw.detect(quiet(0,200,n=300,users=200),self.cfg),[])
  b=quiet(0,120,n=0,users=0)+[dict(t=600,n=9,users=2,funny=0,hype=0,shock=0,fail=0,clip=0)]+quiet(605,10,n=0,users=0)
  self.assertEqual(sw.detect(b,self.cfg),[])          # two people spamming
 def test_a_peak_still_rising_waits_for_its_end(self):
  b=quiet(1000,120)+[dict(t=1600,n=60,users=50,funny=0,hype=30,shock=0,fail=0,clip=0)]
  self.assertEqual(sw.detect(b,self.cfg,now=1606),[])
  self.assertEqual(len(sw.detect(b+quiet(1605,8),self.cfg,now=1650)),1)
 def test_window_keeps_cause_before_and_reaction_after(self):
  start,length=sw.window(dict(at=5000,end=5020),1000,self.cfg)
  self.assertEqual(start,5000-1000-sw.LEAD-self.cfg['before']);self.assertEqual(length,20+self.cfg['before']+self.cfg['after'])
 def test_launch_gate_and_game_filter(self):
  cfg=dict(self.cfg,enabled=True);live=dict(channels=dict(xqc=dict(live=True,game='Grand Theft Auto VI'),lirik=dict(live=True,game='Fortnite'),kaicenat=dict(live=False)))
  import calendar
  before=calendar.timegm(time.strptime('2026-11-18','%Y-%m-%d'));after=calendar.timegm(time.strptime('2026-11-19','%Y-%m-%d'))
  self.assertEqual(sw.watching(cfg,live,before-3600),[]);self.assertEqual(sw.watching(cfg,live,after),['xqc'])
  self.assertEqual(set(sw.watching(dict(cfg,game=''),live,before-3600)),{'xqc','lirik'})

class RuntimeTests(unittest.TestCase):
 def test_chat_line_is_parsed_and_counted_without_names(self):
  line='@badges=;tmi-sent-ts=1794692093268;user-id=1 :bob!bob@bob.tmi.twitch.tv PRIVMSG #xqc :LULW OMEGALUL clip it'
  ch,user,text,at=rt.parse(line);self.assertEqual((ch,user,at),('xqc','bob',1794692093.268));self.assertEqual(set(rt.classify(text)),{'funny','clip'})
  c=rt.Counter()
  for _ in range(5):c.add('xqc','bob','KEKW',100)
  c.add('xqc','amy','W',101)
  rows=c.closed(120);self.assertEqual(rows,[('xqc',100,3,2,2,1,0,0,0)])     # a spammer counts twice, people are a number
  self.assertIsNone(rt.parse(':tmi.twitch.tv 001 justinfan1 :Welcome'))

class WatchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name));self.addCleanup(self.s.db.close)
  sw._last.clear();self.pid=sw.ensure(self.s)
 def test_project_has_its_own_app_and_starts_switched_off(self):
  import project_apps
  self.assertEqual(project_apps.describe(self.s,self.pid)['app'],'watch')
  snap=project_apps.dispatch(self.s,self.pid,'watch_snapshot',dict(project=self.pid))['result']
  self.assertFalse(snap['settings']['enabled']);self.assertEqual(snap['moments'],[])
 def test_tick_records_a_moment_once_and_queues_its_download(self):
  sw.save(self.s,self.pid,dict(enabled=True,game='',channels=['xqc','https://twitch.tv/Lirik']))
  self.assertEqual(sw.settings(self.s,self.pid)['channels'],['xqc','lirik'])
  now=time.time();base=sw.folder(self.s,self.pid)
  (base/'live.json').write_text(json.dumps(dict(checked=now,channels=[dict(channel='xqc',live=True,started=now-7200,vod_started=now-7200,vod='2928767125',game='GTA')])))
  t0=int(now//5)*5-900;b=quiet(t0,150)
  for i,n in enumerate((40,70,45)):b.append(dict(t=t0+750+i*5,n=n,users=n-5,funny=0,hype=n//2,shock=0,fail=0,clip=0))
  b+=quiet(t0+765,20)
  db=rt.database(base);db.executemany('INSERT OR REPLACE INTO buckets VALUES(?,?,?,?,?,?,?,?,?)',[('xqc',x['t'],x['n'],x['users'],x['funny'],x['hype'],x['shock'],x['fail'],x['clip']) for x in b]);db.commit();db.close()
  (base/'listener.heartbeat').touch()
  with patch.object(sw,'spawn') as spawn:
   sw.tick(self.s,now);sw._last.clear();sw.tick(self.s,now+11)
   spawn.assert_not_called()
  rows=self.s.rows('SELECT * FROM stream_moments')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['kind'],'hype');self.assertEqual(rows[0]['status'],'fetching')
  self.assertAlmostEqual(rows[0]['start'],rows[0]['at']-(now-7200)-sw.LEAD-sw.DEFAULT['before'],delta=1)
  job=self.s.rows("SELECT payload FROM jobs WHERE kind='assist'")[0];self.assertEqual(json.loads(job['payload'])['task'],'watch_fetch')
  self.assertEqual(json.loads((base/'listen.json').read_text())['channels'],['xqc'])
 def test_master_pause_and_switch_off_stop_listening(self):
  sw.save(self.s,self.pid,dict(enabled=True,game=''));base=sw.folder(self.s,self.pid)
  (base/'live.json').write_text(json.dumps(dict(checked=time.time(),channels=[dict(channel='xqc',live=True,started=1)])))
  import autonomy
  with patch.object(sw,'spawn') as spawn:
   sw.tick(self.s);self.assertTrue(spawn.called)
   autonomy.set_paused(self.s,True);sw._last.clear();sw.tick(self.s)
  self.assertEqual(json.loads((base/'listen.json').read_text())['updated'],0)
  self.assertIsNone(rt.wanted(base))
  self.assertTrue(any(e['id']=='stream_watch:'+self.pid for e in autonomy.entries(self.s)))
 def test_fetched_clip_is_credited_and_edited_as_a_stream_clip(self):
  path=self.s.safe_path(self.pid,'sources/moments/x.mp4');path.parent.mkdir(parents=True);path.write_bytes(b'x')
  path.with_suffix('.source.json').write_text(json.dumps(dict(origin='stream_watch',channel='xqc',url='https://www.twitch.tv/videos/1?t=5s',title='T')))
  import raw_footage
  with patch.object(raw_footage,'probe_duration',return_value=40.0):
   src=raw_footage.sources(self.s,self.pid,['sources/moments/x.mp4'])[0]
  self.assertEqual((src['metadata']['channel'],src['metadata']['origin']),('xqc','stream_watch'))
  self.assertEqual(sw.campaign(dict(source=src)),dict(kind='gta6_stream',platform='twitch'));self.assertEqual(sw.campaign(dict(source=dict(metadata=dict(origin='owner_footage')))),{})

if __name__=='__main__':unittest.main()


class TitleTest(unittest.TestCase):
    def test_title_has_game_and_streamer(self):
        import stream_watch as w
        for title, channel in [('caseoh_ goes insane #GTA6', 'caseoh_'), ('Wild chase', 'yt:ishowspeed'), ('x' * 300, 'xqc')]:
            out = w.streamer_title(title, channel)
            self.assertIn('GTA6', out)
            self.assertLessEqual(len(out), 90)
        self.assertTrue(w.streamer_title('Wild chase', 'yt:ishowspeed').startswith('IShowSpeed | '))

    def test_auto_post_is_off_by_default(self):
        import stream_watch as w
        self.assertFalse(w.clean({})['auto_post'])
        self.assertGreaterEqual(w.clean({})['min_score'], 15)



class OtherGameTitleTest(unittest.TestCase):
    def test_another_game_is_never_sold_as_gta6(self):
        import stream_watch as w
        self.assertEqual(w.streamer_title("xQC's Hammer or Compass?", 'xqc', 'The Legend of Zelda: Ocarina of Time'), 'xQc | Hammer or Compass?')
        self.assertTrue(w.streamer_title('Wild', 'xqc', 'Grand Theft Auto VI').endswith('| GTA6'))


class BestFirstTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from studio import Studio
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Studio(Path(self.temp.name))
        self.addCleanup(self.s.db.close)
        self.pid = sw.ensure(self.s)
        self.cfg = sw.settings(self.s, self.pid)

    def moment(self, mid, score, status='found'):
        self.s.db.execute("INSERT INTO stream_moments(id,project,channel,vod,at,start,duration,score,kind,detail,status,file,created,game) VALUES(?,?,'xqc','123456789',?,100,30,?,'funny','{}',?,?,?,'Grand Theft Auto VI')",
                          (mid, self.pid, time.time() - 3000, score, status, 'f.mp4' if status == 'ready' else None, time.time()))
        self.s.db.commit()

    def test_strongest_ready_moment_is_made_first_and_weak_ones_never(self):
        for mid, sc in (('a', 30), ('b', 60), ('c', 10)):
            self.moment(mid, sc, 'ready')
        made = []
        with patch.object(sw, 'produce', side_effect=lambda s, m: made.append(m)), patch.object(sw, 'production_active', return_value=False):
            sw.advance(self.s, self.pid, self.cfg, dict(channels={}), time.time())
        self.assertEqual(made, ['b'])
        self.s.db.execute("DELETE FROM stream_moments WHERE id IN ('a','b')")
        self.s.db.commit()
        made.clear()
        with patch.object(sw, 'produce', side_effect=lambda s, m: made.append(m)), patch.object(sw, 'production_active', return_value=False):
            sw.advance(self.s, self.pid, self.cfg, dict(channels={}), time.time())
        self.assertEqual(made, [])

    def test_strongest_found_moment_is_downloaded_first_and_only_strong_ones(self):
        for mid, sc in (('a', 30), ('b', 80), ('c', 5)):
            self.moment(mid, sc)
        got = []
        with patch.object(sw, 'fetch', side_effect=lambda s, m: got.append(m)), patch.object(sw, 'production_active', return_value=True):
            sw.advance(self.s, self.pid, self.cfg, dict(channels={}), time.time())
        self.assertEqual(got, ['b'])

    def test_silent_chat_burst_does_not_explode_the_score(self):
        b = quiet(0, 130, n=0, users=0) + [dict(t=650 + i * 5, n=24, users=20, funny=8, hype=0, shock=0, fail=0, clip=0) for i in range(4)] + quiet(670, 14, n=0, users=0)
        found = sw.detect(b, sw.clean(dict(sw.DEFAULT)))
        self.assertEqual(len(found), 1)
        self.assertLess(found[0]['score'], 45)


class TwitchSegmentTests(unittest.TestCase):
    def test_only_the_segments_holding_the_window_are_chosen(self):
        import re
        text = '#EXTM3U\n#EXT-X-MAP:URI="init-0.mp4"\n' + ''.join('#EXTINF:10.000,\n%d.mp4\n' % i for i in range(30))
        start, duration = 95.0, 25.0
        at, chosen = 0.0, []
        for length, name in re.findall(r'#EXTINF:([\d.]+),[^\n]*\n([^#\s][^\n]*)', text):
            if at + float(length) > start and at < start + duration:
                chosen.append(name)
            at += float(length)
        self.assertEqual(chosen, ['9.mp4', '10.mp4', '11.mp4'])


class AudienceTests(unittest.TestCase):
    def test_bigger_audience_ranks_higher_and_unknown_is_neutral(self):
        self.assertGreater(sw.rank(30, 200000), sw.rank(30, 2000))
        self.assertGreater(sw.rank(30, 2000), sw.rank(30, 100))
        self.assertAlmostEqual(sw.audience_factor(None), sw.audience_factor(1000), 2)
        self.assertGreater(sw.rank(25, 150000), sw.rank(40, 300))      # a huge stream's good moment beats a small stream's better one


class TightCutTests(unittest.TestCase):
    def track(self, db, words=(), duration=70.0, rise=None):
        segs = [dict(start=w[0], end=w[1], text='x', words=[dict(word='x', start=w[0], end=w[1])]) for w in words]
        return dict(source=dict(duration=duration, metadata=dict(rise=rise)), transcript=dict(segments=segs, audio_context=dict(loudness=dict(step=0.5, db=db))))

    def test_short_opens_just_before_the_reaction_and_stays_within_bounds(self):
        import gta6
        db = [-40.0] * 140
        for i in range(30, 38):          # a loud reaction at 15-19 s
            db[i] = -12.0
        cut = gta6.tight_cut([self.track(db, words=[(12.3, 12.6), (14.6, 15.0), (22.0, 22.4)], rise=13)], dict(max_seconds=59, min_seconds=12, target_seconds=35))
        shot = cut['shots'][0]
        self.assertTrue(11.0 <= shot['start'] <= 14.0)                  # about 2.5 s before the reaction's onset (14 s)
        self.assertTrue(22 <= cut['duration'] <= 40)
        self.assertEqual(cut['selection'], 'tight_stream_moment')

    def test_no_loudness_falls_back_to_the_whole_clip(self):
        import gta6
        track = self.track([], duration=50.0)
        track['transcript']['audio_context'] = {}
        self.assertIsNone(gta6.tight_cut([track], dict(max_seconds=59, min_seconds=12, target_seconds=35)))
        cut = gta6.stream_cut([track], dict(max_seconds=59, min_seconds=12, target_seconds=35), 'twitch')
        self.assertEqual(cut['selection'], 'whole_stream_clip')
