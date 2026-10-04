"""Loopback-only Supabase PKCE return listener. Never logs authorization codes."""
import html
import urllib.parse
from http.server import BaseHTTPRequestHandler
from phone import NumericHTTPServer


def callback_server(cloud):
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            if self.headers.get('Host') not in ('localhost:3000','127.0.0.1:3000'):
                self.send_error(403)
                return
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path != '/' or len(self.path)>8192:
                self.send_error(404)
                return
            query = urllib.parse.parse_qs(parsed.query)
            code = query.get('code',[])
            status = 200
            message = '인증이 완료됐어요. JARVIS 앱으로 돌아가세요.'
            try:
                if len(code)!=1 or 'error' in query:
                    raise ValueError('인증 링크가 만료됐거나 이미 사용됐어요. 앱에서 새 메일을 요청하세요.')
                cloud.complete(code[0])
            except ValueError as e:
                status,message = 400,str(e)
                cloud.error = message
            body = ('<!doctype html><meta charset="utf-8"><title>JARVIS 인증</title>'
                    '<script>history.replaceState(null,"","/")</script>'
                    '<body style="background:#061019;color:#b7f6ff;font:20px system-ui;padding:60px">'
                    '<h1>JARVIS</h1><p>'+html.escape(message)+'</p></body>').encode()
            self.send_response(status)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Frame-Options','DENY')
            self.end_headers()
            self.wfile.write(body)
    return NumericHTTPServer(('127.0.0.1',3000),Callback)
