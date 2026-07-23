"""Efficiency S1+E1 — pin the source registry and the parallel fetch phase.

All offline: fake fetchers only, no network, no Claude."""

import inspect
import threading
import time

import digest


EXPECTED_KEYS = [
    "sec_filings", "news_articles", "market_data", "macro_data", "earnings",
    "pacer_entries", "rating_actions", "fund_results",
    "research_articles", "treasury_auctions", "cot_data", "fed_bs",
    "bank_failures", "ishares_oas", "cliffwater_bdc",
]


# --- registry shape ---

def test_registry_keys_pinned():
    assert [entry[0] for entry in digest.SOURCE_FETCHERS] == EXPECTED_KEYS


def test_registry_entries_well_formed():
    for key, start_msg, fail_label, fetch in digest.SOURCE_FETCHERS:
        assert isinstance(key, str) and key
        assert start_msg.endswith("...")
        assert isinstance(fail_label, str) and fail_label
        assert callable(fetch)


def test_registry_keys_route_to_prompt_kwargs():
    # Every registry key must be a summarize_with_claude keyword — a misnamed
    # registry key would silently drop that source from the digest prompt.
    # Exceptions (routed differently by design): news_articles (pre-rendered
    # HTML section, not prompt material); cliffwater_bdc (its row is merged
    # into market_data before summarize — see main()).
    prompt_kwargs = set(inspect.signature(digest.summarize_with_claude).parameters)
    for key in EXPECTED_KEYS:
        if key not in ("news_articles", "cliffwater_bdc"):
            assert key in prompt_kwargs, f"registry key {key!r} not a prompt kwarg"


# --- _fetch_all_sources (E1) ---

def _fake_registry():
    def ok_a():
        print("a fetched 3 items")
        return ["a1", "a2", "a3"]

    def ok_b():
        return ["b1"]

    def boom():
        raise RuntimeError("connection reset")

    return [
        ("alpha", "Fetching alpha...", "Alpha fetch", ok_a),
        ("beta", "Fetching beta...", "Beta fetch", ok_b),
        ("gamma", "Fetching gamma...", "Gamma fetch", boom),
    ]


def test_fetch_all_sources_results_and_isolation(capsys):
    results = digest._fetch_all_sources(registry=_fake_registry(), max_workers=2)
    assert results["alpha"] == ["a1", "a2", "a3"]
    assert results["beta"] == ["b1"]
    assert results["gamma"] == []  # failure isolated to []

    out = capsys.readouterr().out
    assert "Fetching alpha..." in out
    assert "a fetched 3 items" in out           # worker prints surfaced
    assert "Gamma fetch failed: connection reset" in out
    assert "Fetch phase:" in out                # timing line


def test_fetch_all_sources_buffers_output_per_source(capsys):
    # Two slow, chatty fetchers running concurrently: each source's lines must
    # come out as one contiguous block (header immediately followed by its own
    # output), not interleaved with the other's.
    def chatty(name):
        def fetch():
            for i in range(3):
                print(f"{name} line {i}")
                time.sleep(0.02)
            return [name]
        return fetch

    registry = [
        ("one", "Fetching one...", "One fetch", chatty("ONE")),
        ("two", "Fetching two...", "Two fetch", chatty("TWO")),
    ]
    results = digest._fetch_all_sources(registry=registry, max_workers=2)
    assert results == {"one": ["ONE"], "two": ["TWO"]}

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    one_hdr = lines.index("Fetching one...")
    assert lines[one_hdr + 1:one_hdr + 4] == ["ONE line 0", "ONE line 1", "ONE line 2"]
    two_hdr = lines.index("Fetching two...")
    assert lines[two_hdr + 1:two_hdr + 4] == ["TWO line 0", "TWO line 1", "TWO line 2"]


def test_fetch_all_sources_restores_stdout():
    import sys
    before = sys.stdout
    digest._fetch_all_sources(registry=_fake_registry(), max_workers=2)
    assert sys.stdout is before


# --- _ThreadLocalStdout ---

def test_thread_local_stdout_isolates_threads():
    import io

    default = io.StringIO()
    proxy = digest._ThreadLocalStdout(default)

    captured = {}

    def worker(name):
        buf = io.StringIO()
        proxy.register(buf)
        try:
            for i in range(20):
                proxy.write(f"{name}:{i}\n")
        finally:
            proxy.unregister()
            captured[name] = buf.getvalue()

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("x", "y")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert captured["x"] == "".join(f"x:{i}\n" for i in range(20))
    assert captured["y"] == "".join(f"y:{i}\n" for i in range(20))
    # unregistered (main) thread falls through to the default stream
    proxy.write("main\n")
    assert default.getvalue() == "main\n"
