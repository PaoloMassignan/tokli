"""Configuration errors carry a one-line cause and a one-line fix (PT-008)."""


class ConfigError(Exception):
    """An invalid or unusable configuration. ``cause`` names the layer, key or path."""

    def __init__(self, cause: str, fix: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.fix = fix
