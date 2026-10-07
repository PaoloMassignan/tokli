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


MONEY_METHODS = (
    "by where the saving sits in the cache",
    "by the request's average price mix",
    "assumes no cache",
)


def test_ui_cost_card_shows_estimate_range_and_method(page: Page) -> None:
    """UI-013 / UI-002: the card stays compact and Help carries its full provenance."""
    card = page.locator('[data-card="cost"]')
    money = card.locator(".money")
    assert money.locator(".num").inner_text().strip().startswith("$")
    low_high = money.locator(".range").inner_text()
    assert low_high.count("$") == 2 and "\u2013" in low_high
    assert money.locator(".money-method, .basis, .price-book").count() == 0

    page.get_by_role("button", name="Help").click()
    help_money = page.locator("#page-help .help-money .money")
    assert help_money.locator(".money-method").inner_text().strip() in MONEY_METHODS
    assert help_money.locator(".basis").inner_text().strip() in (
        "estimated money saved",
        "value at API prices",
    )
    assert "price book" in help_money.inner_text()


def test_ui_compressor_money_column(page: Page) -> None:
    """UI-013: the Compressors page shows each compressor's money saved with its method."""
    show(page, "compressors")
    table = page.locator("#compressors-table")
    assert "Money saved" in table.locator("thead").inner_text()
    summaries = table.locator(".compressor-detail > summary .money").all_inner_texts()
    assert summaries and any(cell.strip().startswith("$") for cell in summaries)
    assert all("price book" not in cell for cell in summaries)
    first = table.locator("tbody tr").first
    first.locator("summary").click()
    detail = first.locator(".compressor-money-detail .money").inner_text()
    assert "estimate" in detail and "price book" in detail
    assert "estimated money saved" in detail or "value at API prices" in detail


def test_ui_shows_kind_equivalence_and_assumptions(page: Page) -> None:
    """UI-003 (without evaluation status in S3)."""
    show(page, "compressors")
    first = page.locator("#compressors-table tbody tr").first
    first.locator("summary").click()
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
    page.locator("#requests-table tbody tr").first.get_by_role("button", name="View").click()
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
        item = page.locator('[data-compressor="json_minify"]')
        item.locator("details.evidence summary").click()
        card = item.inner_text()
        browser.close()
    assert "lossless · structural" in card
    assert "reads_minified_json" in card
    assert "smoke · no measurable damage · claude-opus-5-5 · 2026-10-03" in card


