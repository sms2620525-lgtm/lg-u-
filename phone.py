"""Bluetooth LE phone motion client. No LAN listener or internet transport."""
import asyncio
import math
import re
import struct
import threading
import time
from http.server import ThreadingHTTPServer
from socketserver import TCPServer

SERVICE = '78e7a600-7d35-4aa1-8b5f-565445c90001'
AUTH = '78e7a600-7d35-4aa1-8b5f-565445c90002'
MOTION = '78e7a600-7d35-4aa1-8b5f-565445c90003'

class NumericHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def decode_motion(data):
    if len(data) != 8:
        raise ValueError('Invalid motion packet')
    pitch, roll = struct.unpack('<ff', data)
    if any(not math.isfinite(v) or abs(v) > 180 for v in (pitch, roll)):
        raise ValueError('Invalid motion angles')
    return pitch, roll


class PhoneBridge:
    def __init__(self):
        self.lock = threading.RLock()
        self.loop = None
        self.future = None
        self.devices = {}
        self.state = {'enabled': False, 'connected': False, 'status': 'idle', 'pitch': 0, 'roll': 0, 'updated': 0}

    def snapshot(self):
        with self.lock:
            data = dict(self.state)
            data['connected'] = data['connected'] and time.monotonic()-data['updated'] < 2
            return data

    def _loop(self):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            threading.Thread(target=self.loop.run_forever, daemon=True).start()
        return self.loop

    def enable(self):
        with self.lock:
            if self.future and not self.future.done():
                raise ValueError('진행 중인 연결을 끊은 뒤 검색하세요.')
            self.state.update(enabled=True, connected=False, status='scanning', error='')
            self.future = asyncio.run_coroutine_threadsafe(self._discover(), self._loop())
        return self.snapshot()

    async def _discover(self):
        try:
            from bleak import BleakScanner
            devices = await BleakScanner.discover(timeout=7, service_uuids=[SERVICE])
            with self.lock:
                self.devices = {d.address: d for d in devices}
                self.state.update(status='ready', devices=[{'id': d.address, 'name': d.name or 'JARVIS Motion'} for d in devices])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            with self.lock:
                self.state.update(status='error', error='Bluetooth 검색 실패: '+str(e))

    def connect(self, address, pin):
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9]{6}', pin):
            raise ValueError('휴대폰에 표시된 6자리 코드를 입력하세요.')
        if not isinstance(address, str):
            raise ValueError('검색 목록에서 휴대폰을 선택하세요.')
        with self.lock:
            if address not in self.devices:
                raise ValueError('휴대폰을 먼저 검색하고 선택하세요.')
            if self.future and not self.future.done():
                raise ValueError('검색 또는 연결이 진행 중입니다.')
            self.state.update(enabled=True, connected=False, status='connecting', error='')
            self.future = asyncio.run_coroutine_threadsafe(self._connect(self.devices[address], pin), self._loop())
        return self.snapshot()

    async def _connect(self, device, pin):
        try:
            from bleak import BleakClient
            async with BleakClient(device, timeout=20) as client:
                await client.write_gatt_char(AUTH, pin.encode('ascii'), response=True)
                await client.start_notify(MOTION, self._receive)
                with self.lock:
                    self.state.update(status='streaming')
                while client.is_connected:
                    await asyncio.sleep(.2)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            with self.lock:
                self.state.update(status='error', error='Bluetooth 연결 실패: '+str(e))
        finally:
            with self.lock:
                self.state['connected'] = False
                if self.state['status'] != 'error':
                    self.state['status'] = 'idle'

    def _receive(self, characteristic, data):
        try:
            pitch, roll = decode_motion(data)
        except ValueError:
            return
        with self.lock:
            if self.state['enabled']:
                self.state.update(connected=True, pitch=pitch, roll=roll, updated=time.monotonic())

    def stop(self):
        with self.lock:
            if self.future:
                self.future.cancel()
            self.state.update(enabled=False, connected=False, status='idle', updated=0)
