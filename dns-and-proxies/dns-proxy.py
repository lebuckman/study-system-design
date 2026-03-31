import socket
import struct
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---- CONFIGURATION ----
UPSTREAM_DNS = "1.1.1.1"  # Cloudflare — or try "8.8.8.8" for Google
UPSTREAM_PORT = 53
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 5354
# -----------------------

# Cache: { domain: (response_bytes, expiry_timestamp) }
cache = {}


def extract_domain(data):
    """
    Parse the domain name out of a raw DNS query packet.
    DNS encodes names as length-prefixed labels:
    google.com → [6]google[3]com[0]
    """
    parts = []
    i = 12  # skip the 12-byte DNS header
    while data[i] != 0:
        length = data[i]
        i += 1
        parts.append(data[i:i + length].decode(errors="replace"))
        i += length
    return ".".join(parts)


def extract_ttl(data):
    """
    Extract the TTL from the first answer record in a DNS response.
    Handles both compressed pointer and full label name formats in the answer section.
    Falls back to 60 seconds if parsing fails.
    """
    try:
        i = 12
        # Skip the question section (domain name + type + class)
        while data[i] != 0:
            i += data[i] + 1
        i += 5  # skip null terminator + QTYPE (2 bytes) + QCLASS (2 bytes)

        # Answer section name can be a compressed pointer or a full label
        if data[i] & 0xC0 == 0xC0:
            i += 2  # compressed pointer is always 2 bytes
        else:
            while data[i] != 0:
                i += data[i] + 1
            i += 1  # skip null terminator

        i += 4  # skip type (2) + class (2)
        ttl = struct.unpack("!I", data[i:i + 4])[0]
        return max(ttl, 5)  # enforce a minimum TTL of 5 seconds
    except Exception:
        return 60  # safe default


def forward_upstream(query):
    """Send a DNS query to the upstream resolver and return the response."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
        upstream.settimeout(3)
        upstream.sendto(query, (UPSTREAM_DNS, UPSTREAM_PORT))
        response, _ = upstream.recvfrom(512)
    return response


def handle_query(data, client_addr, server_socket):
    """Process a single incoming DNS query."""
    domain = extract_domain(data)
    now = time.time()

    if domain in cache:
        response, expiry = cache[domain]
        if now < expiry:
            remaining = round(expiry - now)
            logging.info(f"HIT     │ {domain} (TTL {remaining}s remaining)")
            # Patch the transaction ID from the new query into the cached response
            updated_response = data[:2] + response[2:]
            server_socket.sendto(updated_response, client_addr)
            return
        else:
            del cache[domain]
            logging.info(f"EXPIRED │ {domain} — fetching from upstream")
    else:
        logging.info(f"MISS    │ {domain} — fetching from upstream")

    try:
        response = forward_upstream(data)
        ttl = extract_ttl(response)
        cache[domain] = (response, now + ttl)
        logging.info(f"CACHED  │ {domain} (TTL {ttl}s)")
        server_socket.sendto(response, client_addr)
    except socket.timeout:
        logging.warning(f"TIMEOUT │ {domain} — upstream did not respond")


if __name__ == "__main__":
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind((LISTEN_HOST, LISTEN_PORT))
        logging.info(f"DNS Proxy listening on {LISTEN_HOST}:{LISTEN_PORT}")
        logging.info(f"Forwarding misses to {UPSTREAM_DNS}:{UPSTREAM_PORT}\n")
        try:
            while True:
                data, client_addr = server.recvfrom(512)
                handle_query(data, client_addr, server)
        except KeyboardInterrupt:
            logging.info("Shutting down DNS proxy...")
