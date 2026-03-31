import socket
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---- CONFIGURATION ----
UPSTREAM_DNS = "1.1.1.1"
UPSTREAM_PORT = 53
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 5354
# -----------------------


def extract_domain(data):
    parts = []
    i = 12  # skip the 12-byte DNS header
    while data[i] != 0:
        length = data[i]
        i += 1
        parts.append(data[i:i + length].decode(errors="replace"))
        i += length
    return ".".join(parts)


def forward_upstream(query):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
        upstream.settimeout(3)
        upstream.sendto(query, (UPSTREAM_DNS, UPSTREAM_PORT))
        response, _ = upstream.recvfrom(512)
    return response


if __name__ == "__main__":
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind((LISTEN_HOST, LISTEN_PORT))
        logging.info(f"DNS Proxy listening on {LISTEN_HOST}:{LISTEN_PORT}")
        logging.info(
            f"Forwarding all queries to {UPSTREAM_DNS}:{UPSTREAM_PORT}\n")
        try:
            while True:
                data, client_addr = server.recvfrom(512)
                domain = extract_domain(data)
                logging.info(
                    f"Received query for {domain} — forwarding upstream...")
                response = forward_upstream(data)
                server.sendto(response, client_addr)
        except KeyboardInterrupt:
            logging.info("Shutting down DNS proxy...")
