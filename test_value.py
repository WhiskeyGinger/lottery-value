import unittest, datetime as dt, json, tempfile, math
from pathlib import Path
import value as V

class Odds(unittest.TestCase):
    def test_match_official_charts(self):
        pb=V.GAMES['powerball']; mm=V.GAMES['megamillions']
        self.assertEqual(round(1/V.tier_odds(69,26,5,1)),292_201_338); self.assertEqual(round(1/V.tier_odds(70,24,5,1)),290_472_336)
        self.assertAlmostEqual(1/V.tier_odds(69,26,0,1),38.32,places=2); self.assertAlmostEqual(1/V.tier_odds(70,24,3,0),607.17,places=1)
    def test_powerball_small_prizes_before_tax_match_known_32_cents(self):
        v=V.ticket_value('powerball',0,0,0,tickets=0)
        untaxed=sum(V.tier_odds(69,26,w,b)*p for (w,b),p in V.GAMES['powerball']['tiers']); self.assertAlmostEqual(untaxed,0.32,places=2)
        self.assertLess(v['small_prizes'],untaxed)
    def test_multiplier_mean_is_three(self): self.assertAlmostEqual(sum(k*p for k,p in V.MM_MULTIPLIER.items()),3.0)

class Value(unittest.TestCase):
    def test_bigger_jackpot_more_value_but_more_splitting(self):
        a=V.ticket_value('powerball',300e6,140e6); b=V.ticket_value('powerball',1.5e9,700e6)
        self.assertGreater(b['value'],a['value']); self.assertLess(b['share'],a['share'])
    def test_share_factor(self):
        self.assertAlmostEqual(V.share_factor(0,1e-8),1.0); self.assertAlmostEqual(V.share_factor(1e8,1e-8),(1-math.exp(-1))/1)
    def test_state_tax_lowers_value(self):
        self.assertLess(V.ticket_value('powerball',850e6,400e6,0.0495)['value'],V.ticket_value('powerball',850e6,400e6,0)['value'])
    def test_money_parsing(self):
        self.assertEqual(V.money('$850 Million'),850e6); self.assertEqual(V.money('$1.2 Billion'),1.2e9); self.assertEqual(V.money(4e8),4e8)

NOW=dt.datetime(2026,11,28,14,13,tzinfo=dt.timezone.utc)          # Sat 8:13 AM CST
TONIGHT=dt.datetime(2026,11,29,3,59,tzinfo=dt.timezone.utc)         # Sat 9:59 PM CST
class Run(unittest.TestCase):
    def setUp(self): self.d=tempfile.TemporaryDirectory(); self.p=Path(self.d.name,'s.json'); self.sent=[]
    def tearDown(self): self.d.cleanup()
    def send(self,h,m): self.sent.append(m); return True
    def f(self): return {'powerball':lambda:(850e6,400e6,TONIGHT),'megamillions':lambda:(500e6,230e6,TONIGHT+dt.timedelta(days=2))}
    def test_posts_only_todays_drawing_once(self):
        r=V.run('H',NOW,self.f(),self.send,self.p,0); self.assertEqual(len(r['posted']),1); self.assertIn('Powerball — $850M',self.sent[0]['embeds'][0]['title'])
        V.run('H',NOW+dt.timedelta(hours=2),self.f(),self.send,self.p,0); self.assertEqual(len(self.sent),1)
    def test_message_text(self):
        V.run('H',NOW,self.f(),self.send,self.p,0); e=self.sent[0]['embeds'][0]
        self.assertIn('Sat Nov 28, 9:59 PM CST',e['title']); self.assertIn('A $2 ticket is really worth **$',e['description']); self.assertIn('📉',e['description'])
        self.assertNotIn('content',self.sent[0])
    def test_alarm_when_worth_more_than_price(self):
        f={'powerball':lambda:(9e9,4.5e9,TONIGHT)}
        V.run('H',NOW,f,self.send,self.p,0); self.assertIn('🚨',self.sent[0]['content'])
    def test_feed_error_reported(self):
        def boom(): raise OSError()
        r=V.run('H',NOW,{'powerball':boom},self.send,self.p,0); self.assertEqual(r['errors'],['powerball: OSError']); self.assertEqual(self.sent,[])
    def test_sample_labelled(self):
        self.assertTrue(all(e['title'].startswith('🧪 SAMPLE') for e in V.sample(NOW)['embeds']))

if __name__=='__main__': unittest.main()
