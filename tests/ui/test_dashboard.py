"""SPEC 016 in a real browser (AC-UI-2, UI-003, UI-008, UI-009, AC-UI-4).

Runs with Playwright and headless Chromium when ``RUN_BROWSER_TESTS=1`` (one CI job, ADR 0006).
Tokli is real; only the upstream is faked, and the dashboard reads the data that real proxied
traffic produced.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

if os.environ.get("RUN_BROWSER_TESTS") != "1":
    pytest.skip("set RUN_BROWSER_TESTS=1 (needs Playwright and Chromium)", allow_module_level=True)

import httpx
from playwright.sync_api import Page, sync_playwright

from tests.integration.servers import FakeUpstream, Tokli, make_config, run_tokli, serve
from tests.integration.test_metrics_api import traffic, usage_upstream
from tokli.compression.registry import REGISTRY

TABS = ("overview", "compressors", "requests", "settings")


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


# -- S4: settings (UI-003…UI-005, UI-010, AC-UI-3) and savings per compressor -----------------


@pytest.fixture
def fresh(tmp_path: Path) -> Iterator[Tokli]:
    """A Tokli of its own, so settings changes do not leak into other tests."""
    upstream = FakeUpstream()
    usage_upstream(upstream)
    with serve(upstream.app()) as upstream_url:
        upstream.url = upstream_url
        with run_tokli(make_config(tmp_path, upstream_url)) as t:
            traffic(t)
            yield t


def open_settings(browser: Any, tokli: Tokli) -> Page:
    page = browser.new_page()
    page.goto(tokli.url + "/tokli/")
    page.wait_for_selector("#cards .figure")
    page.click('[data-tab="settings"]')
    page.wait_for_selector('section[data-panel="settings"]:not([hidden]) [data-loaded]')
    return page


def test_ui_toggle_patches_config(fresh: Tokli) -> None:
    """AC-UI-3: a toggle issues PATCH /tokli/api/config and the page re-renders from the
    response."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_settings(browser, fresh)
        toggle = page.locator('[data-compressor="duplicate_tool_results"] input[type="checkbox"]')
        assert toggle.is_checked()  # on by default since E11
        with page.expect_response(
            lambda r: r.url.endswith("/tokli/api/config") and r.request.method == "PATCH"
        ) as info:
            toggle.click()
        assert info.value.status == 200
        page.wait_for_selector(
            '[data-compressor="duplicate_tool_results"] input[type="checkbox"]:not(:checked)'
        )
        hash_after = page.locator("#config-hash").inner_text()
        browser.close()
    assert (
        fresh.services.config.reload().values["compressors.duplicate_tool_results.enabled"] is False
    )
    assert hash_after.strip() == fresh.services.config.reload().config_hash[:12]


def test_ui_shows_equivalence_assumptions_and_eval_status(fresh: Tokli) -> None:
    """UI-003: kind and equivalence, assumptions, and the evaluation record's status."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_settings(browser, fresh)
        card = page.locator('[data-compressor="json_minify"]').inner_text()
        browser.close()
    assert "lossless · structural" in card
    assert "reads_minified_json" in card
    assert "smoke · no measurable damage · claude-opus-5-5 · 2026-10-03" in card


def test_ui_policy_explanations_text(fresh: Tokli) -> None:
    """UI-010 (after S4 SCR-001): the kinds explained in these words."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_settings(browser, fresh)
        text = page.locator('section[data-panel="settings"]').inner_text()
        browser.close()
    assert (
        "Keeps all information in the request: exactly, structurally (e.g. JSON whitespace), or "
        "by reference to an identical earlier tool result. This does not guarantee identical model "
        "behaviour. Defaults are chosen from evaluations." in text
    )
    assert (
        "Drops information: selective ones keep a declared part verbatim, lossy ones do not. "
        "Enable them only with evidence that your tasks are not affected." in text
    )


