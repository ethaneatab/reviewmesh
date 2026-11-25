"""The steps a worker runs for one (record, seq). Step 03: a single APPLIED marker."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .worker import Worker


def run_steps(worker: Worker, body: dict[str, Any], token: int) -> str:
    from .worker import default_process
    return default_process(worker, body, token)
