"""Metrics use cases (SPEC 013 TC-013, TC-015, TC-016; SPEC 015 API-010…API-012).

Stored figures are estimates plus the provider's usage and the per-request ``k``. Calibration is
applied here, per request, at query time (TOKLI_TELEMETRY_AND_COST §1). A total is labelled with
the weakest method among its parts; when that is ``estimate`` it carries the share of the total
that has the stronger method (TC-015).
"""

from __future__ import annotations

import bisect
import itertools
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tokli.app import money
from tokli.pricing.book import PriceTable
from tokli.telemetry import queries
from tokli.tokens.calibration import in_range

API_VERSION = 1
VISION_TARGET_MS = 25.0  # TOKLI_VISION.md: p95 overhead target, a reference, never a gate
DEFAULT_DAYS = 7
MAX_LIMIT = 500
MAX_BUCKETS = 2000
KINDS = ("LOSSLESS", "SELECTIVE", "LOSSY", "UNKNOWN")
SIZE_BUCKETS = (("lt_10k", 10_000), ("10k_50k", 50_000), ("50k_200k", 200_000))
_RANK = {"exact": 0, "calibrated": 1, "estimate": 2}
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
# Flag "latency without benefit" (TOKLI_TELEMETRY_AND_COST §3, TC-016).
FLAG_ZERO_BENEFIT, FLAG_AVG_MS, FLAG_MIN_APPLICABLE = 0.9, 1.0, 100
# Flag "not applying" (TC-021, S8h P3; POLICY, provisional).
NOT_APPLYING_MIN_CONSIDERED, FORMAT_REASON_SHARE = 200, 0.5
FORMAT_REASONS = frozenset(
    {
        "not_applicable(nonstandard_numbering)",
        "not_applicable(not_json)",
        "not_applicable(too_few_grep_lines)",
        "not_applicable(too_few_leveled_lines)",
    }
)

Figure = tuple[int, str]  # (value, method)


class InvalidParameters(Exception):
    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__(", ".join(sorted(fields)))
        self.fields = fields


@dataclass(frozen=True)
class Filters:
    start: datetime
    end: datetime
    tz: ZoneInfo
    bucket: str = "hour"
    provider: str | None = None
    model: str | None = None
    compressor: str | None = None
    kind: str | None = None
    limit: int = 50
    cursor: str | None = None


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("needs an offset, e.g. Z or +02:00")
    return parsed


def parse_filters(params: Mapping[str, str], now: datetime | None = None) -> Filters:
    """Validates the query parameters (API-003, API-010); collects every error."""
    errors: dict[str, str] = {}
    end = now or datetime.now(UTC)
    start = end - timedelta(days=DEFAULT_DAYS)
    for name in ("from", "to"):
        if name in params:
            try:
                moment = _instant(params[name])
            except ValueError as exc:
                errors[name] = f"not an ISO-8601 instant with offset: {exc}"
                continue
            if name == "from":
                start = moment
            else:
                end = moment
    if "from" not in errors and "to" not in errors and end <= start:
        errors["to"] = "must be later than 'from'"
    tz = ZoneInfo("UTC")
    if "tz" in params:
        try:
            tz = ZoneInfo(params["tz"])
        except (ZoneInfoNotFoundError, ValueError):
            errors["tz"] = "unknown IANA time zone"
    bucket = params.get("bucket", "hour")
    if bucket not in ("hour", "day"):
        errors["bucket"] = "must be 'hour' or 'day'"
    kind = params.get("kind")
    if kind is not None and kind not in KINDS:
        errors["kind"] = "must be one of " + ", ".join(KINDS)
    limit = 50
    if "limit" in params:
        try:
            limit = int(params["limit"])
        except ValueError:
            limit = 0
        if not 1 <= limit <= MAX_LIMIT:
            errors["limit"] = f"must be an integer from 1 to {MAX_LIMIT}"
    cursor = params.get("cursor")
    if cursor is not None and not _ULID.match(cursor):
        errors["cursor"] = "must be a request id"
    if errors:
        raise InvalidParameters(errors)
    return Filters(
        start=start,
        end=end,
        tz=tz,
        bucket=bucket,
        provider=params.get("provider"),
        model=params.get("model"),
        compressor=params.get("compressor"),
        kind=kind,
        limit=limit,
        cursor=cursor,
    )


