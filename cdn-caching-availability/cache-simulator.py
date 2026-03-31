import time
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

    def hit_ratio(self):
        total = self.hits + self.misses
        return round((self.hits / total) * 100, 1) if total > 0 else 0.0


if __name__ == "__main__":
    cache = TTLCache()

    cache.set("google.com", "142.250.80.46", ttl=DEFAULT_TTL)
    cache.set("github.com", "140.82.114.4", ttl=DEFAULT_TTL)

    logging.info(f"HIT  → {cache.get('google.com')}")   # should hit
    logging.info(f"HIT  → {cache.get('github.com')}")   # should hit
    logging.info(f"MISS → {cache.get('stripe.com')}")   # should miss

    logging.info(f"Hit ratio: {cache.hit_ratio()}%")
