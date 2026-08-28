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

        The answer is a view of the current best chain, not a log of what was
        ever seen: every transfer at or above ``since_height`` that is on chain
        right now, carrying the block it sits in now. The watcher deduplicates
        by transaction output, so returning the same transfer on every call is
        expected; leaving one out means the chain dropped it, and the watcher
        will take the deposit back.
        """
        ...
