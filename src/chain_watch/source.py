"""The protocol a chain backend has to satisfy to be watchable."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from .models import BlockRef, Transfer

__all__ = ["ChainSource"]


@runtime_checkable
class ChainSource(Protocol):
    """Read-only view of a chain: where the tip is and what arrived below it."""

    def tip(self) -> BlockRef:
        """Return the current best block."""
        ...

    def transfers(
        self, *, addresses: Sequence[str], since_height: int
    ) -> Iterable[Transfer]:
        """Return incoming transfers to ``addresses`` from ``since_height`` up.

        The same transfer may be returned by more than one call; the watcher
        deduplicates by transaction output.
        """
        ...
