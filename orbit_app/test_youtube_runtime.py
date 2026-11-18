import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock

class YouTubeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:import googleapiclient
        except ImportError:raise unittest.SkipTest('Google adapter tests use the isolated media runtime')
        import youtube_runtime
        cls.module=youtube_runtime
    def test_revoked_login_marks_channel_disconnected(self):
        # A revoked Google token used to surface as a vague "network error" while the channel still
        # showed as connected, so every later upload failed the same way.
        from google.auth.exceptions import RefreshError
        import json
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);base=home/'Library/Application Support/Orbit/integrations/youtube/universe';base.mkdir(parents=True)
            creds=MagicMock(valid=False,refresh_token='r');creds.refresh.side_effect=RefreshError('invalid_grant')
            keychain=MagicMock();keychain.get_password.return_value='{"scopes":[]}'
            with patch.object(self.module,'store',return_value=keychain),patch('google.oauth2.credentials.Credentials.from_authorized_user_info',return_value=creds),patch.object(Path,'home',return_value=home):
                with self.assertRaises(ValueError) as ctx:self.module.credentials('universe')
            self.assertIn('lejárt',str(ctx.exception))
            self.assertFalse(json.loads((base/'status.json').read_text())['connected'])
            keychain.set_password.assert_not_called()
    def test_private_resumable_upload_contract_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'video.mp4';path.write_bytes(b'local synthetic test video')
            operation=MagicMock();operation.next_chunk.return_value=(None,{'id':'verified-test-id','status':{'privacyStatus':'private','uploadStatus':'uploaded'}})
            service=MagicMock();service.videos.return_value.insert.return_value=operation
            service.videos.return_value.list.return_value.execute.return_value={'items':[]}
            request=dict(source=str(path),title='Test',description='Synthetic test',made_for_kids=False,progress=str(Path(folder)/'progress.json'))
            with patch.object(self.module,'credentials',return_value=MagicMock()),patch('googleapiclient.discovery.build',return_value=service),patch('google_auth_httplib2.AuthorizedHttp'):
                result=self.module.upload(Path(folder),'universe',request)
            self.assertEqual(result,'verified-test-id');kwargs=service.videos.return_value.insert.call_args.kwargs
            self.assertEqual(kwargs['body']['status']['privacyStatus'],'private')
            self.assertIs(kwargs['body']['status']['selfDeclaredMadeForKids'],False)
            self.assertTrue(kwargs['media_body'].resumable())
    def test_public_request_and_actual_visibility_receipt(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'video.mp4';path.write_bytes(b'local synthetic test video')
            operation=MagicMock();operation.next_chunk.return_value=(None,{'id':'verified-test-id','status':{'privacyStatus':'public'}})
            service=MagicMock();service.videos.return_value.insert.return_value=operation
            service.videos.return_value.list.return_value.execute.return_value={'items':[{'status':{'privacyStatus':'public','uploadStatus':'processed'}}]}
            progress=Path(folder)/'progress.json'
            request=dict(source=str(path),title='Test',description='Synthetic test',made_for_kids=False,privacy='public',progress=str(progress))
            with patch.object(self.module,'credentials',return_value=MagicMock()),patch('googleapiclient.discovery.build',return_value=service),patch('google_auth_httplib2.AuthorizedHttp') as transport:
                self.module.upload(Path(folder),'universe',request)
            self.assertNotIn(308,transport.call_args.kwargs['http'].redirect_codes)
            self.assertIn(302,transport.call_args.kwargs['http'].redirect_codes)
            self.assertEqual(service.videos.return_value.insert.call_args.kwargs['body']['status']['privacyStatus'],'public')
            self.assertEqual(json.loads(progress.read_text())['privacy'],'public')
    def test_google_flow_pkce_and_mac_keychain_backend(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow=InstalledAppFlow.from_client_config({'installed':dict(client_id='test.apps.googleusercontent.com',client_secret='test',auth_uri='https://accounts.google.com/o/oauth2/auth',token_uri='https://oauth2.googleapis.com/token',redirect_uris=['http://localhost'])},self.module.SCOPES,autogenerate_code_verifier=True)
        flow.redirect_uri='http://127.0.0.1:12345/callback'
        url,state=flow.authorization_url(state='fixed-test-state',access_type='offline')
        self.assertIn('code_challenge=',url);self.assertIn('code_challenge_method=S256',url);self.assertEqual(state,'fixed-test-state')
        from keyring.backends.macOS import Keyring
        self.assertIsInstance(self.module.store().get_keyring(),Keyring)

if __name__=='__main__':unittest.main()

class MetricsRuntimeTests(unittest.TestCase):
 def setUp(self):
  try:import googleapiclient
  except ImportError:self.skipTest('Google adapter tests use isolated runtime')
  import youtube_runtime
  self.module=youtube_runtime
 def test_old_grant_reads_counts_without_inventing_retention(self):
  creds=MagicMock();creds.has_scopes.return_value=False;service=MagicMock()
  service.videos.return_value.list.return_value.execute.return_value={'items':[dict(id='abcdefghijk',snippet=dict(publishedAt='2026-10-19T12:00:00Z'),status=dict(uploadStatus='processed'),statistics=dict(viewCount='1000',likeCount='15'))]}
  with patch.object(self.module,'credentials',return_value=creds),patch('googleapiclient.discovery.build',return_value=service):result=self.module.metrics('project',dict(videos=[dict(id='abcdefghijk',duration=40,topic='test')]))
  self.assertEqual(result['analytics_status'],'authorization_required');self.assertEqual(result['videos'][0]['views'],1000);self.assertIsNone(result['videos'][0]['engaged_views'])
 def test_analytics_column_mapping_and_missing_rows(self):
  creds=MagicMock();creds.has_scopes.return_value=True;service=MagicMock();analytics=MagicMock()
  service.videos.return_value.list.return_value.execute.return_value={'items':[dict(id='abcdefghijk',snippet=dict(publishedAt='2026-10-19T12:00:00Z'),status=dict(uploadStatus='processed'),statistics={})]}
  analytics.reports.return_value.query.return_value.execute.return_value={'columnHeaders':[dict(name='video'),dict(name='engagedViews'),dict(name='averageViewPercentage')],'rows':[['abcdefghijk',150,78.5]]}
  with patch.object(self.module,'credentials',return_value=creds),patch('googleapiclient.discovery.build',side_effect=[service,analytics]):result=self.module.metrics('project',dict(videos=[dict(id='abcdefghijk')]))
  self.assertEqual(result['videos'][0]['average_view_percentage'],78.5);self.assertEqual(result['videos'][0]['engaged_views'],150);self.assertIsNone(result['videos'][0]['average_view_duration'])

class ExtendedAnalyticsTests(unittest.TestCase):
 def test_missing_retention_does_not_erase_available_counts(self):
  try:import googleapiclient
  except ImportError:self.skipTest('Run in media runtime')
  import youtube_runtime
  creds=MagicMock();creds.has_scopes.return_value=True;service=MagicMock();analytics=MagicMock()
  service.videos.return_value.list.return_value.execute.return_value={'items':[dict(id='abcdefghijk',snippet=dict(publishedAt='2026-10-19T12:00:00Z',title='Real title'),status=dict(uploadStatus='processed'),statistics=dict(viewCount='100'))]}
  analytics.reports.return_value.query.return_value.execute.side_effect=[dict(columnHeaders=[dict(name='video'),dict(name='engagedViews')],rows=[['abcdefghijk',75]])]+[ValueError('Report unavailable')]*4
  with patch.object(youtube_runtime,'credentials',return_value=creds),patch('googleapiclient.discovery.build',side_effect=[service,analytics]):r=youtube_runtime.metrics('p',dict(videos=[dict(id='abcdefghijk')]))
  self.assertEqual(r['videos'][0]['views'],100);self.assertEqual(r['videos'][0]['engaged_views'],75);self.assertEqual(r['analytics_status'],'available');self.assertIn('elapsedVideoTimeRatio',r['report_errors'])

class ChannelTotalsTests(unittest.TestCase):
 def test_channel_total_is_available_without_any_orbit_uploads(self):
  try:import googleapiclient
  except ImportError:self.skipTest('Run in media runtime')
  import youtube_runtime
  service=MagicMock();service.channels.return_value.list.return_value.execute.return_value=dict(items=[dict(id='channel-1',snippet=dict(title='Actual channel'),statistics=dict(viewCount='4567',videoCount='12'))])
  with patch.object(youtube_runtime,'credentials',return_value=MagicMock()),patch('googleapiclient.discovery.build',return_value=service):r=youtube_runtime.metrics('p',dict(videos=[]))
  self.assertEqual(r['channel']['views'],4567);self.assertEqual(r['channel']['video_count'],12);self.assertEqual(r['videos'],[])

class FreshSourceMetadataTests(unittest.TestCase):
 def setUp(self):
  try:import googleapiclient
  except ImportError:self.skipTest('Run in media runtime')
 def test_metadata_date_is_from_actual_video_not_search_index(self):
  import youtube_runtime as runtime
  service=MagicMock();service.videos.return_value.list.return_value.execute.return_value=dict(items=[dict(id='abcdefghijk',snippet=dict(title='Actual title',publishedAt='2025-08-19T22:30:01Z'),contentDetails=dict(duration='PT1M30S'))])
  with patch.object(runtime,'credentials',return_value=MagicMock()),patch('googleapiclient.discovery.build',return_value=service),patch('google_auth_httplib2.AuthorizedHttp'):
   result=runtime.source_metadata('project',dict(ids=['abcdefghijk','bad']))
  self.assertEqual(service.videos.return_value.list.call_args.kwargs['id'],'abcdefghijk');self.assertEqual(result['videos'][0]['published_at'],'2025-08-19T22:30:01Z');self.assertEqual(result['videos'][0]['duration'],90)
 def test_search_requires_fresh_actual_video_date_and_event_match(self):
  import youtube_runtime as runtime
  from test_source_policy import report
  import datetime
  service=MagicMock();service.search.return_value.list.return_value.execute.return_value=dict(items=[dict(id=dict(videoId='abcdefghijk'))])
  now=datetime.datetime.now(datetime.timezone.utc).isoformat()
  def entry(id,title,date):return dict(id=id,snippet=dict(title=title,publishedAt=date),contentDetails=dict(duration='PT1M30S'),statistics={})
  service.videos.return_value.list.return_value.execute.return_value=dict(items=[entry('abcdefghijk','Minecraft copper golem update launches',now),entry('oldoldoldab','Minecraft copper golem update launches','2025-08-19T22:30:01Z'),entry('otherothera','Unrelated basketball event',now)])
  with patch.object(runtime,'credentials',return_value=MagicMock()),patch('googleapiclient.discovery.build',return_value=service),patch('google_auth_httplib2.AuthorizedHttp'):
   result=runtime.trend_samples('project',dict(topics=['Minecraft update'],news={'Minecraft update':[report()]}))
  self.assertIn('publishedAfter',service.search.return_value.list.call_args.kwargs);self.assertEqual([v['id'] for v in result['samples']['Minecraft update']['videos']],['abcdefghijk'])

class LongerNewsSourceTests(unittest.TestCase):
 def test_discovery_accepts_longer_report_without_relaxing_date_or_topic(self):
  import youtube_runtime as runtime,datetime
  from test_source_policy import report
  service=MagicMock();service.search.return_value.list.return_value.execute.return_value=dict(items=[dict(id=dict(videoId='abcdefghijk'))])
  now=datetime.datetime.now(datetime.timezone.utc).isoformat()
  service.videos.return_value.list.return_value.execute.return_value=dict(items=[dict(id='abcdefghijk',snippet=dict(title='Minecraft copper golem update launches',publishedAt=now),contentDetails=dict(duration='PT8M'),statistics={})])
  with patch.object(runtime,'credentials',return_value=MagicMock()),patch('googleapiclient.discovery.build',return_value=service),patch('google_auth_httplib2.AuthorizedHttp'):
   result=runtime.trend_samples('project',dict(topics=['Minecraft update'],news={'Minecraft update':[report()]},max_video_seconds=1800))
  self.assertEqual(service.search.return_value.list.call_args.kwargs['videoDuration'],'any');self.assertEqual(result['samples']['Minecraft update']['videos'][0]['duration'],480)
