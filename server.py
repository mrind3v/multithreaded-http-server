"""
A multi-threaded HTTP server built from scratch in Python.
This server handles GET and POST requests, serves static and binary files,
supports persistent connections (Keep-Alive), and includes basic security features.
"""

# modules for socket programming and command-line arguments.
import socket
import argparse

# modules for file system operations, date formatting, JSON, and unique IDs.
import os
from datetime import datetime
from email.utils import formatdate
import json
import time
import random

# modules for concurrency (threading and a thread-safe queue).
import threading
import queue

# modules for professional, timestamped logging.
import logging


# Setting up a global logger. All logging calls will use this format.
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# Defines the base directory for serving files, located in a 'resources' subdirectory.
RESOURCES_DIR = os.path.join(os.path.dirname(__file__), 'resources')


class ThreadPool:
    """
    Manages a pool of worker threads to handle client connections concurrently.
    """
    def __init__(self, max_threads: int, queue_size: int):
        # The task queue holds (client_socket, server_config) tuples.
        # It's bounded to a max size to prevent the server from being overwhelmed (STEP 7).
        self.tasks = queue.Queue(maxsize=queue_size)
        self.workers = []
        for i in range(max_threads):
            # Create and start each worker thread.
            # `daemon=True` ensures threads exit when the main program does.
            thread = threading.Thread(target=self._worker, name=f"Thread-{i+1}", daemon=True)
            thread.start()
            self.workers.append(thread)

    def _worker(self):
        """The main loop for each worker thread."""
        while True:
            try:
                # `self.tasks.get()` is a blocking call. The thread will sleep efficiently
                # until a task is available in the queue.
                client_socket, server_config = self.tasks.get()
                handle_connection(client_socket, server_config)
            finally:
                # Used to signal that the task is done, for queue management.
                self.tasks.task_done()

    def add_task(self, task):
        """
        Called by the main thread to add a new connection to the queue.
        `block=False` makes it non-blocking, raising `queue.Full` if the queue is saturated.
        """
        self.tasks.put(task, block=False)


def parse_http_request(raw_request: str) -> dict:
    """
    Parses a raw HTTP request string into a structured dictionary,
    separating the method, path, version, headers, and body.
    """
    if not raw_request:
        return {}
    
    # The body is separated from the headers by a double newline (\r\n\r\n).
    try:
        head, body = raw_request.split('\r\n\r\n', 1)
    except ValueError:
        head, body = raw_request, ""

    lines = head.split('\r\n')
    
    # The first line is the request line (e.g., "GET /index.html HTTP/1.1").
    try:
        method, path, version = lines[0].split(' ')
    except ValueError:
        return {}  # Malformed request line

    # Subsequent lines are headers (e.g., "Host: example.com").
    headers = {}
    for line in lines[1:]:
        key, value = line.split(': ', 1)
        headers[key] = value

    return {
        "method": method,
        "path": path,
        "version": version,
        "headers": headers,
        "body": body
    }


