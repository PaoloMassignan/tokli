"""SPEC 016 in a real browser (AC-UI-2, UI-003, UI-008, UI-009, AC-UI-4).

Runs with Playwright and headless Chromium when ``RUN_BROWSER_TESTS=1`` (one CI job, ADR 0006).
Tokli is real; only the upstream is faked, and the dashboard reads the data that real proxied
traffic produced.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

if os.environ.get("RUN_BROWSER_TESTS") != "1":
    pytest.skip("set RUN_BROWSER_TESTS=1 (needs Playwright and Chromium)", allow_module_level=True)

from playwright.sync_api import Page, sync_playwright

from tests.integration.servers import FakeUpstream, Tokli, make_config, run_tokli, serve
from tests.integration.test_metrics_api import traffic, usage_upstream
from tokli.compression.registry import REGISTRY

TABS = ("overview", "compressors", "requests")


@pytest.fixture(scope="module")
def tokli(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Tokli]:
    upstream = FakeUpstream()
    usage_upstream(upstream)
    with serve(upstream.app()) as upstream_url:
        upstream.url = upstream_url
        config = make_config(tmp_path_factory.mktemp("ui"), upstream_url)
        with run_tokli(config) as t:
            traffic(t)
            yield t


@pytest.fixture
def page(tokli: Tokli) -> Iterator[Page]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(tokli.url + "/tokli/")
        page.wait_for_selector("#cards .figure")
        yield page
        assert errors == [], errors
        browser.close()


def show(page: Page, tab: str) -> None:
    page.click(f'[data-tab="{tab}"]')
    page.wait_for_selector(f'section[data-panel="{tab}"]:not([hidden]) [data-loaded]')


def test_ui_renders_method_labels(page: Page) -> None:
    """AC-UI-2 / UI-002: every token number has its method label; unknown values show a reason."""
    checked = 0
    for tab in TABS:
        show(page, tab)
        figures: list[dict[str, Any]] = page.eval_on_selector_all(
            f'section[data-panel="{tab}"] .figure',
            """els => els.map(e => ({
                num: (e.querySelector('.num') || {}).textContent || '',
                method: (e.querySelector('.method') || {}).textContent || '',
                reason: (e.querySelector('.reason') || {}).textContent || '',
            }))""",
        )
        for figure in figures:
            if any(ch.isdigit() for ch in figure["num"]):
                assert figure["method"].strip() in ("exact", "calibrated", "estimate") or (
                    figure["method"].startswith("estimate ·")
                ), figure
            else:
                assert figure["num"].strip() == "—" and figure["reason"].strip(), figure
            checked += 1
    assert checked >= 10


def test_ui_money_shows_dash_with_reason(page: Page) -> None:
    """X1 / API-012: no price book yet, so money is "—" with the reason."""
    money = page.locator('[data-card="cost"] .figure')
    assert money.locator(".num").inner_text().strip() == "—"
    assert "no_price_book" in money.locator(".reason").inner_text()


def test_ui_shows_kind_equivalence_and_assumptions(page: Page) -> None:
    """UI-003 (without evaluation status in S3)."""
    show(page, "compressors")
    table = page.locator("#compressors-table").inner_text()
    spec = REGISTRY[0].spec
    assert "lossless · structural" in table
    for assumption in spec.assumptions:
        assert assumption in table
    assert page.locator("#compressors-table .badge.lossless").count() >= 1


def test_ui_overhead_target_is_reference_line(page: Page) -> None:
    """UI-009: the target is a labelled reference line, never a pass/fail mark."""
    chart = page.locator("svg#overhead-chart")
    assert chart.locator("line.target").count() == 1
    assert "target (not a limit)" in chart.inner_html()
    text = page.locator('section[data-panel="overview"]').inner_text().lower()
    assert "pass" not in text and "fail" not in text


def test_ui_request_detail_renders_trace(page: Page) -> None:
    show(page, "requests")
    page.locator("#requests-table tbody tr").first.click()
    detail = page.locator("#request-detail")
    detail.wait_for()
    for span in ("route", "upstream", "usage"):
        assert span in detail.inner_text()


def test_ui_usable_at_360px(page: Page) -> None:
    """UI-008: no horizontal page scroll at 360 px; wide tables scroll inside their box."""
    page.set_viewport_size({"width": 360, "height": 740})
    for tab in TABS:
        show(page, tab)
        width = page.evaluate("document.documentElement.scrollWidth")
        assert width <= 360, (tab, width)


def test_ui_assets_load_offline_in_browser(tokli: Tokli, tmp_path: Path) -> None:
    """AC-UI-4: with every non-loopback request blocked, the dashboard still loads fully."""
    blocked: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def guard(route: Any) -> None:
            url = route.request.url
            if url.startswith(tokli.url):
                route.continue_()
            else:
                blocked.append(url)
                route.abort()

        page.route("**/*", guard)
        page.goto(tokli.url + "/tokli/")
        page.wait_for_selector("#cards .figure")
        browser.close()
    assert blocked == []
