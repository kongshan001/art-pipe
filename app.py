#!/usr/bin/env python3
"""ArtPipe MVP - AI-Powered 2D Game Character Asset Pipeline"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import sys

class ArtPipeHandler(SimpleHTTPRequestHandler):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
    
    def do_GET(self):
        if self.path == '/' or self.path == '':
            self.path = '/templates/index.html'
        elif self.path == '/api/info':
            self.send_json({
                'name': 'ArtPipe MVP',
                'version': '0.1.0',
                'description': 'AI-Powered 2D Game Character Asset Generation Pipeline',
                'endpoints': {
                    'GET /': 'Web UI',
                    'GET /api/info': 'API Info',
                    'POST /api/generate': 'Generate Character',
                }
            })
            return
        return super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/generate':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
            self.send_json({
                'status': 'ok',
                'message': 'Client-side generation in MVP',
                'received': data
            })
        else:
            self.send_error(404)
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())
    
    def log_message(self, fmt, *args):
        print("[ArtPipe] " + str(args[0]))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(('0.0.0.0', port), ArtPipeHandler)
    print("ArtPipe MVP v0.1.0 | http://localhost:" + str(port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArtPipe stopped.")
        server.server_close()

if __name__ == '__main__':
    main()