# -- figures ----------------------------------------------------------------------------------


def _weakest(*methods: str) -> str:
    return max(methods, key=_RANK.__getitem__)


def _usage_total(row: Mapping[str, Any]) -> int | None:
    if row["usage_input"] is None:
        return None
    return int(
        row["usage_input"]
        + (row["usage_cache_read"] or 0)
        + (row["usage_cache_write_5m"] or 0)
        + (row["usage_cache_write_1h"] or 0)
    )


def _saving(row: Mapping[str, Any], raw: int) -> Figure:
    if row["outcome"] != "compressed":
        return 0, "exact"  # the forwarded bytes are the client's: nothing was saved
    k = row["calibration_k"]
    if in_range(k):
        return round(raw * k), "calibrated"
    return raw, "estimate"


def _raw_saving(row: Mapping[str, Any]) -> int:
    original, forwarded = row["est_original_tokens"], row["est_forwarded_tokens"]
    return original - forwarded if original is not None and forwarded is not None else 0


@dataclass(frozen=True)
class RequestFigures:
    forwarded: Figure | None
    saved: Figure | None
    original: Figure | None


def request_figures(row: Mapping[str, Any], raw_saving: int | None = None) -> RequestFigures:
    """Best figures of one request (TC-015). ``raw_saving`` restricts the saving (filters)."""
    if row["protocol"] is None:
        return RequestFigures(None, None, None)
    total = _usage_total(row)
    forwarded: Figure
    if total is not None:
        forwarded = (total, "exact")
    elif row["est_request_tokens_forwarded"] is not None:
        forwarded = (int(row["est_request_tokens_forwarded"]), "estimate")
    else:
        return RequestFigures(None, None, None)  # nothing was measured (e.g. an upstream error)
    saved = _saving(row, _raw_saving(row) if raw_saving is None else raw_saving)
    original = (forwarded[0] + saved[0], _weakest(forwarded[1], saved[1]))
    return RequestFigures(forwarded, saved, original)


def figure(value: Figure | None, reason: str = "not_measured") -> dict[str, Any]:
    if value is None:
        return {"value": None, "reason": reason}
    return {"value": value[0], "method": value[1]}


def total(parts: Iterable[Figure], share: str) -> dict[str, Any]:
    """Σ of the parts, labelled with the weakest method; ``share`` names the field that holds
    the stronger-method share when the label is ``estimate`` (TC-015)."""
    items = list(parts)
    if not items:
        return {"value": None, "reason": "no_data"}
    value = sum(v for v, _ in items)
    method = _weakest(*(m for _, m in items))
    result: dict[str, Any] = {"value": value, "method": method}
    if method == "estimate" and value:
        stronger = ("exact",) if share == "exact_share" else ("exact", "calibrated")
        result[share] = round(sum(v for v, m in items if m in stronger) / value, 4)
    return result


def _pct(saved: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    if saved["value"] is None or not original["value"]:
        return {"value": None, "reason": "no_data"}
    return {
        "value": round(100 * saved["value"] / original["value"], 2),
        "method": _weakest(saved["method"], original["method"]),
    }


def _rate(numerator: float, denominator: float, reason: str, digits: int = 4) -> dict[str, Any]:
    if not denominator:
        return {"value": None, "reason": reason}
    return {"value": round(numerator / denominator, digits)}


def _percentiles(values: list[float]) -> dict[str, Any]:
    """Nearest-rank percentiles (TC-013)."""
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)

    def rank(p: float) -> float:
        return round(ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)], 3)

    return {
        "n": len(ordered),
        "p50": rank(50),
        "p95": rank(95),
        "p99": rank(99),
        "max": round(ordered[-1], 3),
    }


