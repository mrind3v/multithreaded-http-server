import socket
import argparse
import os
from datetime import datetime
from email.utils import formatdate
import json
import time
import random
import threading
import queue

RESOURCES_DIR = os.path.join(os.path.dirname(__file__), 'resources')

class ThreadPool:
    def __init__(self, max_threads: int):
        self.tasks = queue.Queue()
        self.workers = []
        for i in range(max_threads):
            thread = threading.Thread(target=self._worker, name=f"Thread-{i+1}", daemon=True)
            thread.start()
            self.workers.append(thread)
    def _worker(self):
        while True:
            try:
                client_socket, server_config = self.tasks.get()
                handle_connection(client_socket, server_config)
            finally:
                self.tasks.task_done()
    def add_task(self, task):
        self.tasks.put(task)


def build_http_response(status_code: int, status_message: str, headers: dict, body: bytes = b'', keep_alive: bool = False):
    response_line = f"HTTP/1.1 {status_code} {status_message}\r\n"
    headers['Date'] = formatdate(timeval=None, localtime=False, usegmt=True)
    headers['Server'] = 'MyPythonHTTPServer'
    headers['Content-Length'] = str(len(body))
    
    if keep_alive:
        headers['Connection'] = 'keep-alive'
        headers['Keep-Alive'] = 'timeout=30, max=100' #
    else:
        headers['Connection'] = 'close'
    
    header_lines = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])
    return response_line.encode('utf-8') + header_lines.encode('utf-8') + b"\r\n" + body

def send_error_response(client_socket: socket.socket, status_code: int, status_message: str):
    response = build_http_response(status_code, status_message, {}, keep_alive=False)
    client_socket.sendall(response)

def handle_get_request(client_socket: socket.socket, request: dict, keep_alive: bool):
    path = request['path']; thread_name = threading.current_thread().name
    if path == '/': path = '/index.html'
    file_path = os.path.abspath(os.path.join(RESOURCES_DIR, path.lstrip('/')))
    if not file_path.startswith(RESOURCES_DIR):
        print(f"[{thread_name}] SECURITY VIOLATION: Path Traversal attempt for: {path}")
        send_error_response(client_socket, 403, "Forbidden"); return False
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        send_error_response(client_socket, 404, "Not Found"); return False
    content_type, is_attachment = get_content_type(file_path)
    if content_type is None:
        send_error_response(client_socket, 415, "Unsupported Media Type"); return False
    with open(file_path, 'rb') as f: file_content = f.read()
    headers = {'Content-Type': content_type}
    if is_attachment:
        filename = os.path.basename(file_path)
        headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    response = build_http_response(200, "OK", headers, file_content, keep_alive)
    client_socket.sendall(response)
    print(f"[{thread_name}] Responded 200 OK for {path} ({len(file_content)} bytes)")
    return keep_alive

def handle_post_request(client_socket: socket.socket, request: dict, keep_alive: bool):
    thread_name = threading.current_thread().name
    if request['headers'].get('Content-Type') != 'application/json':
        send_error_response(client_socket, 415, "Unsupported Media Type"); return False
    try: json_data = json.loads(request['body'])
    except json.JSONDecodeError:
        send_error_response(client_socket, 400, "Bad Request"); return False
    timestamp = time.strftime('%Y%m%d_%H%M%S'); random_id = random.randint(1000, 9999)
    filename = f"upload_{timestamp}_{random_id}.json"
    filepath = os.path.join(RESOURCES_DIR, 'uploads', filename)
    with open(filepath, 'w', encoding='utf-8') as f: json.dump(json_data, f, indent=4)
    response_body = {"status": "success", "message": "File created successfully", "filepath": f"/uploads/{filename}"}
    response_body_bytes = json.dumps(response_body).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    response = build_http_response(201, "Created", headers, response_body_bytes, keep_alive)
    client_socket.sendall(response)
    print(f"[{thread_name}] Responded 201 Created, saved to {filename}")
    return keep_alive


def handle_connection(client_socket: socket.socket, server_config: tuple):
    thread_name = threading.current_thread().name
    requests_handled = 0
    
    try:
        client_socket.settimeout(30) 
        
        while requests_handled < 100: 
            try:
                raw_request_bytes = client_socket.recv(8192)
                if not raw_request_bytes:
                    break 
                
                raw_request = raw_request_bytes.decode('utf-8')
                request = parse_http_request(raw_request)
                if not request:
                    send_error_response(client_socket, 400, "Bad Request"); break

                connection_header = request['headers'].get('Connection', '').lower()
                http_version = request.get('version', 'HTTP/1.0')

                keep_alive = (http_version == 'HTTP/1.1' and connection_header != 'close') or \
                             (http_version == 'HTTP/1.0' and connection_header == 'keep-alive')

                host_header = request['headers'].get('Host'); server_host, server_port = server_config
                expected_host = f"{server_host}:{server_port}"
                if not host_header: send_error_response(client_socket, 400, "Bad Request"); break
                if host_header != expected_host: send_error_response(client_socket, 403, "Forbidden"); break

                print(f"[{thread_name}] Request #{requests_handled+1}: {request['method']} {request['path']}")

                if request['method'] == 'GET':
                    keep_alive = handle_get_request(client_socket, request, keep_alive)
                elif request['method'] == 'POST':
                    keep_alive = handle_post_request(client_socket, request, keep_alive)
                else:
                    send_error_response(client_socket, 405, "Method Not Allowed"); keep_alive = False

                requests_handled += 1
                if not keep_alive:
                    break #

            except socket.timeout:
                print(f"[{thread_name}] Connection timed out. Closing.")
                break
            except Exception as e:
                print(f"[{thread_name}] Error during request loop: {e}")
                send_error_response(client_socket, 500, "Internal Server Error")
                break
    finally:
        print(f"[{thread_name}] Closing connection after {requests_handled} requests.")
        client_socket.close()

def parse_http_request(raw_request: str) -> dict:
    if not raw_request: return {}
    try: head, body = raw_request.split('\r\n\r\n', 1)
    except ValueError: head, body = raw_request, ""
    lines = head.split('\r\n')
    try: method, path, version = lines[0].split(' ')
    except ValueError: return {}
    headers = {};
    for line in lines[1:]:
        key, value = line.split(': ', 1)
        headers[key] = value
    return {"method": method, "path": path, "version": version, "headers": headers, "body": body}
def main():
    parser = argparse.ArgumentParser(description="A multi-threaded HTTP server.")
    parser.add_argument("port", type=int, default=8080, nargs='?', help="The port the server will listen on (default: 8080)")
    parser.add_argument("host", type=str, default="127.0.0.1", nargs='?', help="The host address the server will bind to (default: 127.0.0.1)")
    parser.add_argument("max_threads", type=int, default=10, nargs='?', help="The maximum number of threads in the pool (default: 10)")
    args = parser.parse_args()
    thread_pool = ThreadPool(max_threads=args.max_threads)
    server_config = (args.host, args.port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(server_config)
        server_socket.listen(50)
        print(f"HTTP Server started on http://{server_config[0]}:{server_config[1]}")
        print(f"Thread pool size: {args.max_threads}")
        print("Press Ctrl+C to stop the server")
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                print(f"\n[MainThread] Accepted connection from {client_address[0]}:{client_address[1]}")
                task = (client_socket, server_config)
                thread_pool.add_task(task)
            except KeyboardInterrupt:
                print("\nServer is shutting down.")
                break
if __name__ == "__main__":
    main()