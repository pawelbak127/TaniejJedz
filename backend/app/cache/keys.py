"""Cache key patterns and TTL configuration.

TTLs from architecture v3.1 section 10:
- metadata: 24h
- menu + modifiers: 6h
- prices: 1h
- delivery fees: 5min
- promotions: 30min
- operating hours: 12h
- search results: 15min
"""


class CacheTTL:
    """TTL values in seconds per data type."""

    METADATA = 86400        # 24h
    MENU = 21600            # 6h
    PRICES = 3600           # 1h
    DELIVERY_FEES = 300     # 5min
    PROMOTIONS = 1800       # 30min
    OPERATING_HOURS = 43200 # 12h
    SEARCH = 900            # 15min


class CacheKeys:
    """Key pattern builders for Redis cache."""

    @staticmethod
    def search(city_slug: str, query_hash: str) -> str:
        return f"cache:search:{city_slug}:{query_hash}"

    @staticmethod
    def restaurant_meta(restaurant_id: str) -> str:
        return f"cache:restaurant:{restaurant_id}:meta"

    @staticmethod
    def menu(restaurant_id: str) -> str:
        return f"cache:restaurant:{restaurant_id}:menu"

    @staticmethod
    def platform_prices(platform_restaurant_id: str) -> str:
        return f"cache:platform:{platform_restaurant_id}:prices"

    @staticmethod
    def delivery_fee(platform_restaurant_id: str, geohash: str) -> str:
        return f"cache:delivery:{platform_restaurant_id}:{geohash}"

    @staticmethod
    def promotions(platform_restaurant_id: str) -> str:
        return f"cache:promos:{platform_restaurant_id}"

    @staticmethod
    def operating_hours(platform_restaurant_id: str) -> str:
        return f"cache:hours:{platform_restaurant_id}"

    @staticmethod
    def feature_flags() -> str:
        return "flags:all"

    @staticmethod
    def feature_flag(key: str) -> str:
        return f"flags:{key}"
