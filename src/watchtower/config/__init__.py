"""Describing watchers in YAML config files."""

from watchtower.config._intervals import parse_interval
from watchtower.config._loader import Config, load_config

__all__ = ["Config", "load_config", "parse_interval"]
