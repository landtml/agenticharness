"""Upper-Right Harness: a durable, headless agent orchestrator.

An Opus manager picks steps; Claude Haiku 5.5 workers do them in fresh
contexts; script gates decide "done"; everything that must survive lives in a
SQLite journal and a per-run git repository.
"""

__version__ = "0.1.0"
HARNESS_VERSION = __version__
