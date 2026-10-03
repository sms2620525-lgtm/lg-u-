import asyncio
import math
import struct
import sys
import types
import unittest
from unittest.mock import patch
from phone import PhoneBridge, decode_motion, SERVICE, AUTH, MOTION

class PhoneTests(unittest.TestCase):
    def test_packets(self):
        self.assertEqual(decode_motion(struct.pack('<ff',25,-12)),(25,-12))
        for data in [b'',b'123',struct.pack('<ff',math.nan,0),struct.pack('<ff',181,0)]:
            with self.assertRaises(ValueError): decode_motion(data)
    def test_receive_and_disconnect(self):
        b=PhoneBridge();b.state['enabled']=True;b._receive(None,struct.pack('<ff',20,30))
        self.assertTrue(b.snapshot()['connected']);b.stop()
        b._receive(None,struct.pack('<ff',20,30));self.assertFalse(b.snapshot()['connected'])
    def test_validation(self):
        b=PhoneBridge()
        for pin in ['123','abcdef',123456]:
            with self.assertRaises(ValueError):b.connect('device',pin)
        with self.assertRaises(ValueError):b.connect('unknown','123456')
    def test_ble_protocol(self):
        calls=[]
        class Client:
            def __init__(self,device,**kwargs):self.is_connected=False
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def write_gatt_char(self,uuid,data,response):calls.append((uuid,data,response))
            async def start_notify(self,uuid,callback):calls.append(uuid);callback(None,struct.pack('<ff',1,2))
        b=PhoneBridge();b.state['enabled']=True
        with patch.dict(sys.modules,{'bleak':types.SimpleNamespace(BleakClient=Client)}):asyncio.run(b._connect('device','012345'))
        self.assertEqual(calls,[(AUTH,b'012345',True),MOTION]);self.assertEqual(b.state['pitch'],1)
