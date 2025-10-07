import socket
import argparse

def parse_http_request(raw_request: str) -> dict:
    """
    Parses a raw HTTP request string and returns a dictionary
    with the method, path, version, and headers.
    """
    if not raw_request:
        return {}

    lines = raw_request.split('\r\n')
    
    request_line = lines[0]
    try:
        method, path, version = request_line.split(' ')
    except ValueError:
        return {} 

    headers = {}
    for line in lines[1:]:
        if line == "":
            break
        key, value = line.split(': ', 1)
        headers[key] = value

    return {
        "method": method,
        "path": path,
        "version": version,
        "headers": headers
    }

def handle_connection(client_socket: socket.socket):
    """
    Handles a single client connection: receives, parses, routes the request,
    and sends a response.
    """
    try:
        raw_request_bytes = client_socket.recv(8192)
        if not raw_request_bytes:
            return 

        raw_request = raw_request_bytes.decode('utf-8')

        request = parse_http_request(raw_request)

        if not request:
            return

        print(f"[Request] Method: {request['method']}, Path: {request['path']}")

        if request['method'] == 'GET':
            print("--- Handling GET request (placeholder) ---")
        elif request['method'] == 'POST':
            print("--- Handling POST request (placeholder) ---")
        else:
            print(f"--- Method {request['method']} not allowed ---")
            response = (
                b"HTTP/1.1 405 Method Not Allowed\r\n"
                b"Content-Length: 0\r\n"
                b"Connection: close\r\n\r\n"
            )
            client_socket.sendall(response)

    except Exception as e:
        print(f"Error handling connection: {e}")
    finally:
        client_socket.close()


def main():
    parser = argparse.ArgumentParser(description="A multi-threaded HTTP server.")
    parser.add_argument("port", type=int, default=8080, nargs='?', 
                        help="The port the server will listen on (default: 8080)")
    parser.add_argument("host", type=str, default="127.0.0.1", nargs='?',
                        help="The host address the server will bind to (default: 127.0.0.1)")
    parser.add_argument("max_threads", type=int, default=10, nargs='?',
                        help="The maximum number of threads in the pool (default: 10)")
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((args.host, args.port))
        server_socket.listen(50)
        
        print(f"HTTP Server started on http://{args.host}:{args.port}")
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