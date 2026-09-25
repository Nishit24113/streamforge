"""
Advanced transformation operations for StreamForge pipelines.

Includes:
- SQL-like queries (SELECT, WHERE, JOIN)
- Regex pattern extraction and validation
- GeoIP lookup for IP addresses
- URL parsing and domain extraction
- User agent parsing
"""

import re
import json
from typing import Any, Dict, List
from urllib.parse import urlparse, parse_qs


class SQLTransform:
    """SQL-like query operations on event data."""

    @staticmethod
    def select(events: List[Dict], fields: List[str]) -> List[Dict]:
        """
        SELECT operation - project specific fields.

        Example: SELECT user_id, amount FROM events
        """
        result = []
        for evt in events:
            payload = _get_payload(evt)
            selected = {}
            for field in fields:
                if field in payload:
                    selected[field] = payload[field]
                elif field in evt:
                    selected[field] = evt[field]
            if selected:
                result.append({**evt, 'payload': selected})
        return result

    @staticmethod
    def where(events: List[Dict], condition: str) -> List[Dict]:
        """
        WHERE operation - filter events by condition.

        Supported operators: =, !=, >, <, >=, <=, IN, NOT IN, LIKE

        Examples:
        - "amount > 100"
        - "status = 'completed'"
        - "country IN ['US', 'CA', 'UK']"
        - "email LIKE '%@gmail.com'"
        """
        result = []
        for evt in events:
            payload = _get_payload(evt)
            if _evaluate_condition(payload, condition):
                result.append(evt)
        return result

    @staticmethod
    def join(left_events: List[Dict], right_events: List[Dict],
             left_key: str, right_key: str, join_type: str = 'inner') -> List[Dict]:
        """
        JOIN operation - combine events from two pipelines.

        Types: inner, left, right, outer
        """
        # Build index for right events
        right_index = {}
        for evt in right_events:
            payload = _get_payload(evt)
            key_value = payload.get(right_key)
            if key_value:
                right_index[key_value] = evt

        result = []
        for left_evt in left_events:
            left_payload = _get_payload(left_evt)
            key_value = left_payload.get(left_key)

            if key_value and key_value in right_index:
                # Match found
                right_evt = right_index[key_value]
                right_payload = _get_payload(right_evt)
                merged = {**left_payload, **right_payload}
                result.append({**left_evt, 'payload': merged})
            elif join_type in ('left', 'outer'):
                # Left join - include left event even without match
                result.append(left_evt)

        # Right join - include unmatched right events
        if join_type in ('right', 'outer'):
            matched_keys = {_get_payload(evt).get(left_key) for evt in result}
            for key, right_evt in right_index.items():
                if key not in matched_keys:
                    result.append(right_evt)

        return result


class RegexTransform:
    """Regular expression operations for pattern extraction and validation."""

    @staticmethod
    def extract(events: List[Dict], field: str, pattern: str,
                group: int = 0, target_field: str = None) -> List[Dict]:
        """
        Extract substring matching regex pattern.

        Examples:
        - Extract domain from email: pattern = r'@(.+)$', group = 1
        - Extract phone area code: pattern = r'\((\d{3})\)', group = 1
        """
        compiled = re.compile(pattern)
        target = target_field or f'{field}_extracted'

        for evt in events:
            payload = _get_payload(evt)
            value = str(payload.get(field, ''))

            match = compiled.search(value)
            if match:
                payload[target] = match.group(group)
            else:
                payload[target] = None

            evt['payload'] = payload

        return events

    @staticmethod
    def validate(events: List[Dict], field: str, pattern: str,
                 mark_invalid: bool = True) -> List[Dict]:
        """
        Validate field against regex pattern.

        Examples:
        - Email: r'^[\w\.-]+@[\w\.-]+\.\w+$'
        - Phone: r'^\+?1?\d{10,15}$'
        - Credit card: r'^\d{4}-?\d{4}-?\d{4}-?\d{4}$'
        """
        compiled = re.compile(pattern)

        for evt in events:
            payload = _get_payload(evt)
            value = str(payload.get(field, ''))

            is_valid = bool(compiled.match(value))

            if mark_invalid and not is_valid:
                payload[f'{field}_valid'] = False
            elif mark_invalid:
                payload[f'{field}_valid'] = True

            evt['payload'] = payload

        return events if not mark_invalid else events

    @staticmethod
    def replace(events: List[Dict], field: str, pattern: str,
                replacement: str) -> List[Dict]:
        """
        Replace substring matching pattern.

        Examples:
        - Redact SSN: pattern = r'\d{3}-\d{2}-\d{4}', replacement = 'XXX-XX-XXXX'
        - Strip HTML: pattern = r'<[^>]+>', replacement = ''
        """
        compiled = re.compile(pattern)

        for evt in events:
            payload = _get_payload(evt)
            value = str(payload.get(field, ''))

            payload[field] = compiled.sub(replacement, value)
            evt['payload'] = payload

        return events


