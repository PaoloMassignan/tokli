"""The explicit compressor registry (CC-011). Adding a compressor = one module + one entry here."""

from __future__ import annotations

from tokli.compression.contract import Compressor
from tokli.compressors.json_minify import JsonMinify

REGISTRY: tuple[Compressor, ...] = (JsonMinify(),)