def test_ui_lossless_only_shortcut_switches_off_non_lossless(fresh: Tokli) -> None:
    """UI-004 after S4 SCR-001. No non-lossless compressor ships yet, so the registry answer
    is extended in the browser with one (data only, UI-001) and the PATCH is captured."""
    patches: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def compressors(route: Any) -> None:
            response = route.fetch()
            body = response.json()
            extra = dict(
                body["compressors"][0],
                id="zz_drop",
                name="Synthetic dropper",
                kind="LOSSY",
                equivalence="none",
                enabled=True,
                evaluation={"status": "none"},
            )
            body["compressors"].append(extra)
            route.fulfill(response=response, json=body)

        def config(route: Any) -> None:
            if route.request.method == "PATCH":
                patches.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(json=json.loads(httpx.get(fresh.url + "/tokli/api/config").text))
            else:
                route.continue_()

        page.route("**/tokli/api/compressors", compressors)
        page.route("**/tokli/api/config", config)
        page.goto(fresh.url + "/tokli/")
        page.wait_for_selector("#cards .figure")
        page.click('[data-tab="settings"]')
        page.wait_for_selector('section[data-panel="settings"]:not([hidden]) [data-loaded]')
        assert "drops information" in page.locator('[data-compressor="zz_drop"]').inner_text()
        page.click("#lossless-only")
        page.wait_for_timeout(300)
        browser.close()
    assert patches == [{"changes": {"compressors.zz_drop.enabled": False}}]


def test_ui_locked_settings_show_source(tmp_path: Path) -> None:
    """UI-005: a key pinned by env is disabled and shows its source."""
    upstream = FakeUpstream()
    with serve(upstream.app()) as upstream_url:
        config = make_config(
            tmp_path, upstream_url, env={"TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED": "true"}
        )
        with run_tokli(config) as t, sync_playwright() as p:
            browser = p.chromium.launch()
            page = open_settings(browser, t)
            card = page.locator('[data-compressor="json_minify"]')
            assert card.locator('input[type="checkbox"]').is_disabled()
            assert "locked by env:TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED" in card.inner_text()
            browser.close()


def test_ui_overview_shows_savings_per_compressor(page: Page) -> None:
    """S4 (P10 as answered): saved tokens per compressor, each with its method."""
    rows = page.locator("#per-compressor .figure")
    assert rows.count() >= 1
    text = page.locator("#per-compressor").inner_text()
    assert "JSON minify" in text


# -- S8a-1: the verbatim opt-in (UI-012, S8a SCR-001) ------------------------------------------


def test_ui_verbatim_opt_in_toggle(fresh: Tokli) -> None:
    """UI-012: a compressor that declares `apply_to_verbatim_tools` gets a second toggle,
    labelled with the effective verbatim tools and the warning; others do not."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_settings(browser, fresh)
        card = page.locator('[data-compressor="log_filter"]')
        toggle = card.locator('input[data-toggle="verbatim"]')
        assert not toggle.is_checked()
        text = card.inner_text()
        assert "Also on Read, Bash, shell, shell_command, container.exec" in text
        assert (
            "These tools' output is often copied back exactly by the agent (for example as an "
            "edit anchor). Changing it can make the agent's next tool call fail." in text
        )
        assert (
            page.locator('[data-compressor="json_minify"] input[data-toggle="verbatim"]').count()
            == 0
        )
        with page.expect_response(
            lambda r: r.url.endswith("/tokli/api/config") and r.request.method == "PATCH"
        ) as info:
            toggle.click()
        assert info.value.status == 200
        page.wait_for_selector(
            '[data-compressor="log_filter"] input[data-toggle="verbatim"]:checked'
        )
        browser.close()
    values = fresh.services.config.reload().values
    assert values["compressors.log_filter.apply_to_verbatim_tools"] is True
    assert values["compressors.log_filter.enabled"] is False  # the two toggles are independent
