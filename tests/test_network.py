import unittest
from unittest.mock import patch

import network


class NetworkTests(unittest.TestCase):
    def test_macos_proxy_is_used_without_environment_variables(self):
        with patch.object(network.config, 'OUTBOUND_PROXY', None, create=True), \
                patch.object(network, 'proxy_bypass', return_value=False), \
                patch.object(network, 'getproxies', return_value={'https': 'http://127.0.0.1:7897'}):
            self.assertEqual(network.proxy_for('https://example.com'), 'http://127.0.0.1:7897')

    def test_explicit_direct_connection_overrides_system_proxy(self):
        with patch.object(network.config, 'OUTBOUND_PROXY', '', create=True):
            self.assertIsNone(network.proxy_for('https://example.com'))

    def test_localhost_bypasses_proxy(self):
        with patch.object(network.config, 'OUTBOUND_PROXY', None, create=True), \
                patch.object(network, 'proxy_bypass', return_value=True):
            self.assertIsNone(network.proxy_for('http://localhost:8511'))

    def test_explicit_direct_does_not_reenable_environment_proxy(self):
        with patch.object(network.config, 'OUTBOUND_PROXY', '', create=True), \
                patch.object(network.httpx, 'Client') as client:
            network.http_client('https://example.com')
        self.assertFalse(client.call_args.kwargs['trust_env'])
