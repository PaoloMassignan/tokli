"""S1 acceptance 5 (decision P3): hash of the rendered compat corpus with the default config.

Usage: ``python -m tests.compat.render_corpus --data-dir DIR``. Prints one ``name sha256`` line
per fixture. CI runs it in every job and checks that all 9 outputs are identical.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from tokli.app.bootstrap import bootstrap
from tokli.config import CliOverrides, load_config
from tokli.domain.stage import StageContext
from tokli.protocols.anthropic_messages import parse, render

FIXTURES = Path(__file__).parent / "fixtures" / "anthropic_messages"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    env = {k: v for k, v in os.environ.items() if not k.startswith("TOKLI_")}
    config = load_config(CliOverrides(data_dir=args.data_dir), env, sys.platform)
    services = bootstrap(config, version="corpus", telemetry=False)
    for path in sorted(FIXTURES.glob("*.json")):
        request = parse(path.read_bytes(), mutable_kinds=services.mutable_kinds)
        result = services.pipeline.run(request, StageContext(request_id="corpus"))
        rendered = render(request, result.patches)
        print(f"{path.stem} {hashlib.sha256(rendered).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
