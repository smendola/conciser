#!/usr/bin/env python3
"""
Tests for GET /api/voices endpoint.

Runs against a live server (default: http://localhost:5000).
Set BASE_URL env var to override.
"""
import os
import sys
import json
import urllib.request
import urllib.error

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")


def _get(path):
    """Return (status_code, body_dict)."""
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _voices(locale):
    return _get(f"/api/voices?locale={locale}")


# ── helpers ───────────────────────────────────────────────────────────────────

def _friendly_names(voices, locale=None):
    subset = [v for v in voices if locale is None or v["locale"] == locale]
    return sorted(v["friendly_name"] for v in subset)


def _locales(voices):
    return {v["locale"] for v in voices}


# ── tests ─────────────────────────────────────────────────────────────────────

def test_no_locale_param_returns_400():
    status, body = _get("/api/voices")
    assert status == 400, f"expected 400, got {status}"
    assert "error" in body, "expected error key in body"
    assert "locale" in body["error"].lower(), f"error message should mention 'locale': {body['error']}"


def test_en_prefix_returns_nonempty():
    status, body = _voices("en")
    assert status == 200
    assert len(body["voices"]) > 0, "expected voices for locale=en"


def test_en_prefix_all_locales_start_with_en():
    _, body = _voices("en")
    for v in body["voices"]:
        assert v["locale"].startswith("en-"), f"unexpected locale {v['locale']!r} for locale=en"


def test_en_prefix_us_voices_are_whitelisted():
    _, body = _voices("en")
    us_names = _friendly_names(body["voices"], "en-US")
    assert us_names == ["Andrew", "Ava", "Brian", "Emma", "Jenny"], \
        f"en-US voices not whitelisted correctly: {us_names}"


def test_en_prefix_gb_voices_are_whitelisted():
    _, body = _voices("en")
    gb_names = _friendly_names(body["voices"], "en-GB")
    assert gb_names == ["Ryan", "Sonia"], \
        f"en-GB voices not whitelisted correctly: {gb_names}"


def test_en_prefix_other_locales_unfiltered():
    _, body = _voices("en")
    other_locales = {v["locale"] for v in body["voices"] if v["locale"] not in ("en-US", "en-GB")}
    assert other_locales, "expected voices from en-* locales other than en-US and en-GB"


def test_en_us_exact_returns_whitelisted_voices():
    status, body = _voices("en-US")
    assert status == 200
    names = _friendly_names(body["voices"])
    assert names == ["Andrew", "Ava", "Brian", "Emma", "Jenny"], \
        f"en-US voices wrong: {names}"


def test_en_us_exact_all_locales_correct():
    _, body = _voices("en-US")
    for v in body["voices"]:
        assert v["locale"] == "en-US", f"unexpected locale {v['locale']!r} for locale=en-US"


def test_en_in_exact_returns_nonempty():
    status, body = _voices("en-IN")
    assert status == 200
    assert len(body["voices"]) > 0, "expected voices for locale=en-IN"


def test_en_in_exact_all_locales_correct():
    _, body = _voices("en-IN")
    for v in body["voices"]:
        assert v["locale"] == "en-IN", f"unexpected locale {v['locale']!r} for locale=en-IN"


def test_it_prefix_returns_nonempty():
    status, body = _voices("it")
    assert status == 200
    assert len(body["voices"]) > 0, "expected voices for locale=it"


def test_it_prefix_all_locales_start_with_it():
    _, body = _voices("it")
    for v in body["voices"]:
        assert v["locale"].startswith("it-"), f"unexpected locale {v['locale']!r} for locale=it"


def test_it_it_exact_returns_nonempty():
    status, body = _voices("it-IT")
    assert status == 200
    assert len(body["voices"]) > 0, "expected voices for locale=it-IT"


def test_it_it_exact_all_locales_correct():
    _, body = _voices("it-IT")
    for v in body["voices"]:
        assert v["locale"] == "it-IT", f"unexpected locale {v['locale']!r} for locale=it-IT"


def test_unknown_language_prefix_returns_empty():
    status, body = _voices("qq")
    assert status == 200
    assert body["voices"] == [], f"expected empty voices for locale=qq, got {body['voices']}"


def test_unknown_exact_locale_returns_empty():
    status, body = _voices("qq-RR")
    assert status == 200
    assert body["voices"] == [], f"expected empty voices for locale=qq-RR"


def test_numeric_locale_returns_empty():
    status, body = _voices("123")
    assert status == 200
    assert body["voices"] == [], f"expected empty voices for locale=123"


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
