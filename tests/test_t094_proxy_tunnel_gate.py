#!/usr/bin/env python3
"""T-094 (F-2): a paid host reached through an HTTP(S)_PROXY env var used to
bypass `spend_guard` entirely. With a proxy configured, `socket.getaddrinfo`/
`socket.socket.connect` (the layer the gate patched through T-089 round 3)
only ever see the PROXY's own host — the paid hostname travels inside the
CONNECT tunnel request, built by `http.client.HTTPConnection.set_tunnel()`.
This test proves that call site is now gated too, without a single live
network attempt (per §5/packet constraints — no address is ever resolved or
connected to; `set_tunnel()` only stores the target host until `connect()`
is called later).
"""

from __future__ import annotations

import http.client
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import seo_cycle_core  # noqa: F401  (side effect: installs the spend_guard patches)
from seo_cycle_core import spend_guard as sg


class ProxyTunnelGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(sg.gate_installed(), "spend_guard patches must be the active implementation")

    def test_set_tunnel_is_patched(self) -> None:
        self.assertIs(http.client.HTTPConnection.set_tunnel, sg._guarded_set_tunnel)

    def test_unarmed_paid_host_via_tunnel_is_refused(self) -> None:
        # No socket is opened by set_tunnel() itself — it only records the
        # target host for the CONNECT request connect() would send later.
        conn = http.client.HTTPConnection("127.0.0.1", 1)
        with self.assertRaises(sg.SpendNotArmedError):
            conn.set_tunnel("api.dataforseo.com")

    def test_free_host_via_tunnel_is_not_refused(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", 1)
        conn.set_tunnel("example.com")  # must not raise

    def test_armed_paid_host_via_tunnel_is_allowed(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", 1)
        with sg.armed_spend(lambda: True, "api.dataforseo.com"):
            conn.set_tunnel("api.dataforseo.com")  # must not raise while armed

    def test_case_and_trailing_dot_do_not_evade_the_tunnel_check(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", 1)
        with self.assertRaises(sg.SpendNotArmedError):
            conn.set_tunnel("API.DATAFORSEO.COM.")

    def test_explicit_port_does_not_evade_the_tunnel_check(self) -> None:
        # T-094 round 2 (R-1): a URL that spells its port out
        # (https://api.dataforseo.com:443/...) makes urllib pass
        # "api.dataforseo.com:443" to set_tunnel — an independent gate
        # reproduced this live and it slipped past PAID_HOSTS unstripped.
        conn = http.client.HTTPConnection("127.0.0.1", 1)
        with self.assertRaises(sg.SpendNotArmedError):
            conn.set_tunnel("api.dataforseo.com:443")

    def test_strip_port_handles_bracketed_ipv6_and_leaves_bare_ipv6_alone(self) -> None:
        self.assertEqual(sg._strip_port("[::1]:443"), "::1")
        self.assertEqual(sg._strip_port("::1"), "::1")
        self.assertEqual(sg._strip_port("api.dataforseo.com:443"), "api.dataforseo.com")
        self.assertEqual(sg._strip_port("api.dataforseo.com"), "api.dataforseo.com")


if __name__ == "__main__":
    unittest.main()
