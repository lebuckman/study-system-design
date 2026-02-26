import http.server
import socketserver
import requests

# List of backend servers
backend_servers = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002"
]

# Round-robin counter
current_server = 0


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
        global current_server
        backend = backend_servers[current_server]
        print(f"Forwarding request to {backend}")
        self.forward_request(backend)
        current_server = (current_server + 1) % len(backend_servers)


PORT = 8080

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), LoadBalancerHandler) as httpd:
        print(f"Load balancer running on port {PORT}...")
        httpd.serve_forever()
