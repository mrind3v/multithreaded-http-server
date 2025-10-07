import socket
import argparse

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
                print(f"Connection from {client_address[0]}:{client_address[1]}")
                
                client_socket.close()

            except KeyboardInterrupt:
                print("\nServer is shutting down.")
                break

if __name__ == "__main__":
    main()