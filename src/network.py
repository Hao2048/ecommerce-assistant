"""Use environment/config proxies and macOS system proxies consistently across SDKs.

httpx does not discover macOS system proxy settings on its own. urllib does.
TLS certificate verification remains enabled.
"""
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

import httpx

from settings import config


def proxy_for(url):
    configured = getattr(config, 'OUTBOUND_PROXY', None)
    if configured is not None:
        # An empty string explicitly requests a direct connection.
        return configured or None
    host = urlsplit(url).hostname or ''
    if proxy_bypass(host):
        return None
    proxies = getproxies()
    return proxies.get(urlsplit(url).scheme) or proxies.get('all')


def http_client(url, timeout=60):
    return httpx.Client(proxy=proxy_for(url), timeout=timeout,
                        trust_env=getattr(config, 'OUTBOUND_PROXY', None) != '')
