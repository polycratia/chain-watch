"""Follow a set of addresses and report every deposit exactly once."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import Deposit, DepositKey, Transfer, confirmations_for
from .policy import ConfirmationPolicy, DepthSpec
from .source import ChainSource
from .state import WatcherState

__all__ = ["DepositWatcher", "PollResult"]


@dataclass(frozen=True, slots=True)
class PollResult:
    """What one poll changed: deposits that matured and deposits that died."""

    confirmed: tuple[Deposit, ...] = ()
    reverted: tuple[Deposit, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.confirmed or self.reverted)


class DepositWatcher:
    """Turn raw transfers from a chain source into deposits.

    Each :meth:`poll` re-reads the last ``reorg_depth`` blocks from the source
    and holds every transfer it finds until it reaches the depth the policy
    requires for its asset. The transition from seen to confirmed happens once:
    a transfer that was already reported is never reported again, even if the
    source keeps returning it.

    A chain can also take blocks back. While a deposit is still inside the
    reorg window, its block is checked against what the source reports now; if
    the block is gone, or the transfer moved elsewhere, the deposit comes back
    as ``reverted`` and the caller can withdraw the credit. A transfer that is
    mined again is held from scratch and confirms a second time. Below the
    window a deposit is final: never reverted, never reported twice.

    Identity is the transfer's ``DepositKey``, the ``(tx_id, output_index)``
    pair, so duplicated blocks and sources that replay ranges they already
    served change nothing. Memory alone would lose that across a restart, so
    the bookkeeping is available as :attr:`state` and can be handed back to the
    constructor to resume where the previous process stopped.
    """

    def __init__(
        self,
        source: ChainSource,
        addresses: Iterable[str],
        *,
        policy: DepthSpec = 1,
        start_height: int = 0,
        reorg_depth: int | None = None,
        state: WatcherState | None = None,
    ) -> None:
        watched = {address.strip() for address in addresses}
        watched.discard("")
        if not watched:
            raise ValueError("at least one address is required")
        if state is not None:
            if start_height:
                raise ValueError("pass either start_height or state, not both")
            start_height = state.start_height
        if start_height < 0:
            raise ValueError(f"start_height must not be negative: {start_height}")

        self._policy = ConfirmationPolicy.coerce(policy)
        if reorg_depth is None:
            reorg_depth = self._policy.max_depth
        elif reorg_depth < 1:
            raise ValueError(f"reorg_depth must be at least 1: {reorg_depth}")

        self._source = source
        self._addresses = watched
        self._reorg_depth = reorg_depth
        self._start_height = start_height
        self._pending: dict[DepositKey, Transfer] = {}
        self._reported: dict[DepositKey, Deposit] = {}
        self._settled: set[DepositKey] = set()
        if state is not None:
            self._pending.update((t.key, t) for t in state.pending)
            self._reported.update((d.key, d) for d in state.reported)
            self._settled.update(state.settled)

    @property
    def addresses(self) -> frozenset[str]:
        return frozenset(self._addresses)

    @property
    def policy(self) -> ConfirmationPolicy:
        return self._policy

    @property
    def reorg_depth(self) -> int:
        """How many blocks below the tip are re-read on every poll."""
        return self._reorg_depth

    @property
    def pending(self) -> tuple[Transfer, ...]:
        """Seen transfers that are not deep enough to be reported yet."""
        return tuple(sorted(self._pending.values(), key=_transfer_order))

    @property
    def revertible(self) -> tuple[Deposit, ...]:
        """Reported deposits still shallow enough to be taken back."""
        return tuple(
            sorted(
                self._reported.values(),
                key=lambda deposit: _transfer_order(deposit.transfer),
            )
        )

    @property
    def settled(self) -> frozenset[DepositKey]:
        """Keys that were notified and are now below the reorg window."""
        return frozenset(self._settled)

    @property
    def state(self) -> WatcherState:
        """A snapshot that resumes the watcher without notifying twice."""
        return WatcherState(
            start_height=self._start_height,
            pending=self.pending,
            reported=self.revertible,
            settled=tuple(sorted(self._settled)),
        )

    def poll(self) -> PollResult:
        """Fetch from the source and report what confirmed and what vanished."""
        tip = self._source.tip()
        floor = max(self._start_height, tip.height - self._reorg_depth + 1)
        addresses = sorted(self._addresses)

        seen: dict[DepositKey, Transfer] = {}
        for transfer in self._source.transfers(
            addresses=addresses, since_height=floor
        ):
            if transfer.address not in self._addresses:
                continue
            seen[transfer.key] = transfer

        for key, transfer in list(self._pending.items()):
            if transfer.block.height >= floor and key not in seen:
                del self._pending[key]

        reverted: list[Deposit] = []
        for key, deposit in list(self._reported.items()):
            if deposit.block.height < floor:
                continue
            current = seen.get(key)
            if current is not None and current.block == deposit.block:
                continue
            del self._reported[key]
            reverted.append(deposit)

        for key, transfer in seen.items():
            if key not in self._reported and key not in self._settled:
                self._pending[key] = transfer

        confirmed: list[Deposit] = []
        for key, transfer in list(self._pending.items()):
            confirmations = confirmations_for(transfer.block, tip)
            if not self._policy.is_confirmed(transfer.asset, confirmations):
                continue
            del self._pending[key]
            deposit = Deposit(transfer=transfer, confirmations=confirmations)
            self._reported[key] = deposit
            confirmed.append(deposit)

        for key, deposit in list(self._reported.items()):
            if deposit.block.height < floor:
                del self._reported[key]
                self._settled.add(key)

        confirmed.sort(key=lambda deposit: _transfer_order(deposit.transfer))
        reverted.sort(key=lambda deposit: _transfer_order(deposit.transfer))
        return PollResult(tuple(confirmed), tuple(reverted))


def _transfer_order(transfer: Transfer) -> tuple[int, str, int]:
    return (transfer.block.height, transfer.tx_id, transfer.output_index)
