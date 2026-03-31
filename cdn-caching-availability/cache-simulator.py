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

    def invalidate(self, key):
        if key in self.store:
            del self.store[key]
            logging.info(f"INVALIDATED → {key}")

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


if __name__ == "__main__":
    cache = TTLCache()

    cache.set("google.com", "142.250.80.46", ttl=DEFAULT_TTL)
    cache.set("github.com", "140.82.114.4", ttl=DEFAULT_TTL)

    logging.info(f"HIT  → {cache.get('google.com')}")
    logging.info(f"HIT  → {cache.get('github.com')}")
    logging.info(f"MISS → {cache.get('stripe.com')}")

    cache.invalidate("google.com")
    logging.info(f"MISS → {cache.get('google.com')}")

    cache.stats()
