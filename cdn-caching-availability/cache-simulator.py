import time
import random
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---- CONFIGURATION ----
DEFAULT_TTL = 6  # seconds
# -----------------------


class TTLCache:

    def __init__(self):
        self.store = {}  # { key: (value, expiry_timestamp) }
        self.hits = 0
        self.misses = 0

    def get(self, key):
        if key in self.store:
            value, expiry = self.store[key]
            if time.time() < expiry:
                self.hits += 1
                return value
            else:
                del self.store[key]  # lazy eviction
        self.misses += 1
        return None

    def set(self, key, value, ttl):
        self.store[key] = (value, time.time() + ttl)

    def invalidate(self, key):
        if key in self.store:
            del self.store[key]
            logging.info(f"  INVALIDATED → {key}")

    def size(self):
        return len(self.store)

    def hit_ratio(self):
        total = self.hits + self.misses
        return round((self.hits / total) * 100, 1) if total > 0 else 0.0

    def stats(self):
        print("─" * 40)
        print(f"  Cache Hits:    {self.hits}")
        print(f"  Cache Misses:  {self.misses}")
        print(f"  Hit Ratio:     {self.hit_ratio()}%")
        print(f"  Cached items:  {self.size()}")
        print("─" * 40)

# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


# Simulated origin server (in a real CDN, this would be your web server)
ORIGIN = {
    "github.com":     "140.82.114.4",
    "google.com":     "142.250.80.46",
    "cloudflare.com": "104.16.132.229",
    "openai.com":     "104.18.32.47",
    "stripe.com":     "54.187.188.194",
}


def fetch_from_origin(domain):
    time.sleep(0.05)  # simulate network round-trip delay
    return ORIGIN.get(domain, "NXDOMAIN")


def request(cache, domain):
    result = cache.get(domain)
    if result is not None:
        logging.info(f"  HIT  │ {domain:20s} → {result}")
    else:
        ip = fetch_from_origin(domain)
        cache.set(domain, ip, ttl=DEFAULT_TTL)
        logging.info(
            f"  MISS │ {domain:20s} → {ip} (fetched from origin, TTL {DEFAULT_TTL}s)")


def run_simulation():
    cache = TTLCache()
    domains = list(ORIGIN.keys())

    print("=" * 40)
    print("  CDN Cache Simulator")
    print("=" * 40)

    # Phase 1
    print("\n[Phase 1] First-time requests")
    print("─" * 40)
    for domain in domains:
        request(cache, domain)
        time.sleep(0.1)

    # Phase 2
    print("\n[Phase 2] Repeat requests")
    print("─" * 40)
    for domain in random.choices(domains, k=8):
        request(cache, domain)
        time.sleep(0.1)

    # Phase 3
    print("\n[Phase 3] Manual cache invalidation")
    print("─" * 40)
    cache.invalidate("github.com")
    request(cache, "github.com")

    # Phase 4
    print(f"\n[Phase 4] Waiting {DEFAULT_TTL}s for TTL to expire...")
    print("─" * 40)
    time.sleep(DEFAULT_TTL + 1)
    for domain in random.choices(domains, k=4):
        request(cache, domain)
        time.sleep(0.1)

    print("\n[Results]")
    cache.stats()


if __name__ == "__main__":
    run_simulation()
