"""A chain a test can script: mine, stall, fork and roll back on demand.

The watcher only ever sees the current best chain, so a chain held in memory is
enough to drive every transition it knows. Blocks are appended, dropped and
rebuilt; ``transfers`` is recomputed from whatever the chain looks like at the
moment it is asked, which is exactly the contract ``ChainSource`` states.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chain_watch import BlockRef, Transfer

__all__ = ["Payment", "ScriptedChain", "pay"]


@dataclass(frozen=True, slots=True)
class Payment:
    """A payment waiting to be mined into some block."""

    tx_id: str
    output_index: int = 0
    address: str = "addr-1"
    amount: str = "1"
    asset: str = "BTC"


def pay(
    tx_id: str,
    *,
    output_index: int = 0,
    address: str = "addr-1",
    amount: str = "1",
    asset: str = "BTC",
) -> Payment:
    return Payment(tx_id, output_index, address, amount, asset)


@dataclass(frozen=True, slots=True)
class _Block:
    height: int
    hash: str
    payments: tuple[Payment, ...]

    @property
    def ref(self) -> BlockRef:
        return BlockRef(height=self.height, hash=self.hash)


class ScriptedChain:
    """An in-memory best chain plus the levers a test needs to move it.

    With ``noisy`` the source stops filtering by address and answers with every
    payment in the window, the way a sloppy backend would.
    """

    def __init__(self, *, noisy: bool = False) -> None:
        self._noisy = noisy
        self._mined = 0
        self._blocks: list[_Block] = [self._new_block(0, ())]
        self.queries: list[tuple[tuple[str, ...], int]] = []

    def _new_block(self, height: int, payments: Sequence[Payment]) -> _Block:
        self._mined += 1
        return _Block(height, f"blk-{height}-{self._mined}", tuple(payments))

    @property
    def height(self) -> int:
        return self._blocks[-1].height

    @property
    def last_query(self) -> tuple[tuple[str, ...], int]:
        return self.queries[-1]

    def block_at(self, height: int) -> BlockRef:
        return self._blocks[height].ref

    def mine(self, *payments: Payment, count: int = 1) -> BlockRef:
        """Append ``count`` blocks, with ``payments`` landing in the first."""
        if count < 1:
            raise ValueError(f"count must be at least 1: {count}")
        for index in range(count):
            self._blocks.append(
                self._new_block(self.height + 1, payments if index == 0 else ())
            )
        return self.tip()

    def stall(self) -> BlockRef:
        """Produce nothing: the next poll meets the very same chain."""
        return self.tip()

    def rollback(self, to_height: int) -> BlockRef:
        """Drop every block above ``to_height``."""
        if not 0 <= to_height <= self.height:
            raise ValueError(f"cannot roll back to height {to_height}")
        del self._blocks[to_height + 1 :]
        return self.tip()

    def fork(self, at_height: int, *payments: Payment, length: int = 1) -> BlockRef:
        """Rebuild the chain from ``at_height`` up with freshly hashed blocks."""
        if at_height < 1:
            raise ValueError(f"cannot fork below the genesis block: {at_height}")
        self.rollback(at_height - 1)
        return self.mine(*payments, count=length)

    def tip(self) -> BlockRef:
        return self._blocks[-1].ref

    def transfers(
        self, *, addresses: Sequence[str], since_height: int
    ) -> list[Transfer]:
        self.queries.append((tuple(addresses), since_height))
        watched = set(addresses)
        found: list[Transfer] = []
        for block in self._blocks:
            if block.height < since_height:
                continue
            for payment in block.payments:
                if not self._noisy and payment.address not in watched:
                    continue
                found.append(
                    Transfer(
                        tx_id=payment.tx_id,
                        output_index=payment.output_index,
                        address=payment.address,
                        amount=payment.amount,
                        asset=payment.asset,
                        block=block.ref,
                    )
                )
        return found
