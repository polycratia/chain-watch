"""Follow a set of addresses and report every deposit exactly once."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Deposit, Transfer, confirmations_for
from .policy import ConfirmationPolicy, DepthSpec
from .source import ChainSource

__all__ = ["DepositWatcher"]


class DepositWatcher:
    """Turn raw transfers from a chain source into deposits.

    Each :meth:`poll` asks the source for transfers at or above the internal
    cursor and holds them until they reach the depth the policy requires for
    their asset. The transition from seen to confirmed happens once: a transfer
    that was already reported is never reported again, even if the source keeps
    returning it. Reorgs are not handled yet: a transfer is trusted as soon as
    its block is deep enough.
    """

    def __init__(
        self,
        source: ChainSource,
        addresses: Iterable[str],
        *,
        policy: DepthSpec = 1,
        start_height: int = 0,
    ) -> None:
        watched = {address.strip() for address in addresses}
        watched.discard("")
        if not watched:
            raise ValueError("at least one address is required")
        if start_height < 0:
            raise ValueError(f"start_height must not be negative: {start_height}")

        self._source = source
        self._addresses = watched
        self._policy = ConfirmationPolicy.coerce(policy)
        self._cursor = start_height
        self._pending: dict[tuple[str, int], Transfer] = {}
        self._reported: set[tuple[str, int]] = set()

    @property
    def addresses(self) -> frozenset[str]:
        return frozenset(self._addresses)

    @property
    def policy(self) -> ConfirmationPolicy:
        return self._policy

    @property
    def pending(self) -> tuple[Transfer, ...]:
        """Seen transfers that are not deep enough to be reported yet."""
        return tuple(sorted(self._pending.values(), key=_transfer_order))

    def poll(self) -> tuple[Deposit, ...]:
        """Fetch from the source and return the deposits that matured now."""
        tip = self._source.tip()
        addresses = sorted(self._addresses)
        for transfer in self._source.transfers(
            addresses=addresses, since_height=self._cursor
        ):
            if transfer.address not in self._addresses:
                continue
            if transfer.key in self._reported:
                continue
            self._pending[transfer.key] = transfer
        self._cursor = tip.height + 1

        matured: list[Deposit] = []
        for key, transfer in list(self._pending.items()):
            confirmations = confirmations_for(transfer.block, tip)
            if not self._policy.is_confirmed(transfer.asset, confirmations):
                continue
            del self._pending[key]
            self._reported.add(key)
            matured.append(Deposit(transfer=transfer, confirmations=confirmations))

        matured.sort(key=lambda deposit: _transfer_order(deposit.transfer))
        return tuple(matured)


def _transfer_order(transfer: Transfer) -> tuple[int, str, int]:
    return (transfer.block.height, transfer.tx_id, transfer.output_index)
