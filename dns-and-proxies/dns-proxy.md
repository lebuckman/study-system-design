# Building a DNS Proxy

Build a working DNS proxy that listens for DNS queries over UDP, forwards them to Cloudflare's upstream resolver (`1.1.1.1`), caches responses using each record's TTL, and logs whether each query was a cache hit or miss.

This quick demonstration was implemented with the assistance of Claude.

```
Your Machine (port 5354)
        │
        │  DNS query (UDP)
        ▼
   dns-proxy.py
        │
        ├── Cache hit?  ──► return cached response immediately ✅
        │
        └── Cache miss? ──► forward to 1.1.1.1:53
                                │
                                ▼
                         Upstream response
                                │
                                ▼
                         cache it with TTL
                                │
                                ▼
                         return to client ✅
```

## 💡 Key Concepts

**Using UDP** — DNS uses UDP (not TCP) because queries are small and speed matters. There is no handshake overhead; if no response arrives, the client just retries.

**Port 53 vs Port 5354** — DNS officially runs on port 53, but binding to ports below 1024 requires root/admin privileges. Using `5354` avoids needing `sudo`. Port `5353` is also unavailable on macOS as it's reserved by **mDNS** (Multicast DNS), a system background service.

**DNS Packet Structure** — A DNS query is a raw binary packet. The first 12 bytes are a fixed header, followed by the question section which encodes the domain name as a sequence of length-prefixed labels:

```
google.com → [6]google[3]com[0]
              └─ "google" is 6 chars, "com" is 3 chars, 0 = end
```

## ⚙️ Configuration

At the top of `dns-proxy.py`:

```python
UPSTREAM_DNS = "1.1.1.1"   # Cloudflare — or try "8.8.8.8" for Google
UPSTREAM_PORT = 53
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 5354
```

## ⚡ Getting Started

**Start the proxy:**

```bash
python3 dns-proxy.py
```

**In a second terminal, test with `dig`:**

```bash
# First lookup — expect a MISS
dig @127.0.0.1 -p 5354 google.com

# Same domain again — expect a HIT
dig @127.0.0.1 -p 5354 google.com

# Try others
dig @127.0.0.1 -p 5354 github.com
dig @127.0.0.1 -p 5354 cloudflare.com
```

> [!note]
> `dig` is available on macOS and Linux by default. On Mac, install via `brew install bind` if needed.

## 📍 Key Code Concepts

### Parsing the Domain Name

DNS doesn't transmit domain names as plain strings — they're encoded as length-prefixed labels in the raw binary packet. `extract_domain` reads past the 12-byte header and manually reconstructs the domain:

```python
i = 12  # skip the DNS header
while data[i] != 0:
    length = data[i]
    i += 1
    parts.append(data[i:i + length].decode(errors="replace"))
    i += length
return ".".join(parts)
```

### Extracting TTL From the Response

The TTL lives in the answer section of the response packet. Skip through the question section first, then handle the answer section's name field, which can be encoded two ways:

```python
if data[i] & 0xC0 == 0xC0:
    i += 2  # compressed pointer — always exactly 2 bytes
else:
    while data[i] != 0:  # full label — variable length
        i += data[i] + 1
    i += 1

i += 4  # skip type + class
ttl = struct.unpack("!I", data[i:i + 4])[0]
return max(ttl, 5)
```

`struct.unpack("!I", ...)` reads a 4-byte unsigned integer in network byte order (big-endian). The minimum of 5 prevents a TTL of 0 from causing immediate re-fetching on every query.

> [!note]
> Assuming the answer name is always a compressed pointer (the common case) causes TTL values to be read from the wrong offset — producing astronomically large numbers like `1694720879s`. Handling both formats is enforces correct parsing.

### Cache Check + Forwarding

Check the cache first, and forward upstream on a miss:

```python
if domain in cache:
    response, expiry = cache[domain]
    if time.time() < expiry:
        updated_response = data[:2] + response[2:]  # patch transaction ID
        server_socket.sendto(updated_response, client_addr)
        return
    else:
        del cache[domain]  # expired — evict and fall through to upstream

response = forward_upstream(data)
ttl = extract_ttl(response)
cache[domain] = (response, time.time() + ttl)  # store with absolute expiry
server_socket.sendto(response, client_addr)
```

The cache stores `(response_bytes, expiry_timestamp)`, an absolute timestamp rather than a countdown, so we just compare against `time.time()` at lookup without needing to update entries every second.

The `data[:2] + response[2:]` line patches the first 2 bytes of the cached response with the new query's transaction ID. Every DNS query carries a unique ID that the client uses to match responses — serving a cached response with a stale ID causes the client to reject it entirely.

