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
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

RESOURCES_DIR = os.path.join(os.path.dirname(__file__), 'resources')

class ThreadPool:
    def __init__(self, max_threads: int, queue_size: int):
        self.tasks = queue.Queue(maxsize=queue_size)
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
        self.tasks.put(task, block=False)

.

def build_http_response(status_code: int, status_message: str, headers: dict, body: bytes = b'', keep_alive: bool = False):
    response_line = f"HTTP/1.1 {status_code} {status_message}\r\n"
    headers['Date'] = formatdate(timeval=None, localtime=False, usegmt=True)
    headers['Server'] = 'MyPythonHTTPServer'
    headers['Content-Length'] = str(len(body))
    if keep_alive:
        headers['Connection'] = 'keep-alive'
        headers['Keep-Alive'] = 'timeout=30, max=100'
    else:
        headers['Connection'] = 'close'
    header_lines = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])
    return response_line.encode('utf-8') + header_lines.encode('utf-8') + b"\r\n" + body

def send_error_response(client_socket: socket.socket, status_code: int, status_message: str, headers: dict = None):
    if headers is None:
        headers = {}
    response = build_http_response(status_code, status_message, headers, keep_alive=False)
    client_socket.sendall(response)


def handle_connection(client_socket: socket.socket, server_config: tuple):
    thread_name = threading.current_thread().name
    requests_handled = 0
    try:
        client_socket.settimeout(30)
        while requests_handled < 100:
            try:
                raw_request_bytes = client_socket.recv(8192)
                if not raw_request_bytes: break
                
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
                if not host_header:
                    logging.warning(f"[{thread_name}] SECURITY VIOLATION: Missing Host header.")
                    send_error_response(client_socket, 400, "Bad Request"); break
                if host_header != expected_host:
                    logging.warning(f"[{thread_name}] SECURITY VIOLATION: Mismatched Host. Got '{host_header}', expected '{expected_host}'.")
                    send_error_response(client_socket, 403, "Forbidden"); break
                
                log_line_1 = f"{request['method']} {request['path']} {request['version']}"
                logging.info(f"[{thread_name}] Request: {log_line_1}")
                logging.info(f"[{thread_name}] Host validation: {host_header}")
                
                if request['method'] == 'GET':
                    keep_alive = handle_get_request(client_socket, request, keep_alive)
                
                requests_handled += 1
                logging.info(f"[{thread_name}] Connection: {'keep-alive' if keep_alive else 'close'}")
                if not keep_alive: break

            except socket.timeout:
                logging.info(f"[{thread_name}] Connection timed out. Closing.")
                break
            except Exception as e:
                logging.error(f"[{thread_name}] Error during request loop: {e}")
                send_error_response(client_socket, 500, "Internal Server Error")
                break
    finally:
        client_socket.close()

def main():
    parser = argparse.ArgumentParser(description="A multi-threaded HTTP server.")
    parser.add_argument("port", type=int, default=8080, nargs='?', help="The port the server will listen on")
    parser.add_argument("host", type=str, default="127.0.0.1", nargs='?', help="The host address to bind to")
    parser.add_argument("max_threads", type=int, default=10, nargs='?', help="Maximum number of threads in the pool")
    args = parser.parse_args()

    max_queue_size = args.max_threads * 2
    thread_pool = ThreadPool(max_threads=args.max_threads, queue_size=max_queue_size)
    server_config = (args.host, args.port)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(server_config)
        server_socket.listen(50)
        
        logging.info(f"HTTP Server started on http://{server_config[0]}:{server_config[1]}")
        logging.info(f"Thread pool size: {args.max_threads}")
        logging.info(f"Serving files from '{RESOURCES_DIR}' directory")
        logging.info("Press Ctrl+C to stop the server")

        while True:
            try:
                client_socket, client_address = server_socket.accept()
                logging.info(f"[MainThread] Accepted connection from {client_address[0]}:{client_address[1]}")
                
                try:
                    task = (client_socket, server_config)
                    thread_pool.add_task(task)
                except queue.Full:
                    logging.warning(f"[MainThread] Warning: Thread pool saturated, queuing connection rejected.")
                    send_error_response(client_socket, 503, "Service Unavailable", headers={'Retry-After': '10'})
                    client_socket.close()

            except KeyboardInterrupt:
                logging.info("\nServer is shutting down.")
                break

if __name__ == "__main__":

    main()