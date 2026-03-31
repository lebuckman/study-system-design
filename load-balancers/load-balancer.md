# Building a Load Balancer

Build a working HTTP load balancer, implementing weighted round robin, least connections, health checks with server recovery, and structured logging.

Based on the article [Build your own Load Balancer](https://www.valentindush.com/blog/loadbalancer) by Valentin Dushime, with several modifications. Note the domain for this article may have expired (as of March 2026).

```
Client Request (port 8080)
        │
        ▼
  LoadBalancerHandler         ← receives & forwards requests
        │
        ▼
  Pick a backend server       ← weighted round robin OR least connections
        │
        ▼
  Forward to backend          ← transparent proxy
        │
        ▼
  Return response to client

  [Background thread]
  Health check every 10s      ← removes/re-adds servers automatically
```

## ⚙️ Configuration

At the top of `load-balancer.py`, there are several possible configs:

```python
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load balancing algorithm and server configuration
ALGORITHM = "least_connections"  # "round_robin" or "least_connections"
PORT = 8080


# List of all backend servers (with weights)
all_servers = [
    {"url": "http://127.0.0.1:8001", "weight": 2},
    {"url": "http://127.0.0.1:8002", "weight": 1}
]
```

While you can update the logging output, weight of servers, or the ports, `ALGORITHM` is the only change needed to swap strategies (weighted round robin or least connections).

## ⚡ Getting Started

**Step 1. Start two backend servers** (in separate terminal windows)

```bash
# Make sure you are in the right directory
cd load-balancers

# Terminal 1
python3 -m http.server 8001

# Terminal 2
python3 -m http.server 8002
```

These use Python's built-in HTTP server to simulate real backends. You should see `Serving HTTP on :: port 800X` in each window.

**Step 2. Start the load balancer**

```bash
# Terminal 3
python3 load-balancer.py
```

**Step 3. Send some requests**

Visit `http://127.0.0.1:8080` in your browser and refresh several times. Watch the terminal output to see requests being distributed.

> [!note]
> This binds to `127.0.0.1` (localhost) — only your own machine can reach it. In production you'd bind to `0.0.0.0` to accept external traffic.

## 📍 Code Walkthrough

### Backend Server Lists

```python
# All known servers — never modified
all_servers = [
    {"url": "http://127.0.0.1:8001", "weight": 2},
    {"url": "http://127.0.0.1:8002", "weight": 1}
]

# Active pool — modified by the health checker
backend_servers = all_servers[:]
```

`all_servers` is the permanent source of truth. `backend_servers` is the live active pool that shrinks and grows as servers go up and down.

Each server has a `url` and a `weight`. Weight only applies during `round_robin` — server `8001` (weight 2) gets twice as many requests as `8002` (weight 1).

### Active Connections Tracker

A dictionary initialized at startup that tracks in-flight requests per server. Starts at 0 for all servers. Used by the `least_connections` algorithm.

```python
active_connections = {server["url"]: 0 for server in backend_servers}
```

### Health Check

Runs in a background daemon thread, pinging every server every 10 seconds.

```python
def health_check():
    while True:
		# iterate the full list, not just active
        for server in all_servers:
            try:
                response = requests.get(server["url"], timeout=2)
                if response.status_code == 200:
                    if server not in backend_servers:
                        logging.info(f"Server {server['url']} is healthy again. Adding back to pool.")
                        backend_servers.append(server)
                else:
                    if server in backend_servers:
                        logging.warning(f"Server {server['url']} is unhealthy. Removing from pool.")
                        backend_servers.remove(server)
            except requests.RequestException:
                if server in backend_servers:
                    logging.warning(f"Server {server['url']} is unhealthy. Removing from pool.")
                    backend_servers.remove(server)
        time.sleep(10)
```

> [!note]
> The original article incorrectly modified `backend_servers` while iterating over it, causing items to be skipped. By iterating over the never-changing `all_servers` and using `remove()` on `backend_servers`, this bug is fixed.
>
> Also, the original article never re-added recovered servers after being removed by the health checker. Additional detection checks were added to implement this.

---

### Weighted Round Robin

Uses `current_weight` to count how many times the current server has been used. Once it hits the server's weight limit, it advances to the next server and resets the counter.

With weights `2` and `1`, the distribution is: `8001 → 8001 → 8002 → 8001 → 8001 → 8002 ...`

```python
current_server = 0
current_weight = 0

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
```

> [!note]
> The original article had an `IndexError` bug when indexing a shrinking list. To account for this, `% len(backend_servers)` is added when indexing.

---

### Least Connections

Picks whichever server currently has the fewest active connections. Filters to only servers in the current active pool before calling `min()`.

```python
def get_least_connections_server():
    active_urls = {server["url"] for server in backend_servers}
    filtered = {url: count for url, count in active_connections.items() if url in active_urls}
    return min(filtered, key=filtered.get)
```

> [!note]
> The original article called `min(active_connections, ...)` directly, which considers all servers, including ones removed by the health checker. This could route traffic to a downed server, so to address this requires filtering out non-active servers.

---

### Request Handler

```python
class LoadBalancerHandler(http.server.BaseHTTPRequestHandler):
    def forward_request(self, backend):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else None

        try:
            response = requests.request(
                method=self.command,
                url=f"{backend}{self.path}",
                headers=self.headers,
                data=body,
                allow_redirects=False
            )
            self.send_response(response.status_code)
            for header, value in response.headers.items():
                self.send_header(header, value)
            self.end_headers()
            self.wfile.write(response.content)
        except requests.RequestException as e:
            self.send_error(500, f"Error forwarding request: {e}")

    def do_GET(self):
        if ALGORITHM == "round_robin":
            backend = get_next_server()
        else:
            backend = get_least_connections_server()

        active_connections[backend] += 1
        logging.info(f"Forwarding request to {backend} (active connections: {active_connections[backend]})")
        self.forward_request(backend)
        active_connections[backend] -= 1

    def do_POST(self):
        self.do_GET()
```

`do_GET` is automatically called by Python's HTTP server on every GET request. It selects a backend, increments the connection counter, forwards the request, and decrements when done.

`forward_request` acts as a transparent proxy — it reads the incoming request and re-sends it to the chosen backend with the same method and path. The original client never knows a middleman was involved.

> [!note]
> The original article required manually editing two separate lines to switch algorithms. This version uses a single `ALGORITHM` config flag at the top of the file.

## 📊 Expected Output

### Round Robin (`ALGORITHM = "round_robin"`)

Look for the **2:1 pattern** — `8001` appearing twice for every one `8002`:

```
2026-02-25 21:30:01 - INFO - Load balancer running on port 8080 using round_robin...
2026-02-25 21:30:05 - INFO - Forwarding request to http://127.0.0.1:8001 (active connections: 1)
2026-02-25 21:30:05 - INFO - Forwarding request to http://127.0.0.1:8001 (active connections: 1)
2026-02-25 21:30:07 - INFO - Forwarding request to http://127.0.0.1:8002 (active connections: 1)
2026-02-25 21:30:09 - INFO - Forwarding request to http://127.0.0.1:8001 (active connections: 1)
2026-02-25 21:30:09 - INFO - Forwarding request to http://127.0.0.1:8001 (active connections: 1)
2026-02-25 21:30:09 - INFO - Forwarding request to http://127.0.0.1:8002 (active connections: 1)
```

### Least Connections (`ALGORITHM = "least_connections"`)

Locally, requests complete near-instantly so both servers stay at 0 connections — you'll see roughly even distribution. In production with slower requests you'd see the balancer actively avoiding busier servers:

```
2026-02-25 21:30:01 - INFO - Load balancer running on port 8080 using least_connections...
2026-02-25 21:30:05 - INFO - Forwarding request to http://127.0.0.1:8001 (active connections: 1)
2026-02-25 21:30:05 - INFO - Forwarding request to http://127.0.0.1:8002 (active connections: 1)
2026-02-25 21:30:07 - INFO - Forwarding request to http://127.0.0.1:8001 (active connections: 1)
```

### Health Check Events

```
2026-02-25 21:35:01 - WARNING - Server http://127.0.0.1:8001 is unhealthy. Removing from pool.
2026-02-25 21:35:11 - INFO    - Server http://127.0.0.1:8001 is healthy again. Adding back to pool.
```

## 🔎 Misc Behavior Worth Knowing

Miscellaneous encounters during testing that may or may not appear:

**Multiple log lines per browser visit** — Browsers automatically fire several requests per page load (favicon, repo-figures, etc.).

**`::ffff:127.0.0.1`** — Your local IP in IPv6 format. Python's HTTP server supports both address families.

**`GET /favicon.ico 404`** — The browser automatically looks for a tab icon. Our bare Python backend doesn't have one, so it returns 404.

**`KeyboardInterrupt` on `Ctrl+C`** — The original article does not gracefully handle shut down, so Python prints a full traceback on exit. By wrapping `serve_forever()` in `try/except KeyboardInterrupt`, a clean shutdown message is presented instead.
