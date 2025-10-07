
# Multi-threaded HTTP Server in Python

This project is a multi-threaded HTTP server built from scratch in Python using low-level sockets. It is designed to handle multiple concurrent clients, serve static and binary files, process JSON data via POST requests, and implement key HTTP/1.1 features like persistent connections and security validations.

## Features

-   **Concurrent Architecture:** Utilizes a fixed-size thread pool to handle multiple client connections simultaneously.
-   **Configurable:** Server host, port, and thread pool size can be configured via command-line arguments.
-   **GET Request Handling:**
    -   Serves HTML files (`text/html`) for in-browser rendering.
    -   Serves binary files (`.png`, `.jpeg`, `.txt`) as downloadable attachments (`application/octet-stream`).
-   **POST Request Handling:**
    -   Accepts and processes `application/json` content.
    -   Saves posted JSON data to a uniquely named file in the `resources/uploads/` directory.
    -   Returns a `201 Created` response with the path to the new resource.
-   **HTTP/1.1 Connection Management:**
    -   Supports persistent connections (`Connection: keep-alive`).
    -   Implements a 30-second idle connection timeout.
    -   Enforces a maximum of 100 requests per connection.
-   **Security:**
    -   **Path Traversal Protection:** Prevents access to files outside the designated `resources` web root.
    -   **Host Header Validation:** Validates the `Host` header against the server's configuration, rejecting mismatched or missing headers.
-   **Robust Error Handling:** Implements proper HTTP error responses for various scenarios, including `400`, `403`, `404`, `405`, `415`, `500`, and `503`.
-   **Comprehensive Logging:** Outputs timestamped logs for server events, requests, responses, and security violations.

## Directory Structure

The server expects the following directory structure to be in place:

```

project/
├── server.py
└── resources/
├── index.html
├── sample.txt
├── logo.png
└── uploads/      \<-- For POST request uploads

````

## Requirements

-   Python 3.6+

## Usage

Run the server from the command line. You can specify the port, host, and max threads as optional arguments.

```sh
# Syntax
python server.py [port] [host] [max_threads]

# Run with defaults (127.0.0.1:8080, 10 threads)
python server.py

# Run on port 8000, accessible on the local network, with 20 threads
python server.py 8000 0.0.0.0 20
````

## Architecture & Implementation

### Concurrency Model (Thread Pool)

The server's concurrency is managed by a thread pool to avoid the overhead of creating a new thread for each request.

  - **Main Thread:** The primary thread's sole responsibility is to listen for and `accept()` incoming TCP connections. Upon accepting a new connection, it places the client socket into a thread-safe task queue.
  - **Task Queue (`queue.Queue`):** A bounded, FIFO queue holds pending client connections. If the queue is full (i.e., all worker threads are busy and the queue has reached its capacity), the server responds with `503 Service Unavailable`.
  - **Worker Threads:** A fixed number of worker threads run in the background. Each worker continuously attempts to retrieve a client socket from the task queue. The `queue.get()` call is blocking, ensuring threads sleep efficiently while idle. Once a task is retrieved, the worker is responsible for the entire lifecycle of that client's connection.

### Security Measures

  - **Path Traversal:** Protection is implemented by canonicalizing the requested file path using `os.path.abspath()`. The resulting absolute path is then validated to ensure it starts with the server's root `resources` directory path. Any request for a path that resolves outside this directory is denied with a `403 Forbidden` error.
  - **Host Header Validation:** As per the HTTP/1.1 RFC, all requests are checked for a `Host` header. Requests with a missing header are rejected with `400 Bad Request`. The header's value must also match the server's `host:port` configuration, otherwise the request is rejected with `403 Forbidden`.

### Connection Management

Persistent connections are handled within a loop inside the `handle_connection` function, which is executed by a worker thread.

  - **Keep-Alive Logic:** The decision to keep a connection open is based on the client's HTTP version and the value of the `Connection` header. The connection is closed if the client sends `Connection: close`, the request limit is reached, or an idle timeout occurs.
  - **Timeout:** Each accepted socket is configured with a 30-second timeout (`socket.settimeout(30)`). If no data is received from the client within this period, a `socket.timeout` exception is caught, and the connection is gracefully closed.

## How to Test

Use a tool like `curl` for testing.

```sh
# Test GET request for an HTML page
curl -v [http://127.0.0.1:8080/](http://127.0.0.1:8080/)

# Test GET request for a binary file (download)
curl -v [http://127.0.0.1:8080/logo.png](http://127.0.0.1:8080/logo.png) -o downloaded_logo.png

# Test successful POST request
curl -v -X POST [http://127.0.0.1:8080/upload](http://127.0.0.1:8080/upload) \
-H "Content-Type: application/json" \
-d '{"key": "value"}'

# Test Path Traversal attack (should fail with 403)
curl -v [http://127.0.0.1:8080/../server.py](http://127.0.0.1:8080/../server.py)

# Test mismatched Host header (should fail with 403)
curl -v -H "Host: example.com" [http://127.0.0.1:8080/](http://127.0.0.1:8080/)
```

## Known Limitations

  - The server does not support HTTPS (TLS/SSL).
  - The HTTP parser is basic and may not be fully robust against all forms of malformed requests.
  - The set of supported MIME types is limited.
  - The implementation is for educational purposes and is not hardened for a production environment.