### Forwarding Upstream

Open a fresh UDP socket, send the original query bytes unmodified to `1.1.1.1:53`, and wait up to 3 seconds for a response. If nothing comes back, `socket.timeout` is raised and logged as a warning.

```python
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
    upstream.settimeout(3)
    upstream.sendto(query, (UPSTREAM_DNS, UPSTREAM_PORT))
    response, _ = upstream.recvfrom(512)
```

### 📊 Expected Output

**Proxy terminal:**

```
2026-03-01 14:00:01 - INFO - DNS Proxy listening on 127.0.0.1:5354
2026-03-01 14:00:01 - INFO - Forwarding misses to 1.1.1.1:53

2026-03-01 14:00:05 - INFO - MISS    │ google.com — fetching from upstream
2026-03-01 14:00:05 - INFO - CACHED  │ google.com (TTL 210s)
2026-03-01 14:00:09 - INFO - HIT     │ google.com (TTL 206s remaining)
2026-03-01 14:00:12 - INFO - MISS    │ github.com — fetching from upstream
2026-03-01 14:00:12 - INFO - CACHED  │ github.com (TTL 60s)
2026-03-01 14:00:18 - INFO - HIT     │ google.com (TTL 198s remaining)
```

**`dig` output (first query → cache miss):**

```
;; ANSWER SECTION:
google.com.             210     IN      A       142.250.80.46

;; Query time: 27 msec
;; SERVER: 127.0.0.1#5354(127.0.0.1)
```

- `210` — TTL in seconds, matching `CACHED │ google.com (TTL 210s)` in the proxy log
- `Query time: 27ms` — full round trip through your proxy to Cloudflare and back
- `SERVER: 127.0.0.1#5354` — confirms the response came through your proxy, not upstream directly

**`dig` output (second query → cache hit):**

```
;; Query time: 1 msec
;; SERVER: 127.0.0.1#5354(127.0.0.1)
```

- `Query time: 1ms` vs `27ms` — the cache serving the response without ever leaving your machine

## 🧪 Experimenting

**Watch TTL count down** — Query the same domain every few seconds within its TTL window. Each HIT log will show a lower remaining TTL than the last, counting down in real time as the cached entry ages toward expiry.

```
HIT     │ google.com (TTL 210s remaining)
HIT     │ google.com (TTL 203s remaining)
HIT     │ google.com (TTL 196s remaining)
```

**Trigger an expiry** — Query a domain through your proxy, then wait for its TTL to pass and query it again. You'll see the entry evicted and a fresh upstream fetch:

```
MISS    │ google.com — fetching from upstream
CACHED  │ google.com (TTL 139s)
...wait 139 seconds...
EXPIRED │ google.com — fetching from upstream
CACHED  │ google.com (TTL 145s)
```

**Nonexistent domain** — Query a domain that doesn't exist:

```bash
dig @127.0.0.1 -p 5354 totallyfakedomain12345.com
```

The proxy forwards the query upstream as normal. Cloudflare returns an NXDOMAIN response (DNS for "not found"), which you'll see in the dig output as `status: NXDOMAIN` instead of `status: NOERROR`. The proxy still caches and returns this response.

**Switch upstream resolver** — Change `UPSTREAM_DNS = "8.8.8.8"` and query the same domains. TTL values and response times may differ slightly between Google and Cloudflare depending on their caching state and your network proximity to each provider.

## 💡 Key Observations

- First query for any domain is slower — requires a full upstream round trip
- Repeat queries within the TTL window are near-instant — served from the in-memory cache
- Different domains have different TTLs — records that change often have short TTLs, stable ones have long TTLs
- The proxy treats DNS responses as opaque bytes — it doesn't interpret the IP inside, it just caches and forwards the raw packet

## 🔗 Relation to Load Balancing

A DNS proxy resolves domain names to IP addresses (often for security/filtering), while a load balancer distributes incoming network traffic across multiple backend servers to ensure high availability and performance. Proxies focus on request control and security, whereas load balancers focus on traffic distribution, scalability, and uptime.

|              | Load Balancer              | DNS Proxy             |
| ------------ | -------------------------- | --------------------- |
| Listens on   | Port `8080` (TCP)          | Port `5354` (UDP)     |
| Forwards to  | Backend HTTP servers       | Upstream DNS resolver |
| Caches       | ❌ stateless forwarding    | ✅ with TTL           |
| Tracks state | Active connections         | Cached responses      |
| Uses         | `http.server` + `requests` | Raw `socket` (UDP)    |
