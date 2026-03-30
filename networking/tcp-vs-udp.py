import socket
import threading
import time
import random

HOST = "127.0.0.1"
MESSAGES = ["Message 1", "Message 2", "Message 3", "Message 4", "Message 5"]

# ---- CONFIGURATION ----
MODE = "tcp"     # options: "tcp" or "udp"
LOSS_RATE = 0.4  # simulated packet loss — only applies to udp (0.0 to 1.0)
# -----------------------

PORT = 9001 if MODE == "tcp" else 9002


# ─── TCP ────────────────────────────────────────────────────────────────────

def tcp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)
        print("[SERVER] Waiting for connection...")
        conn, addr = server.accept()
        with conn:
            print(f"[SERVER] Connected to {addr}")
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                print(f"[SERVER] Received: {data.decode()}")
        print("[SERVER] Connection closed.")


def tcp_client():
    time.sleep(0.5)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((HOST, PORT))
        print(f"[CLIENT] Connected to server")
        for msg in MESSAGES:
            print(f"[CLIENT] Sending: {msg}")
            client.sendall(msg.encode())
            time.sleep(0.3)
    print("[CLIENT] All messages sent.")


# ─── UDP ────────────────────────────────────────────────────────────────────

def udp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind((HOST, PORT))
        print(
            f"[SERVER] Listening on {HOST}:{PORT} (simulating {int(LOSS_RATE * 100)}% packet loss)")
        received = 0
        for _ in range(len(MESSAGES)):
            data, addr = server.recvfrom(1024)
            if random.random() < LOSS_RATE:
                print(f"[SERVER] ✗ Dropped packet (simulated loss)")
            else:
                print(f"[SERVER] ✓ Received: {data.decode()}")
                received += 1
        print(f"[SERVER] Done. Received {received}/{len(MESSAGES)} messages.")
        print("[SERVER] Shutting down.")


def udp_client():
    time.sleep(0.5)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        for msg in MESSAGES:
            print(f"[CLIENT] Sending: {msg}")
            client.sendto(msg.encode(), (HOST, PORT))
            time.sleep(0.3)
    print("[CLIENT] All messages sent — but did they all arrive?")


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if MODE == "tcp":
        print("=== TCP Demo ===\n")
        server_thread = threading.Thread(target=tcp_server)
        server_thread.start()
        tcp_client()
        server_thread.join()
    elif MODE == "udp":
        print("=== UDP Demo ===\n")
        server_thread = threading.Thread(target=udp_server)
        server_thread.start()
        udp_client()
        server_thread.join()
    else:
        print(f"Unknown MODE '{MODE}'. Choose 'tcp' or 'udp'.")
