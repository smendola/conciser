"""BrightData residential proxy configuration for yt-dlp."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BrightDataProxy:
    """Configure BrightData residential proxies for yt-dlp and HTTP requests."""

    # BrightData residential proxy endpoint
    PROXY_HOST = "brd.superproxy.io"
    PROXY_PORT = 33335

    # Common country codes for geo-targeting
    COUNTRY_CODES = {
        'us': 'United States',
        'gb': 'United Kingdom',
        'de': 'Germany',
        'fr': 'France',
        'au': 'Australia',
        'ca': 'Canada',
        'jp': 'Japan',
        'br': 'Brazil',
        'in': 'India',
        'kr': 'South Korea',
    }

    def __init__(
        self,
        customer_id: str,
        password: str,
        zone: str = "residential",
        country: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        """
        Initialize BrightData proxy configuration.

        Args:
            customer_id: Your BrightData customer ID
            password: Your BrightData zone password
            zone: Zone name (default: "residential")
            country: ISO 3166-1 alpha-2 country code (e.g., "us", "gb")
            session_id: Optional session ID for sticky IP sessions

        Example:
            # Basic residential proxy
            proxy = BrightDataProxy("hl_abc123", "my_password")

            # US-targeted residential proxy
            proxy = BrightDataProxy("hl_abc123", "my_password", country="us")

            # Sticky session (same IP for multiple requests)
            proxy = BrightDataProxy("hl_abc123", "my_password", session_id="session_123")
        """
        self.customer_id = customer_id.strip()
        self.password = password.strip()
        self.zone = zone.strip()
        self.country = country.strip().lower() if country else None
        self.session_id = session_id.strip() if session_id else None

        if not self.customer_id or not self.password:
            raise ValueError("BrightData customer_id and password are required")

        if self.country and self.country not in self.COUNTRY_CODES:
            logger.warning(
                f"Country code '{self.country}' not in common list. "
                f"Supported: {', '.join(self.COUNTRY_CODES.keys())}"
            )

    def get_proxy_url(self) -> str:
        """
        Build the complete BrightData proxy URL for yt-dlp and HTTP clients.

        Format: http://brd-customer-{customer_id}-zone-{zone}[-country-{country}][-session-{session_id}]:{password}@{host}:{port}

        Returns:
            Proxy URL string suitable for yt-dlp's 'proxy' option
        """
        # Build username with optional parameters
        username_parts = [
            f"brd-customer-{self.customer_id}",
            f"zone-{self.zone}"
        ]

        if self.country:
            username_parts.append(f"country-{self.country}")

        if self.session_id:
            username_parts.append(f"session-{self.session_id}")

        username = "-".join(username_parts)

        proxy_url = f"http://{username}:{self.password}@{self.PROXY_HOST}:{self.PROXY_PORT}"

        logger.debug(f"BrightData proxy URL configured: zone={self.zone}, country={self.country or 'auto'}")
        return proxy_url

    def get_urllib_proxy_handler(self) -> dict:
        """
        Get proxy configuration dict for urllib.request.ProxyHandler.

        Returns:
            Dict with 'http' and 'https' keys for ProxyHandler
        """
        proxy_url = self.get_proxy_url()
        return {
            'http': proxy_url,
            'https': proxy_url
        }

    @classmethod
    def from_env(cls,
                 customer_id: str,
                 password: str,
                 zone: str = "residential",
                 country: Optional[str] = None) -> Optional['BrightDataProxy']:
        """
        Create BrightData proxy from environment variables.

        Returns None if credentials are missing or invalid.

        Args:
            customer_id: BrightData customer ID from env
            password: BrightData password from env
            zone: Zone name (default: "residential")
            country: Optional country code for geo-targeting

        Returns:
            BrightDataProxy instance or None if credentials invalid
        """
        if not customer_id or not password:
            logger.info("BrightData credentials not configured, proxy disabled")
            return None

        try:
            return cls(customer_id, password, zone, country)
        except ValueError as e:
            logger.warning(f"Failed to configure BrightData proxy: {e}")
            return None


def parse_proxy_url(proxy_url: str) -> Optional[dict]:
    """
    Parse a proxy URL into components.

    Args:
        proxy_url: Proxy URL string (e.g., "http://user:pass@host:port")

    Returns:
        Dict with parsed components or None if invalid
    """
    if not proxy_url:
        return None

    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)

        return {
            'scheme': parsed.scheme,
            'username': parsed.username,
            'password': parsed.password,
            'host': parsed.hostname,
            'port': parsed.port or (33335 if 'brightdata' in proxy_url or 'brd.' in proxy_url else 80)
        }
    except Exception as e:
        logger.error(f"Failed to parse proxy URL: {e}")
        return None