def size_bucket(tokens: int | None) -> str:
    if tokens is None:
        return "unknown"
    for name, bound in SIZE_BUCKETS:
        if tokens < bound:
            return name
    return "gt_200k"


# -- the use cases ----------------------------------------------------------------------------


class MetricsQuery:
    """The metrics use cases over one telemetry database (read-only)."""

    def __init__(
        self, db_path: Path, *, budget_ms: float = 50.0, prices: PriceTable | None = None
    ) -> None:
        self._db_path = db_path
        self._budget_ms = budget_ms
        self._prices = prices

    # Selection shared by the endpoints: request rows in range and their stats rows, with the
    # provider/model filters, and the compressor/kind filters restricting the request set.

    def _select(
        self, filters: Filters
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        rows = [
            row
            for row in queries.requests_between(self._db_path, filters.start, filters.end)
            if (filters.provider is None or row["provider"] == filters.provider)
            and (filters.model is None or row["model"] == filters.model)
        ]
        stats: dict[str, list[dict[str, Any]]] = defaultdict(list)
        restricted = filters.compressor is not None or filters.kind is not None
        if not restricted:
            return rows, stats  # the stats rows are needed only to restrict or to attribute
        for stat in queries.stats_between(self._db_path, filters.start, filters.end):
            stats[stat["request_id"]].append(stat)
        if restricted:
            for request_id, items in list(stats.items()):
                stats[request_id] = [s for s in items if _matches(s, filters)]
            rows = [row for row in rows if stats.get(row["request_id"])]
        return rows, stats

    def _figures(
        self, row: Mapping[str, Any], stats: Mapping[str, list[dict[str, Any]]], filters: Filters
    ) -> RequestFigures:
        if filters.compressor is None and filters.kind is None:
            return request_figures(row)
        raw = sum(s["marginal_saved"] for s in stats.get(row["request_id"], ()))
        return request_figures(row, raw_saving=raw)

    def _range(self, filters: Filters) -> dict[str, str]:
        return {
            "from": filters.start.astimezone(UTC).isoformat(),
            "to": filters.end.astimezone(UTC).isoformat(),
            "tz": filters.tz.key,
        }

    @staticmethod
    def _totals(measured: list[RequestFigures]) -> dict[str, dict[str, Any]]:
        forwarded = total((f.forwarded for f in measured if f.forwarded), "exact_share")
        saved = total((f.saved for f in measured if f.saved), "calibrated_share")
        original = total((f.original for f in measured if f.original), "calibrated_share")
        return {"original": original, "forwarded": forwarded, "saved": saved}

    def summary(self, filters: Filters) -> dict[str, Any]:
        rows, stats = self._select(filters)
        figures = [self._figures(row, stats, filters) for row in rows]
        measured = [f for f in figures if f.forwarded is not None]
        tokens = self._totals(measured)
        tokens["saving_pct"] = _pct(tokens["saved"], tokens["original"])
        by_outcome: dict[str, int] = defaultdict(int)
        for row in rows:
            by_outcome[row["outcome"]] += 1
        return {
            "api_version": API_VERSION,
            "range": self._range(filters),
            "requests": {
                "total": len(rows),
                "measured": len(measured),
                "by_outcome": dict(sorted(by_outcome.items())),
            },
            "tokens": tokens,
            "overhead": self._overhead(rows),
            "cost": self._cost(rows, stats, filters),
        }

    # -- money (S6: TC-004…TC-006, TC-019, TC-020; API-013) -------------------------------------

    def _price(
        self, row: Mapping[str, Any], stats: Mapping[str, list[dict[str, Any]]], filters: Filters
    ) -> tuple[bool, money.PricedRequest | None]:
        """(measured, priced) for one request row, under the compressor/kind filters."""
        figures = self._figures(row, stats, filters)
        if figures.forwarded is None or figures.saved is None or self._prices is None:
            return figures.forwarded is not None, None
        restricted = filters.compressor is not None or filters.kind is not None
        if restricted:
            matching = stats.get(row["request_id"], [])
            raw = sum(s["marginal_saved"] for s in matching)
            split = money.split_of(matching)
        else:
            raw = _raw_saving(row)
            split = money.split_of([row])
        return True, money.price_request(self._prices, row, figures.saved[0], raw, split)

    def _cost(
        self,
        rows: list[dict[str, Any]],
        stats: Mapping[str, list[dict[str, Any]]],
        filters: Filters,
    ) -> dict[str, Any]:
        measured, priced = 0, []
        for row in rows:
            was_measured, result = self._price(row, stats, filters)
            measured += was_measured
            if result is not None:
                priced.append(result)
        figures = (
            money.money_block(priced, measured)
            if self._prices is not None
            else {
                name: money.unavailable("no_price_book")
                for name in ("forwarded", "saved", "original")
            }
        )
        ordered = sorted(rows, key=lambda r: r["ts_start"])
        hashes = [r["config_hash"] for r in ordered if r["config_hash"] is not None]
        return {
            **figures,
            "priced_requests": len(priced),
            "unpriced_requests": measured - len(priced),
            "caveats": {  # TC-020: cache rewrites Tokli does not deduct
                "history_rewritten_requests": sum(1 for r in rows if r["history_rewritten"]),
                "config_changes": sum(1 for a, b in itertools.pairwise(hashes) if a != b),
            },
        }

    def _request_cost(self, row: Mapping[str, Any]) -> dict[str, Any]:
        measured, priced = self._price(row, {}, _NO_FILTER)
        if self._prices is None:
            return {
                name: money.unavailable("no_price_book")
                for name in ("forwarded", "saved", "original")
            }
        return money.money_block([priced] if priced is not None else [], int(measured))

    @staticmethod
    def _overhead(rows: list[dict[str, Any]]) -> dict[str, Any]:
        """TC-013: distribution per (policy, config_hash) and size bucket; the target is a
        reference value, never a status."""
        groups: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
            lambda: {name: [] for name in (*(n for n, _ in SIZE_BUCKETS), "gt_200k", "unknown")}
        )
        for row in rows:
            if row["ms_tokli_overhead"] is None:
                continue
            group = groups[(row["policy"], row["config_hash"])]
            group[size_bucket(row["est_request_tokens_original"])].append(
                float(row["ms_tokli_overhead"])
            )
        return {
            "target": {"value": VISION_TARGET_MS, "unit": "ms", "kind": "target"},
            "groups": [
                {
                    "policy": policy,
                    "config_hash": config_hash,
                    "buckets": {name: _percentiles(v) for name, v in buckets.items()},
                }
                for (policy, config_hash), buckets in sorted(groups.items())
            ],
        }

    def timeseries(self, filters: Filters) -> dict[str, Any]:
        starts = _bucket_starts(filters)
        rows, stats = self._select(filters)
        per_bucket: list[list[dict[str, Any]]] = [[] for _ in starts]
        for row in rows:
            moment = datetime.fromisoformat(row["ts_start"])
            index = bisect.bisect_right(starts, moment) - 1
            if index >= 0:
                per_bucket[index].append(row)
        buckets = []
        for start, members in zip(starts, per_bucket, strict=True):
            figures = [self._figures(row, stats, filters) for row in members]
            totals = self._totals([f for f in figures if f.forwarded is not None])
            buckets.append(
                {
                    "start": start.astimezone(filters.tz).isoformat(),
                    "requests": len(members),
                    **totals,
                }
            )
        return {
            "api_version": API_VERSION,
            "range": self._range(filters),
            "bucket": filters.bucket,
            "buckets": buckets,
        }

    def compressors(self, filters: Filters) -> dict[str, Any]:
        groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for stat in queries.stats_with_request(self._db_path, filters.start, filters.end):
            if (
                (filters.provider is None or stat["provider"] == filters.provider)
                and (filters.model is None or stat["model"] == filters.model)
                and _matches(stat, filters)
            ):
                groups[stat["compressor_id"]].append((stat, stat))  # (request part, stats part)
        savings = {
            cid: total((_saving(row, s["marginal_saved"]) for row, s in pairs), "calibrated_share")
            for cid, pairs in groups.items()
        }
        overall = sum(s["value"] or 0 for s in savings.values())
        result = [
            {
                **self._compressor_row(cid, pairs, savings[cid], overall),
                "money_saved": self._compressor_money(pairs),
            }
            for cid, pairs in sorted(groups.items())
        ]
        return {
            "api_version": API_VERSION,
            "range": self._range(filters),
            "budget_ms": self._budget_ms,
            "compressors": result,
        }

    def _compressor_money(
        self, pairs: list[tuple[dict[str, Any], dict[str, Any]]]
    ) -> dict[str, Any]:
        """API-013 (P2): each compressor's money from its own split (TC-017)."""
        if self._prices is None:
            return money.unavailable("no_price_book")
        priced = []
        for row, stat in pairs:
            saved = _saving(row, stat["marginal_saved"])
            result = money.price_request(
                self._prices, row, saved[0], stat["marginal_saved"], money.split_of([stat])
            )
            if result is not None:
                priced.append(result)
        return money.saved_figure(priced, len(pairs))

    @staticmethod
    def _compressor_row(
        cid: str,
        pairs: list[tuple[dict[str, Any], dict[str, Any]]],
        saved: dict[str, Any],
        overall: int,
    ) -> dict[str, Any]:
        def s(name: str) -> int:
            return sum(stat[name] or 0 for _, stat in pairs)

        considered, applicable, accepted = s("considered"), s("applicable"), s("accepted")
        failed, skipped, raw = s("failed"), s("skipped_budget"), s("marginal_saved")
        ms_total = round(sum(stat["ms_total"] or 0.0 for _, stat in pairs), 3)
        known = [stat for _, stat in pairs if stat["tokens_in_accepted"] is not None]
        if known:
            avg_pct = _rate(
                100 * sum(st["marginal_saved"] for st in known),
                sum(st["tokens_in_accepted"] for st in known),
                "no_accepted_invocations",
                digits=2,
            )
        else:
            avg_pct = {"value": None, "reason": "not_recorded_before_schema_v3"}
        zero_benefit = _rate(applicable - accepted, applicable, "no_applicable_invocations")
        avg_ms = _rate(ms_total, applicable, "no_applicable_invocations", digits=3)
        flag = (
            applicable >= FLAG_MIN_APPLICABLE
            and (zero_benefit["value"] or 0) >= FLAG_ZERO_BENEFIT
            and (avg_ms["value"] or 0) >= FLAG_AVG_MS
        )
        return {
            "compressor_id": cid,
            "kind": pairs[0][1]["kind"],
            "considered": considered,
            "applicable": applicable,
            "accepted": accepted,
            "failed": failed,
            "skipped_budget": skipped,
            "tokens_in": {"value": s("tokens_in"), "method": "estimate"},
            "marginal_saved": saved,
            "share_of_saving": _rate(saved["value"] or 0, overall, "no_saving"),
            "avg_saving_pct_per_accepted": avg_pct,
            "zero_benefit_rate": zero_benefit,
            "failure_rate": _rate(failed, applicable, "no_applicable_invocations"),
            "skipped_budget_rate": _rate(skipped, considered, "not_considered"),
            "ms_total": ms_total,
            "avg_ms": avg_ms,
            "tokens_saved_per_ms": (
                {"value": round(raw / ms_total, 2), "method": "estimate"}
                if ms_total
                else {"value": None, "reason": "no_latency_recorded"}
            ),
            "latency_without_benefit": flag,
            "not_applying": _not_applying(pairs, considered, applicable),
        }

    def requests(self, limit: int, cursor: str | None) -> dict[str, Any]:
        rows = queries.recent_requests(self._db_path, limit + 1, cursor)
        page, more = rows[:limit], len(rows) > limit
        items = []
        for row in page:
            figures = request_figures(row)
            items.append(
                {
                    "request_id": row["request_id"],
                    "ts_start": row["ts_start"],
                    "provider": row["provider"],
                    "model": row["model"],
                    "stream": bool(row["stream"]),
                    "outcome": row["outcome"],
                    "reason": row["passthrough_reason"],
                    "status_code": row["status_code"],
                    "usage_source": row["usage_source"],
                    "overhead_ms": (
                        round(row["ms_tokli_overhead"], 3)
                        if row["ms_tokli_overhead"] is not None
                        else None
                    ),
                    "tokens": {
                        "original": figure(figures.original),
                        "forwarded": figure(figures.forwarded),
                        "saved": figure(figures.saved),
                    },
                    "cost": self._request_cost(row),
                }
            )
        return {
            "api_version": API_VERSION,
            "requests": items,
            "next_cursor": page[-1]["request_id"] if more and page else None,
        }


