from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest

from tests.integration.servers import FakeUpstream, Tokli, make_config, run_tokli, serve


@pytest.fixture
def upstream() -> Iterator[FakeUpstream]:
    fake = FakeUpstream()
    with serve(fake.app()) as url:
        fake.url = url
        yield fake


@pytest.fixture
def tokli(tmp_path: Path, upstream: FakeUpstream) -> Iterator[Callable[..., Tokli]]:
    """Factory: ``tokli("compressors.json_minify.enabled=false", env={...})`` starts a Tokli."""
    with ExitStack() as stack:

        def start(
            *sets: str, env: dict[str, str] | None = None, base_url: str | None = None
        ) -> Tokli:
            config = make_config(tmp_path, base_url or upstream.url, *sets, env=env)
            return stack.enter_context(run_tokli(config))

        yield start