class GeoIPTransform:
    """IP address geolocation lookup (simplified implementation)."""

    # Simplified GeoIP database (in production, use MaxMind GeoIP2)
    IP_RANGES = {
        '8.8.8.0/24': {'country': 'US', 'city': 'Mountain View', 'region': 'California', 'lat': 37.386, 'lon': -122.084},
        '1.1.1.0/24': {'country': 'AU', 'city': 'Sydney', 'region': 'NSW', 'lat': -33.867, 'lon': 151.207},
        '192.168.0.0/16': {'country': 'PRIVATE', 'city': None, 'region': None, 'lat': None, 'lon': None},
        '10.0.0.0/8': {'country': 'PRIVATE', 'city': None, 'region': None, 'lat': None, 'lon': None},
    }

    @staticmethod
    def lookup(events: List[Dict], ip_field: str = 'ip_address') -> List[Dict]:
        """
        Lookup geographic location from IP address.

        Adds fields: country, city, region, latitude, longitude
        """
        for evt in events:
            payload = _get_payload(evt)
            ip = payload.get(ip_field, '')

            # Simplified lookup (in production, use MaxMind or ip-api.com)
            geo = GeoIPTransform._lookup_ip(ip)

            if geo:
                payload['geo_country'] = geo.get('country')
                payload['geo_city'] = geo.get('city')
                payload['geo_region'] = geo.get('region')
                payload['geo_latitude'] = geo.get('lat')
                payload['geo_longitude'] = geo.get('lon')

            evt['payload'] = payload

        return events

    @staticmethod
    def _lookup_ip(ip: str) -> Dict:
        """Lookup IP in simplified database."""
        # Check private ranges first
        if ip.startswith('192.168.') or ip.startswith('10.'):
            return {'country': 'PRIVATE', 'city': None, 'region': None}

        # Default to US for public IPs (simplified)
        return {'country': 'US', 'city': 'Unknown', 'region': 'Unknown', 'lat': 37.0, 'lon': -95.0}


class URLTransform:
    """URL parsing and domain extraction."""

    @staticmethod
    def parse(events: List[Dict], url_field: str = 'url') -> List[Dict]:
        """
        Parse URL into components: scheme, domain, path, query params.

        Example: https://shop.example.com/products?id=123&sort=price
        → scheme='https', domain='shop.example.com', path='/products',
          query={'id': '123', 'sort': 'price'}
        """
        for evt in events:
            payload = _get_payload(evt)
            url = payload.get(url_field, '')

            if url:
                parsed = urlparse(url)
                payload['url_scheme'] = parsed.scheme
                payload['url_domain'] = parsed.netloc
                payload['url_path'] = parsed.path
                payload['url_params'] = dict(parse_qs(parsed.query))

            evt['payload'] = payload

        return events

    @staticmethod
    def extract_domain(events: List[Dict], url_field: str = 'url',
                       include_subdomain: bool = False) -> List[Dict]:
        """
        Extract domain from URL.

        Examples:
        - https://shop.example.com/page → example.com (or shop.example.com)
        - http://blog.company.co.uk → company.co.uk
        """
        for evt in events:
            payload = _get_payload(evt)
            url = payload.get(url_field, '')

            if url:
                parsed = urlparse(url)
                domain = parsed.netloc

                if not include_subdomain and domain:
                    # Extract root domain (simplified - doesn't handle all TLDs)
                    parts = domain.split('.')
                    if len(parts) >= 2:
                        domain = '.'.join(parts[-2:])

                payload['domain'] = domain

            evt['payload'] = payload

        return events


