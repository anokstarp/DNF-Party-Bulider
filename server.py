# server.py
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import os

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 메인 페이지 서빙
        if self.path == '/' or self.path == '/index.html':
            self.path = '/index.html'
            return self.serve_file()
        # 다른 경로는 파일 서버 기본 동작
        return self.serve_file()

    def do_POST(self):
        # /run 경로로 POST 요청이 오면 스크립트 실행
        if self.path == '/run':
            script_path = os.path.join(os.path.dirname(__file__), 'script.py')
            try:
                result = subprocess.run(
                    ['python3', script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=True,
                    text=True
                )
                output = result.stdout
            except subprocess.CalledProcessError as e:
                output = f"Error:\n{e.output}"
            # 응답: 실행 결과를 포함한 HTML
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            with open('index.html', 'r', encoding='utf-8') as f:
                page = f.read()
            # 출력 결과를 <pre> 태그에 넣어 삽입
            page = page.replace('<!-- OUTPUT_PLACEHOLDER -->', f'<pre>{output}</pre>')
            self.wfile.write(page.encode('utf-8'))
        else:
            self.send_error(404)

    def serve_file(self):
        # 파일 서빙 기본 메서드
        try:
            file_path = self.path.lstrip('/')
            if not file_path:
                file_path = 'index.html'
            with open(file_path, 'rb') as f:
                self.send_response(200)
                content_type = 'text/html' if file_path.endswith('.html') else 'application/octet-stream'
                self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            self.send_error(404)

if __name__ == '__main__':
    port = 8000
    server = HTTPServer(('0.0.0.0', port), RequestHandler)
    print(f"Serving on port {port}...")
    server.serve_forever()
