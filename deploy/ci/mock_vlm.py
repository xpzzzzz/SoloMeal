"""Closed CI-only synthetic response server. Never use as a real model provider."""
import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Request bodies contain private images; do not log them.

    def do_POST(self):
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size < 8 * 1024 * 1024:
            self.send_error(413)
            return
        payload = json.loads(self.rfile.read(size))
        url = payload['messages'][1]['content'][1]['image_url']['url']
        image = base64.b64decode(url.split(',', 1)[1], validate=True)
        if b'M5:failed' in image:
            self.send_response(503)
            self.end_headers()
            return
        result = {'purchased_on': None, 'items': [{'name': 'Rice', 'quantity':
            '999' if b'M5:conflict' in image else '500', 'unit': 'g', 'amount': '3.00', 'uncertain': True}]}
        body = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}],
                           'usage': {'prompt_tokens': 12, 'completion_tokens': 7, 'total_tokens': 19}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTTPServer(('0.0.0.0', 8010), Handler).serve_forever()
