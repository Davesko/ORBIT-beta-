import unittest
import short_feedback as f
def video(dur,pct,views=200,hook=4,humor='none',caption='clean',age=100):
 return dict(status='processed',age_hours=age,views=views,engaged_views=views,average_view_percentage=pct,duration=dur,edit_traits=dict(hook_seconds=hook,caption_theme=caption),editorial=dict(humor_type=humor))
class LessonTests(unittest.TestCase):
 def test_learns_length_and_hook_from_older_uploads(self):
  vids=[video(40,55,hook=3),video(42,50,hook=4),video(70,30,hook=12),video(75,28,hook=11),video(38,9,views=3)]
  r=f.recommendation(vids)
  self.assertEqual(r['status'],'learned')
  traits={l['trait']:l for l in r['lessons']}
  self.assertEqual(traits['duration']['best'],'30–45 mp-es');self.assertIn('30-46 s',traits['duration']['instruction'])
  self.assertEqual(traits['hook']['best'],'5 mp alatti nyitású');self.assertIn('never sacrifice the story',r['instruction'])
 def test_no_lesson_from_tiny_or_similar_groups(self):
  self.assertEqual(f.recommendation([video(40,50),video(70,30)])['status'],'collecting')
  self.assertEqual(f.lessons([video(40,50),video(42,48),video(70,47),video(72,45)]),[])
if __name__=='__main__':unittest.main()