def get_content_type(file_path: str) -> (str, bool):
    """
    Determines the MIME type for a file and whether it should be downloaded as an attachment.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.html':
        return 'text/html; charset=utf-8', False
    elif ext in ['.txt', '.png', '.jpg', '.jpeg']:
        # Treat as a generic binary stream to trigger download.
        return 'application/octet-stream', True
    else:
        # Unsupported file type.
        return None, False


def build_http_response(status_code: int, status_message: str, headers: dict, body: bytes = b'', keep_alive: bool = False):
    """
    Constructs a complete, well-formed HTTP response as a byte string.
    """
    response_line = f"HTTP/1.1 {status_code} {status_message}\r\n"
    
    # adding standard headers required for every response.
    headers['Date'] = formatdate(timeval=None, localtime=False, usegmt=True)
    headers['Server'] = 'MyPythonHTTPServer'
    headers['Content-Length'] = str(len(body))
    
    # adding Keep-Alive headers based on the connection decision.
    if keep_alive:
        headers['Connection'] = 'keep-alive'
        headers['Keep-Alive'] = 'timeout=30, max=100'
    else:
        headers['Connection'] = 'close'
    
    header_lines = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])
    
    # combining all parts and encode to bytes for sending over the socket.
    return response_line.encode('utf-8') + header_lines.encode('utf-8') + b"\r\n" + body


def send_error_response(client_socket: socket.socket, status_code: int, status_message: str, headers: dict = None):
    """
    Builds and sends a standard HTTP error response.
    Error responses always close the connection.
    """
    if headers is None:
        headers = {}
    response = build_http_response(status_code, status_message, headers, keep_alive=False)
    client_socket.sendall(response)


def handle_get_request(client_socket: socket.socket, request: dict, keep_alive: bool):
    thread_name = threading.current_thread().name
    path = request['path']
    if path == '/':
        path = '/index.html'

    # resolving the absolute path and ensure it's within the allowed resources directory.
    file_path = os.path.abspath(os.path.join(RESOURCES_DIR, path.lstrip('/')))
    if not file_path.startswith(RESOURCES_DIR):
        logging.warning(f"[{thread_name}] SECURITY VIOLATION: Path Traversal for: {path}")
        send_error_response(client_socket, 403, "Forbidden")
        return False # Signal to close connection

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        send_error_response(client_socket, 404, "Not Found")
        return False

    content_type, is_attachment = get_content_type(file_path)
    if content_type is None:
        send_error_response(client_socket, 415, "Unsupported Media Type")
        return False

    # Read file in binary mode ('rb') to handle all file types correctly.
    with open(file_path, 'rb') as f:
        file_content = f.read()

    headers = {'Content-Type': content_type}
    if is_attachment:
        filename = os.path.basename(file_path)
        # This header tells the browser to download the file.
        headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    response = build_http_response(200, "OK", headers, file_content, keep_alive)
    client_socket.sendall(response)
    logging.info(f"[{thread_name}] Response: 200 OK ({len(file_content)} bytes)")
    return keep_alive


def handle_post_request(client_socket: socket.socket, request: dict, keep_alive: bool):
    thread_name = threading.current_thread().name
    
    # Rule: Only accept application/json.
    if request['headers'].get('Content-Type') != 'application/json':
        send_error_response(client_socket, 415, "Unsupported Media Type")
        return False

    # Rule: Ensure the body is valid JSON.
    try:
        json_data = json.loads(request['body'])
    except json.JSONDecodeError:
        send_error_response(client_socket, 400, "Bad Request")
        return False

    # Create a unique filename based on timestamp and a random ID.
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    random_id = random.randint(1000, 9999)
    filename = f"upload_{timestamp}_{random_id}.json"
    filepath = os.path.join(RESOURCES_DIR, 'uploads', filename)

    # writing the received JSON data to the file.
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=4)

    # Respond with a 201 Created status, indicating success.
    response_body = {
        "status": "success",
        "message": "File created successfully",
        "filepath": f"/uploads/{filename}"
    }
    response_body_bytes = json.dumps(response_body).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    response = build_http_response(201, "Created", headers, response_body_bytes, keep_alive)
    client_socket.sendall(response)
    logging.info(f"[{thread_name}] Response: 201 Created, saved to {filename}")
    return keep_alive


def handle_connection(client_socket: socket.socket, server_config: tuple):
    thread_name = threading.current_thread().name
    requests_handled = 0
    
    try:
        # setting a 30-second idle timeout for the connection.
        client_socket.settimeout(30)
        
        # Loop to handle multiple requests on one connection (Keep-Alive).
        while requests_handled < 100:
            try:
                raw_request_bytes = client_socket.recv(8192)
                if not raw_request_bytes:
                    break  # Client closed the connection.
                
                request = parse_http_request(raw_request_bytes.decode('utf-8'))
                if not request:
                    send_error_response(client_socket, 400, "Bad Request"); break

                connection_header = request['headers'].get('Connection', '').lower()
                http_version = request.get('version', 'HTTP/1.0')
                keep_alive = (http_version == 'HTTP/1.1' and connection_header != 'close') or \
                             (http_version == 'HTTP/1.0' and connection_header == 'keep-alive')
                
                # Host Header Security Validation 
                host_header = request['headers'].get('Host'); server_host, server_port = server_config
                expected_host = f"{server_host}:{server_port}"
                if not host_header:
                    logging.warning(f"[{thread_name}] SECURITY VIOLATION: Missing Host header.")
                    send_error_response(client_socket, 400, "Bad Request"); break
                if host_header != expected_host:
                    logging.warning(f"[{thread_name}] SECURITY VIOLATION: Mismatched Host. Got '{host_header}'.")
                    send_error_response(client_socket, 403, "Forbidden"); break

                # PDF-Compliant Logging 
                log_line = f"{request['method']} {request['path']} {request.get('version', '')}"
                logging.info(f"[{thread_name}] Request #{requests_handled+1}: {log_line}")
                logging.info(f"[{thread_name}] Host validation: {host_header}")
                
                # Routing  ---
                if request['method'] == 'GET':
                    keep_alive = handle_get_request(client_socket, request, keep_alive)
                elif request['method'] == 'POST':
                    keep_alive = handle_post_request(client_socket, request, keep_alive)
                else:
                    send_error_response(client_socket, 405, "Method Not Allowed"); keep_alive = False

                requests_handled += 1
                logging.info(f"[{thread_name}] Connection: {'keep-alive' if keep_alive else 'close'}")
                if not keep_alive:
                    break # Exit loop if client requested to close or an error occurred.

            except socket.timeout:
                logging.info(f"[{thread_name}] Connection timed out.")
                break
            except Exception as e:
                logging.error(f"[{thread_name}] Error during request loop: {e}")
                send_error_response(client_socket, 500, "Internal Server Error")
                break
    finally:
        client_socket.close()


def main():
    # Parse command-line arguments for server configuration.
    parser = argparse.ArgumentParser(description="A multi-threaded HTTP server.")
    parser.add_argument("port", type=int, default=8080, nargs='?', help="The port the server will listen on")
    parser.add_argument("host", type=str, default="127.0.0.1", nargs='?', help="The host address to bind to")
    parser.add_argument("max_threads", type=int, default=10, nargs='?', help="Maximum number of threads in the pool")
    args = parser.parse_args()

    # Initialising the thread pool with a max queue size for overload protection.
    max_queue_size = args.max_threads * 2
    thread_pool = ThreadPool(max_threads=args.max_threads, queue_size=max_queue_size)
    server_config = (args.host, args.port)

    # Setting up the main listening socket.
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
                # This is the main thread's only blocking call. It waits for new connections.
                client_socket, client_address = server_socket.accept()
                logging.info(f"[MainThread] Accepted connection from {client_address[0]}:{client_address[1]}")
                
                try:
                    # Add the new connection to the thread pool's task queue.
                    task = (client_socket, server_config)
                    thread_pool.add_task(task)
                except queue.Full:
                    # Handle server overload by rejecting the connection.
                    logging.warning(f"[MainThread] Thread pool queue is full. Rejecting connection.")
                    send_error_response(client_socket, 503, "Service Unavailable", headers={'Retry-After': '10'})
                    client_socket.close()

            except KeyboardInterrupt:
                logging.info("\nServer is shutting down.")
                break

if __name__ == "__main__":
    main()