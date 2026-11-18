import datetime
import unittest
from zoneinfo import ZoneInfo
from autonomous import next_slot,validate_plan

ZONE=ZoneInfo('Europe/Budapest')
def ts(value):return datetime.datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()
class PlanTests(unittest.TestCase):
    def setUp(self):self.plan=dict(start_date='2026-10-19',end_date='2026-10-30',weekdays=[0,1,2,3,4],from_time='09:00',to_time='17:00')
    def test_future_start_and_daily_window(self):
        self.assertEqual(next_slot(ts('2026-10-18T12:00'),self.plan),ts('2026-10-19T09:00'))
        self.assertEqual(next_slot(ts('2026-10-19T12:00'),self.plan),ts('2026-10-19T12:00'))
        self.assertEqual(next_slot(ts('2026-10-19T17:00'),self.plan),ts('2026-10-20T09:00'))
    def test_weekend_and_dst_transition(self):
        self.assertEqual(next_slot(ts('2026-10-23T18:00'),self.plan),ts('2026-10-26T09:00'))
    def test_expired_plan(self):self.assertIsNone(next_slot(ts('2026-10-30T17:00'),self.plan))
    def test_invalid_plan(self):
        for change in [dict(weekdays=[]),dict(weekdays=[True]),dict(from_time='18:00'),dict(end_date='2026-10-01'),dict(to_time='bad')]:
            with self.assertRaises(ValueError):validate_plan(dict(self.plan,**change))
    def test_legacy_always_on(self):self.assertEqual(next_slot(123456,{}),123456)
if __name__=='__main__':unittest.main()
