#!/usr/bin/env python3
"""Zero-config Вебмастер: user_id/host_id выводятся из API, host — по домену."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("webmaster_fetch", ROOT / "scripts" / "webmaster-fetch.py")
wf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wf)


def host(host_id: str, url: str, verified: bool = True) -> dict:
    return {"host_id": host_id, "ascii_host_url": url, "verified": verified}


class NormalizeDomainTest(unittest.TestCase):
    def test_strips_scheme_www_path_and_port(self) -> None:
        self.assertEqual(wf.normalize_domain("https://www.Gsse.ru/catalog/"), "gsse.ru")
        self.assertEqual(wf.normalize_domain("gsse.ru:443"), "gsse.ru")
        self.assertEqual(wf.normalize_domain("  emwoody.ru "), "emwoody.ru")
        self.assertEqual(wf.normalize_domain(""), "")


class PickHostTest(unittest.TestCase):
    HOSTS = [
        host("http:gsse.ru:80", "http://gsse.ru/"),
        host("https:gsse.ru:443", "https://gsse.ru/"),
        host("https:emwoody.ru:443", "https://emwoody.ru/"),
        host("https:old.gsse.ru:443", "https://old.gsse.ru/", verified=False),
    ]

    def test_domain_match_prefers_https(self) -> None:
        host_id, why = wf.pick_host(self.HOSTS, "gsse.ru")
        self.assertEqual(host_id, "https:gsse.ru:443")
        self.assertEqual(why, "")

    def test_www_and_scheme_in_domain_are_tolerated(self) -> None:
        host_id, _ = wf.pick_host(self.HOSTS, "https://www.emwoody.ru")
        self.assertEqual(host_id, "https:emwoody.ru:443")

    def test_single_verified_host_without_domain(self) -> None:
        host_id, why = wf.pick_host([host("https:one.ru:443", "https://one.ru/")], "")
        self.assertEqual(host_id, "https:one.ru:443")
        self.assertEqual(why, "")

    def test_many_hosts_without_domain_asks_for_hint(self) -> None:
        host_id, why = wf.pick_host(self.HOSTS, "")
        self.assertIsNone(host_id)
        self.assertIn("--domain", why)

    def test_unknown_domain_reports_honestly(self) -> None:
        host_id, why = wf.pick_host(self.HOSTS, "nope.ru")
        self.assertIsNone(host_id)
        self.assertIn("nope.ru", why)

    def test_unverified_pool_used_when_nothing_verified(self) -> None:
        only_unverified = [host("https:new.ru:443", "https://new.ru/", verified=False)]
        host_id, _ = wf.pick_host(only_unverified, "new.ru")
        self.assertEqual(host_id, "https:new.ru:443")


if __name__ == "__main__":
    unittest.main()
