import unittest
from youtube import upload_status_text
from youtube_runtime import verified_upload_fields

class YouTubeProcessingTests(unittest.TestCase):
 def test_upload_completion_does_not_claim_processing_or_shorts_classification(self):
  receipt=verified_upload_fields(dict(status=dict(privacyStatus='public',uploadStatus='uploaded'),processingDetails=dict(processingStatus='processing')))
  self.assertIn('még feldolgozza',upload_status_text(receipt))
  self.assertNotIn('shorts_status',receipt)
  self.assertNotIn('format',receipt)
 def test_server_processing_success_and_failure_are_separate(self):
  result=verified_upload_fields(dict(status=dict(uploadStatus='processed'),processingDetails=dict(processingStatus='succeeded'),contentDetails=dict(duration='PT1M36S')))
  self.assertEqual(result['youtube_duration'],'PT1M36S')
  self.assertEqual(upload_status_text(result),'YouTube-feldolgozás kész')
  result=verified_upload_fields(dict(status=dict(uploadStatus='rejected',rejectionReason='copyright')))
  self.assertEqual(result['processing_failure'],'copyright')
  self.assertIn('hiba',upload_status_text(result))
 def test_hd_still_processing_takes_precedence_over_upload_processed(self):
  self.assertIn('még feldolgozza',upload_status_text(dict(processing='processed',processing_status='processing')))
