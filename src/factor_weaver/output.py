"""Shared rich consoles: one palette for logs and printed output."""

from rich.console import Console
from rich.theme import Theme

THEME = Theme(
    {
        "logging.level.debug": "cyan",
        "logging.level.info": "green",
        "logging.level.warning": "yellow",
        "logging.level.error": "red",
        "logging.level.critical": "bold red",
    }
)

out = Console(theme=THEME, color_system="standard")
err = Console(stderr=True, theme=THEME, color_system="standard")
