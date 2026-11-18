import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import revenue,connections
class RevenueTests(unittest.TestCase):
 def test_sums_charges_minus_refunds_per_currency_with_paging(self):
  pages=[dict(has_more=True,data=[dict(id='t1',type='charge',currency='eur',amount=4900,fee=170,net=4730),dict(id='t2',type='payout',currency='eur',amount=-9999,fee=0,net=-9999)]),
         dict(has_more=False,data=[dict(id='t3',type='refund',currency='eur',amount=-4900,fee=0,net=-4900),dict(id='t4',type='charge',currency='huf',amount=1290000,fee=40000,net=1250000)])]
  with patch('connections.http',side_effect=lambda *a,**k:pages.pop(0)) as h:
   r=revenue.fetch(now=1_800_000_000)
  self.assertEqual(r['payments'],2);self.assertEqual(r['totals']['EUR']['net'],-1.7);self.assertEqual(r['totals']['HUF']['net'],12500.0)
  self.assertIn('starting_after=t2',h.call_args_list[1][0][1])
  self.assertIn('12 500,00 HUF',revenue.label(r))
 def test_only_restricted_keys_are_accepted(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'rk_'):connections.save(dict(provider='stripe',key='sk_live_'+'x'*30),d)
   connections.save(dict(provider='stripe',key='rk_live_'+'x'*30,enabled=True),d)
   self.assertTrue(connections.secret('stripe',d).startswith('rk_live_'))
 def test_silent_without_stripe(self):
  with patch('connections.secret',return_value=''):self.assertIsNone(revenue.refresh(None))
if __name__=='__main__':unittest.main()