_NO_FILTER = Filters(
    start=datetime.min.replace(tzinfo=UTC), end=datetime.max.replace(tzinfo=UTC), tz=ZoneInfo("UTC")
)


def _not_applying(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]], considered: int, applicable: int
) -> dict[str, Any]:
    """TC-021: a compressor that does not apply to this traffic, with its main skip reason."""
    reasons: dict[str, int] = defaultdict(int)
    for _, stat in pairs:
        raw = stat.get("skip_reasons")
        for reason, n in (json.loads(raw) if isinstance(raw, str) else raw or {}).items():
            reasons[reason] += int(n)
    main = max(reasons, key=lambda r: (reasons[r], r)) if reasons else None
    format_share = (
        sum(n for r, n in reasons.items() if r in FORMAT_REASONS) / considered if considered else 0
    )
    flagged = (considered >= NOT_APPLYING_MIN_CONSIDERED and applicable == 0) or (
        format_share > FORMAT_REASON_SHARE
    )
    if not flagged:
        return {"flag": False, "reason": None}
    if format_share > FORMAT_REASON_SHARE:
        main = max((r for r in reasons if r in FORMAT_REASONS), key=lambda r: (reasons[r], r))
    return {"flag": True, "reason": main}


def _matches(stat: Mapping[str, Any], filters: Filters) -> bool:
    return (filters.compressor is None or stat["compressor_id"] == filters.compressor) and (
        filters.kind is None or stat["kind"] == filters.kind
    )


def _bucket_starts(filters: Filters) -> list[datetime]:
    """Bucket boundaries in UTC, aligned to local hours or local midnights of ``tz`` (DST-safe:
    days step by calendar date, not by 24 hours)."""
    tz = filters.tz
    local = filters.start.astimezone(tz)
    starts: list[datetime] = []
    if filters.bucket == "day":
        day = local.date()
        moment = datetime(day.year, day.month, day.day, tzinfo=tz)
        while moment < filters.end:
            starts.append(moment.astimezone(UTC))
            day += timedelta(days=1)
            moment = datetime(day.year, day.month, day.day, tzinfo=tz)
            if len(starts) > MAX_BUCKETS:
                break
    else:
        moment = local.replace(minute=0, second=0, microsecond=0).astimezone(UTC)
        while moment < filters.end:
            starts.append(moment)
            moment += timedelta(hours=1)
            if len(starts) > MAX_BUCKETS:
                break
    if len(starts) > MAX_BUCKETS:
        raise InvalidParameters({"bucket": f"more than {MAX_BUCKETS} buckets; narrow the range"})
    return starts
