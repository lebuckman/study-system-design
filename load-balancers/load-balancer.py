import http.server
import socketserver
import threading
import time
import requests

# List of all backend servers (with weights)
all_servers = [
    {"url": "http://127.0.0.1:8001", "weight": 2},
    {"url": "http://127.0.0.1:8002", "weight": 1}
]

# Active pool of healthy backend servers
backend_servers = all_servers[:]

# Round-robin counter and weight tracking
current_server = 0
current_weight = 0

# Track active connections for each server
active_connections = {server["url"]: 0 for server in backend_servers}


def health_check():
    while True:
        for server in all_servers:
            try:
                response = requests.get(server["url"], timeout=2)
                if response.status_code == 200:
                    if server not in backend_servers:
                        print(
                            f"Server {server['url']} is healthy again. Adding back to pool.")
                        backend_servers.append(server)
                else:
                    if server in backend_servers:
                        print(
                            f"Server {server['url']} is unhealthy. Removing from pool.")
                        backend_servers.remove(server)
            except requests.RequestException:
                if server in backend_servers:
                    print(
                        f"Server {server['url']} is unhealthy. Removing from pool.")
                    backend_servers.remove(server)
        time.sleep(10)  # Check every 10 seconds


def get_next_server():
    global current_server, current_weight
    while True:
        server = backend_servers[current_server % len(backend_servers)]
        if current_weight < server["weight"]:
            current_weight += 1
            return server["url"]
        else:
            current_weight = 0
            current_server = (current_server + 1) % len(backend_servers)


def get_least_connections_server():
    active_urls = {server["url"] for server in backend_servers}
    filtered = {url: count for url,
                count in active_connections.items() if url in active_urls}
    return min(filtered, key=filtered.get)


class LoadBalancerHandler(http.server.BaseHTTPRequestHandler):
    def forward_request(self, backend):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else None

        # Forward the request to the backend server
        try:
            response = requests.request(
                method=self.command,
                url=f"{backend}{self.path}",
                headers=self.headers,
                data=body,
                allow_redirects=False
            )

            # Send the backend's response back to the client
            self.send_response(response.status_code)
            for header, value in response.headers.items():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(response.content)
        except requests.RequestException as e:
            self.send_error(500, f"Error forwarding request: {e}")

    def do_GET(self):
        backend = get_least_connections_server()
        active_connections[backend] += 1
        print(
            f"Forwarding request to {backend} (active connections: {active_connections[backend]})")
        self.forward_request(backend)
        active_connections[backend] -= 1

    def do_POST(self):
        self.do_GET()


PORT = 8080

if __name__ == "__main__":
    threading.Thread(target=health_check, daemon=True).start()

    with socketserver.TCPServer(("", PORT), LoadBalancerHandler) as httpd:
        print(f"Load balancer running on port {PORT}...")
        httpd.serve_forever()