def test_ui_policy_explanations_text(fresh: Tokli) -> None:
    """UI-010 (after S4 SCR-001): the kinds explained in these words."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_settings(browser, fresh)
        page.get_by_role("button", name="Help").click()
        text = page.locator("#page-help").inner_text()
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


# -- S6.5: plain hierarchy, reachable detail and visual-review artifacts ----------------------


def test_ui_filters_are_only_on_metrics_pages(page: Page) -> None:
    """S6.5 P1: metrics filters are contextual and keep their values between metrics pages."""
    filters = page.locator("#filters")
    assert filters.is_visible()
    filters.locator('[name="provider"]').fill("anthropic")
    show(page, "compressors")
    assert filters.is_visible()
    assert filters.locator('[name="provider"]').input_value() == "anthropic"
    for tab in ("requests", "settings"):
        show(page, tab)
        assert not filters.is_visible()


def test_ui_overview_prioritises_savings_and_keeps_totals_reachable(page: Page) -> None:
    """S6.5 P2: the first figures answer saving; input totals remain one disclosure away."""
    primary = page.locator("#primary-metrics")
    assert primary.locator('[data-card="saved"]').count() == 1
    assert primary.locator('[data-card="cost"]').count() == 1
    assert primary.locator('[data-card="saving_pct"]').count() == 1
    breakdown = page.locator("#overview-breakdown")
    assert not breakdown.get_attribute("open")
    for key in ("requests", "original", "forwarded"):
        assert breakdown.locator(f'[data-card="{key}"]').count() == 1
    breakdown.locator("summary").click()
    assert breakdown.locator(".legend").count() == 0


def test_ui_timeseries_values_show_methods(page: Page) -> None:
    """UI-002 / S6.5 F8: every reachable saved-token bucket has method or unavailable reason."""
    details = page.locator("#timeseries-values")
    details.locator("summary").click()
    figures = details.locator(".figure")
    assert figures.count() >= 1
    for i in range(figures.count()):
        item = figures.nth(i)
        assert item.locator(".method, .reason").inner_text().strip()


def test_ui_all_overhead_groups_and_percentiles_are_reachable(page: Page) -> None:
    """UI-009 / TC-013: all groups expose n, p50, p95, p99 and max without pass/fail."""
    details = page.locator("#overhead-values")
    details.locator("summary").click()
    headings = details.locator("thead").inner_text()
    for label in ("Policy", "Configuration", "Requests", "p50", "p95", "p99", "Max"):
        assert label in headings
    assert details.locator("tbody tr").count() >= 5
    assert "pass" not in details.inner_text().lower()
    assert "fail" not in details.inner_text().lower()


def test_ui_compressor_summary_and_full_details(page: Page) -> None:
    """UI-009 / UI-013: compact comparison rows retain every detailed measurement and label."""
    show(page, "compressors")
    table = page.locator("#compressors-table")
    headings = table.locator("thead").inner_text()
    for label in ("Compressor", "On", "Kind", "Tokens saved", "Money saved", "Attention"):
        assert label in headings
    row = table.locator("tbody tr").first
    row.locator("summary").click()
    text = row.inner_text()
    for label in (
        "Effective budget",
        "Cost class",
        "Average latency",
        "Skipped for budget",
        "Considered",
        "Applicable",
        "Accepted",
        "Tokens processed",
        "Total latency",
        "Assumptions",
    ):
        assert label in text
    money_text = row.locator(".compressor-money-detail .money").inner_text()
    assert "estimate" in money_text
    assert "price book" in money_text
    assert "estimated money saved" in money_text or "value at API prices" in money_text


def test_ui_recent_requests_show_provider_and_native_detail_button(page: Page) -> None:
    """SPEC 016 / S6.5 P4: provider is visible and detail uses a keyboard-native button."""
    show(page, "requests")
    table = page.locator("#requests-table")
    assert "Provider" in table.locator("thead").inner_text()
    first = table.locator("tbody tr").first
    assert first.locator("td").nth(1).inner_text().strip()
    button = first.get_by_role("button", name="View")
    button.focus()
    page.keyboard.press("Space")
    page.locator("#request-detail").wait_for()
    assert button.get_attribute("aria-current") == "true"
    detail = page.locator("#request-detail").inner_text()
    assert first.locator("td").nth(1).inner_text().strip() in detail


def test_ui_recent_request_money_is_compact_with_descriptions_in_help(page: Page) -> None:
    """Gate 2 feedback: request rows retain estimate/range without verbose provenance labels."""
    show(page, "requests")
    money = page.locator("#requests-table tbody tr").first.locator("td").nth(7)
    assert money.locator(".num").inner_text().strip().startswith("$")
    assert money.locator(".label").inner_text().strip() == "estimate"
    assert money.locator(".range").inner_text().count("$") == 2
    assert money.locator(".money-method, .basis, .price-book").count() == 0

    page.get_by_role("button", name="Help").click()
    help_text = page.locator("#page-help").inner_text()
    for label in ("money range", "money method", "basis", "price book"):
        assert label in help_text


def test_ui_compressor_columns_share_one_alignment_grid(page: Page) -> None:
    """Gate 2 feedback: headers and compact compressor values use the same column geometry."""
    show(page, "compressors")
    table = page.locator("#compressors-table")
    header = table.locator("thead tr")
    summary = table.locator("tbody tr").first.locator("summary")
    assert header.evaluate("e => getComputedStyle(e).gridTemplateColumns") == summary.evaluate(
        "e => getComputedStyle(e).gridTemplateColumns"
    )
    for index in (3, 4):
        assert (
            header.locator("th").nth(index).evaluate("e => getComputedStyle(e).textAlign")
            == "right"
        )


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_ui_focus_is_visible_in_both_colour_schemes(page: Page, scheme: str) -> None:
    """UI-008 / S6.5 F4: keyboard focus has an explicit visible indicator in both themes."""
    page.emulate_media(color_scheme=scheme)
    page.locator('[data-tab="overview"]').focus()
    style = page.locator('[data-tab="overview"]').evaluate(
        "e => ({style: getComputedStyle(e).outlineStyle, width: getComputedStyle(e).outlineWidth})"
    )
    assert style["style"] != "none"
    assert float(style["width"].removesuffix("px")) >= 2


def test_ui_settings_primary_controls_and_disclosures(page: Page) -> None:
    """UI-003/UI-004/UI-010: primary controls precede exact reference text and evidence."""
    show(page, "settings")
    panel = page.locator('section[data-panel="settings"]')
    assert panel.locator("#lossless-only").is_visible()
    card = panel.locator('[data-compressor="json_minify"]')
    assert card.get_by_text("Enabled", exact=True).count() == 1
    evidence = card.locator("details.evidence")
    assert not evidence.get_attribute("open")
    evidence.locator("summary").click()
    assert "Assumptions" in evidence.inner_text()


def test_ui_help_reveals_contextual_field_descriptions(page: Page) -> None:
    """Gate 2 feedback: explanatory copy is hidden until the single Help button is used."""
    button = page.get_by_role("button", name="Help")
    help_panel = page.locator("#page-help")
    assert button.get_attribute("aria-expanded") == "false"
    assert not help_panel.is_visible()
    button.click()
    assert help_panel.is_visible()
    assert "counted by the provider" in help_panel.inner_text()
    button.click()
    assert not help_panel.is_visible()

    show(page, "compressors")
    assert "credited only with what it saved" not in page.locator("#compressors-body").inner_text()
    button.click()
    assert "credited only with what it saved" in help_panel.inner_text()

    show(page, "settings")
    settings_panel = page.locator('section[data-panel="settings"]')
    assert "Keeps all information in the request" not in settings_panel.inner_text()
    button.click()
    assert "Keeps all information in the request" in help_panel.inner_text()


def test_ui_screenshots(tokli: Tokli) -> None:
    """S6.5: optionally write the 16 human-review screenshots; never commit them."""
    configured = os.environ.get("UI_SCREENSHOTS_DIR")
    if not configured:
        pytest.skip("set UI_SCREENSHOTS_DIR to write S6.5 review screenshots")
    output = Path(configured)
    output.mkdir(parents=True, exist_ok=True)
    sizes = ((1280, 900), (360, 740))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            for width, height in sizes:
                context = browser.new_context(
                    viewport={"width": width, "height": height}, color_scheme=scheme
                )
                shot = context.new_page()
                shot.goto(tokli.url + "/tokli/")
                shot.wait_for_selector("#primary-metrics .figure")
                for tab in TABS:
                    if tab != "overview":
                        show(shot, tab)
                    shot.screenshot(
                        path=output / f"{tab}-{width}x{height}-{scheme}.png",
                        animations="disabled",
                    )
                context.close()
        browser.close()
    assert len(list(output.glob("*.png"))) == 16