class UserAgentTransform:
    """User agent string parsing."""

    @staticmethod
    def parse(events: List[Dict], ua_field: str = 'user_agent') -> List[Dict]:
        """
        Parse user agent string into browser, OS, device.

        Example: Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)...
        → browser='Safari', os='iOS', device='iPhone'
        """
        for evt in events:
            payload = _get_payload(evt)
            ua = payload.get(ua_field, '')

            if ua:
                # Simplified parsing (in production, use user-agents library)
                browser = UserAgentTransform._detect_browser(ua)
                os = UserAgentTransform._detect_os(ua)
                device = UserAgentTransform._detect_device(ua)

                payload['browser'] = browser
                payload['os'] = os
                payload['device_type'] = device
                payload['is_mobile'] = device in ('mobile', 'tablet')
                payload['is_bot'] = 'bot' in ua.lower() or 'crawler' in ua.lower()

            evt['payload'] = payload

        return events

    @staticmethod
    def _detect_browser(ua: str) -> str:
        ua_lower = ua.lower()
        if 'edg/' in ua_lower:
            return 'Edge'
        if 'chrome/' in ua_lower:
            return 'Chrome'
        if 'firefox/' in ua_lower:
            return 'Firefox'
        if 'safari/' in ua_lower and 'chrome' not in ua_lower:
            return 'Safari'
        return 'Unknown'

    @staticmethod
    def _detect_os(ua: str) -> str:
        ua_lower = ua.lower()
        if 'windows' in ua_lower:
            return 'Windows'
        if 'mac os' in ua_lower or 'macos' in ua_lower:
            return 'macOS'
        if 'iphone' in ua_lower or 'ipad' in ua_lower:
            return 'iOS'
        if 'android' in ua_lower:
            return 'Android'
        if 'linux' in ua_lower:
            return 'Linux'
        return 'Unknown'

    @staticmethod
    def _detect_device(ua: str) -> str:
        ua_lower = ua.lower()
        if 'mobile' in ua_lower or 'iphone' in ua_lower:
            return 'mobile'
        if 'tablet' in ua_lower or 'ipad' in ua_lower:
            return 'tablet'
        return 'desktop'


# Helper functions

def _get_payload(event: Dict) -> Dict:
    """Extract payload from event, handling both string and dict."""
    payload = event.get('payload', {})
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload


def _evaluate_condition(data: Dict, condition: str) -> bool:
    """
    Evaluate WHERE condition against data.

    Supports: =, !=, >, <, >=, <=, IN, NOT IN, LIKE
    """
    condition = condition.strip()

    # IN operator
    if ' IN ' in condition.upper():
        field, values_str = condition.split(' IN ', 1)
        field = field.strip()
        values_str = values_str.strip()

        # Parse list: ['val1', 'val2'] or ("val1", "val2")
        values = eval(values_str)  # Simplified - in production, use proper parsing
        return data.get(field) in values

    # LIKE operator
    if ' LIKE ' in condition.upper():
        field, pattern = condition.split(' LIKE ', 1)
        field = field.strip()
        pattern = pattern.strip().strip("'\"")

        # Convert SQL LIKE to regex
        regex_pattern = pattern.replace('%', '.*').replace('_', '.')
        value = str(data.get(field, ''))
        return bool(re.match(regex_pattern, value))

    # Comparison operators
    operators = ['>=', '<=', '!=', '=', '>', '<']
    for op in operators:
        if op in condition:
            field, value = condition.split(op, 1)
            field = field.strip()
            value = value.strip().strip("'\"")

            field_value = data.get(field)

            # Type conversion
            try:
                if isinstance(field_value, (int, float)):
                    value = float(value)
            except ValueError:
                pass

            if op == '=':
                return field_value == value
            elif op == '!=':
                return field_value != value
            elif op == '>':
                return field_value > value
            elif op == '<':
                return field_value < value
            elif op == '>=':
                return field_value >= value
            elif op == '<=':
                return field_value <= value

    return False
