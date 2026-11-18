import math,unittest
import strategy_lab as L
def rows(n=300,trend=.004):
 out=[];p=100.0
 for i in range(n):
  o=p;p=p*(1+trend+.02*math.sin(i/5));out.append(dict(t=i*86400000,o=o,h=max(o,p)*1.01,l=min(o,p)*.99,c=p))
 return out
class StrategyLabTests(unittest.TestCase):
 def spec(self,**kw):return dict(dict(coin='SOL',interval='1d',rules=dict(type='sma_cross',fast=5,slow=20),stop_loss_pct=5,take_profit_pct=20),**kw)
 def test_validation_rejects_bad_rules(self):
  for bad in (dict(coin='SO L'),dict(rules=dict(type='magic')),dict(rules=dict(type='sma_cross',fast=30,slow=10)),dict(stop_loss_pct=0)):
   with self.assertRaises(ValueError):L.validate(self.spec(**bad))
 def test_backtest_is_deterministic_and_reports_out_of_sample(self):
  a=L.backtest(self.spec(),rows());b=L.backtest(self.spec(),rows())
  self.assertEqual(a['full'],b['full']);self.assertIn(a['verdict'],('promising','weak'));self.assertGreater(a['full']['trades'],0)
  self.assertIn('return_pct',a['out_of_sample']);self.assertIn('nem befektetési tanács',a['note'])
 def test_fees_reduce_returns_and_all_rule_types_run(self):
  cheap=L.backtest(self.spec(fee_pct=0),rows())['full']['return_pct'];dear=L.backtest(self.spec(fee_pct=1),rows())['full']['return_pct']
  self.assertGreater(cheap,dear)
  for r in (dict(type='rsi_reversion',period=14,buy=30,sell=70),dict(type='breakout',lookback=20)):L.backtest(self.spec(rules=r,side='long_short'),rows())
 def test_forward_test_uses_only_new_bars(self):
  data=rows();r=L.forward(self.spec(),data[250]['t']/1000,data)
  self.assertEqual(r['bars'],50);self.assertEqual(r['virtual_capital'],1000)
  self.assertEqual(L.forward(self.spec(),data[-1]['t']/1000+86400,data)['status'],'waiting')
 def test_unit_economics(self):
  e=L.economics(dict(price=40,product_cost=10,shipping_cost=5,ad_cost_per_sale=10));self.assertEqual(e['verdict'],'viable')
  self.assertEqual(L.economics(dict(price=20,product_cost=15,shipping_cost=5,ad_cost_per_sale=10))['verdict'],'loss')
if __name__=='__main__':unittest.main()
