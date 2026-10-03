"""Single-host Nmap inventory with structured results and no shell execution."""
import ipaddress
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET


def target_ip(value):
    if not isinstance(value, str) or '%' in value:
        raise ValueError('IPv4 또는 IPv6 주소 하나를 입력하세요.')
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        raise ValueError('IPv4 또는 IPv6 주소 하나를 입력하세요.') from None
    if address.is_multicast or address.is_unspecified:
        raise ValueError('단일 장치의 IP를 입력하세요.')
    return str(address)


def find_nmap():
    for candidate in [shutil.which('nmap'), '/opt/homebrew/bin/nmap', '/usr/local/bin/nmap']:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def command(binary, target, output):
    target = target_ip(target)
    return [binary, *(['-6'] if ':' in target else []), '-sT', '-sV', '--version-light',
            '--top-ports', '100', '-T3', '-n', '-Pn', '--host-timeout', '120s',
            '-oX', str(output), target]


def parse_xml(path):
    root = ET.parse(path).getroot()
    hosts = []
    for host in root.findall('host'):
        ports = []
        for p in host.findall('ports/port'):
            state = p.find('state'); service = p.find('service')
            ports.append({'port': int(p.get('portid')), 'protocol': p.get('protocol'),
                          'state': state.get('state', 'unknown') if state is not None else 'unknown',
                          'service': dict(service.attrib) if service is not None else {}})
        hosts.append({'addresses': [a.get('addr') for a in host.findall('address')],
                      'ports': ports, 'timed_out': host.get('timedout') == 'true'})
    finished = root.find('runstats/finished')
    if finished is None or finished.get('exit') != 'success':
        raise ValueError('스캔이 정상 완료되지 않았습니다.')
    return hosts


class Scanner:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.state = {'status': 'idle', 'hosts': []}
        self.process = None
        self.cancelled = False

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self, target, terminal=False):
        target = target_ip(target)
        binary = find_nmap()
        if not binary:
            raise ValueError('Nmap이 없습니다. nmap.org의 macOS 설치 패키지를 먼저 설치하세요.')
        with self.lock:
            if self.state['status'] == 'running':
                raise ValueError('이미 점검 중입니다. 완료 후 다시 시작하세요.')
            scan_id = uuid.uuid4().hex
            output = self.directory / (scan_id + '.xml')
            log = self.directory / (scan_id + '.log')
            args = command(binary, target, output)
            log.write_text('$ ' + shlex.join(args) + '\n', encoding='utf-8')
            os.chmod(log, 0o600)
            self.state = {'status': 'running', 'target': target, 'hosts': [], 'command': shlex.join(args), 'id': scan_id}
            self.cancelled = False
            threading.Thread(target=self._run, args=(args, output, log), daemon=True).start()
        if terminal and sys.platform == 'darwin':
            # Terminal displays the command and Nmap output. Nmap itself runs via argv.
            shell_command = 'tail -n +1 -f ' + shlex.quote(str(log))
            script = 'tell application "Terminal"\nactivate\ndo script ' + json.dumps(shell_command) + '\nend tell'
            try:
                subprocess.run(['/usr/bin/osascript', '-e', script], capture_output=True, timeout=10, check=True)
            except (OSError, subprocess.SubprocessError):
                with self.lock:
                    self.state['notice'] = '터미널 표시를 열지 못했어요. 점검은 계속 진행됩니다.'
        return self.snapshot()

    def _run(self, args, output, log):
        try:
            with log.open('a') as stream:
                with self.lock:
                    if self.cancelled:
                        self.state['status'] = 'cancelled'
                        return
                    self.process = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT)
                    proc = self.process
                try:
                    code = proc.wait(timeout=150)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait()
                    raise ValueError('150초 제한으로 점검을 중단했어요.')
            with self.lock:
                if self.cancelled:
                    self.state['status'] = 'cancelled'
                elif code:
                    self.state.update(status='error', error='Nmap 실행 실패. 터미널 로그를 확인하세요.')
                else:
                    self.state.update(status='done', hosts=parse_xml(output))
            if output.exists():
                os.chmod(output, 0o600)
        except (OSError, ValueError, ET.ParseError) as e:
            with self.lock:
                self.state.update(status='error', error=str(e))
        finally:
            with self.lock:
                self.process = None

    def cancel(self):
        with self.lock:
            self.cancelled = True
            if self.process and self.process.poll() is None:
                self.process.terminate()
