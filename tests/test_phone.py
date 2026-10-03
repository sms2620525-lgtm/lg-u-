import time
import unittest
from phone import PhoneBridge

class PhoneTests(unittest.TestCase):
    def bridge(self):
        b=PhoneBridge();b.pin='012345';b.expires=time.time()+300
        return b
    def test_pair_then_motion(self):
        b=self.bridge();code,result=b.accept('/pair',{'pin':'012345'});self.assertEqual(code,200)
        self.assertEqual(b.accept('/pair',{'pin':'012345'})[0],403)
        self.assertEqual(b.accept('/motion',{'pitch':20,'roll':-30},'Bearer '+result['token'])[0],200)
        self.assertTrue(b.snapshot()['connected'])
        self.assertEqual(b.snapshot()['pitch'],20)
    def test_unauthorized_and_invalid_motion(self):
        b=self.bridge();token=b.accept('/pair',{'pin':'012345'})[1]['token']
        self.assertEqual(b.accept('/motion',{'pitch':0,'roll':0},'wrong')[0],403)
        for value in [float('nan'),float('inf'),True,181,'1']:
            self.assertEqual(b.accept('/motion',{'pitch':value,'roll':0},'Bearer '+token)[0],400)
        self.assertEqual(b.accept('/api/scan',{})[0],404)
    def test_pair_lockout_and_expiration(self):
        b=self.bridge()
        for i in range(5): self.assertEqual(b.accept('/pair',{'pin':'000000'})[0],403)
        self.assertEqual(b.accept('/pair',{'pin':'012345'})[0],403)
        b=self.bridge();b.expires=0
        self.assertEqual(b.accept('/pair',{'pin':'012345'})[0],403)
    def test_stop_revokes(self):
        b=self.bridge();token=b.accept('/pair',{'pin':'012345'})[1]['token'];b.stop()
        self.assertEqual(b.accept('/motion',{'pitch':0,'roll':0},'Bearer '+token)[0],403)
