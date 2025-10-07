import socket
import argparse
import os
from datetime import datetime
from email.utils import formatdate

RESOURCES_DIR = os.path.join(os.path.dirname(__file__), 'resources')

def parse_http_request(raw_request: str) -> dict:
    if not raw_request:
        return {}
    lines = raw_request.split('\r\n')
    try:
        method, path, version = lines[0].split(' ')
    except ValueError:
        return {}
    headers = {}
    for line in lines[1:]:
        if line == "":
            break
        key, value = line.split(': ', 1)
        headers[key] = value
    return {"method": method, "path": path, "version": version, "headers": headers}

def get_content_type(file_path: str) -> (str, bool):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.html':
        return 'text/html; charset=utf-8', False
    elif ext in ['.txt', '.png', '.jpg', '.jpeg']:
        return 'application/octet-stream', True
    else:
        return None, False 

def build_http_response(status_code: int, status_message: str, headers: dict, body: bytes = b''):
    """Constructs a full HTTP response."""
    response_line = f"HTTP/1.1 {status_code} {status_message}\r\n"
    
    headers['Date'] = formatdate(timeval=None, localtime=False, usegmt=True)
    headers['Server'] = 'MyPythonHTTPServer'
    headers['Content-Length'] = str(len(body))
    headers['Connection'] = 'close' 
    
    header_lines = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])
    
    return response_line.encode('utf-8') + header_lines.encode('utf-8') + b"\r\n" + body

def send_error_response(client_socket: socket.socket, status_code: int, status_message: str):
    response = build_http_response(status_code, status_message, {})
    client_socket.sendall(response)

def handle_get_request(client_socket: socket.socket, request: dict):
    """Handles a GET request by serving a file."""
    path = request['path']
    if path == '/':
        path = '/index.html' 

    file_path = os.path.abspath(os.path.join(RESOURCES_DIR, path.lstrip('/')))
    if not file_path.startswith(RESOURCES_DIR):
        send_error_response(client_socket, 403, "Forbidden")
        return

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        send_error_response(client_socket, 404, "Not Found")
        return

    content_type, is_attachment = get_content_type(file_path)
    if content_type is None:
        send_error_response(client_socket, 415, "Unsupported Media Type")
        return

    with open(file_path, 'rb') as f:
        file_content = f.read()

    headers = {'Content-Type': content_type}
    if is_attachment:
        filename = os.path.basename(file_path)
        headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    response = build_http_response(200, "OK", headers, file_content)
    client_socket.sendall(response)
    print(f"--- Responded 200 OK for {path} ({len(file_content)} bytes) ---")

def handle_connection(client_socket: socket.socket):
    try:
        raw_request_bytes = client_socket.recv(8192)
        if not raw_request_bytes: return
        raw_request = raw_request_bytes.decode('utf-8')
        request = parse_http_request(raw_request)
        if not request: return
        
        print(f"[Request] Method: {request['method']}, Path: {request['path']}")
        
        if request['method'] == 'GET':
            handle_get_request(client_socket, request)
        elif request['method'] == 'POST':
            print("--- Handling POST request (placeholder) ---")
            send_error_response(client_socket, 501, "Not Implemented") 
        else:
            send_error_response(client_socket, 405, "Method Not Allowed")

    except Exception as e:
        print(f"Error handling connection: {e}")
    finally:
        client_socket.close()

def main():
    parser = argparse.ArgumentParser(description="A multi-threaded HTTP server.")
    parser.add_argument("port", type=int, default=8080, nargs='?', help="The port the server will listen on (default: 8080)")
    parser.add_argument("host", type=str, default="127.0.0.1", nargs='?', help="The host address the server will bind to (default: 127.0.0.1)")
    parser.add_argument("max_threads", type=int, default=10, nargs='?', help="The maximum number of threads in the pool (default: 10)")
    args = parser.parse_args()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((args.host, args.port))
        server_socket.listen(50)
        print(f"HTTP Server started on http://{args.host}:{args.port}")
        print(f"Serving files from '{RESOURCES_DIR}' directory")
        print(f"Press Ctrl+C to stop the server")
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                print(f"\nAccepted connection from {client_address[0]}:{client_address[1]}")
                handle_connection(client_socket)
            except KeyboardInterrupt:
                print("\nServer is shutting down.")
                break

if __name__ == "__main__":
    main()