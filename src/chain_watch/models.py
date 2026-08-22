"""Value types the watcher works with: blocks, transfers and deposits.

A :class:`Transfer` is what a chain source sees; a :class:`Deposit` is what the
watcher reports once a transfer is buried deep enough. Both are immutable and
carry no persistence concerns: the caller decides where they end up.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "InvalidTransfer",
    "BlockRef",
    "Transfer",
    "Deposit",
    "confirmations_for",
]


class InvalidTransfer(ValueError):
    """A chain source reported data that cannot describe a deposit."""


@dataclass(frozen=True, slots=True)
class BlockRef:
    """Where something happened on the chain."""

    height: int
    hash: str

    def __post_init__(self) -> None:
        if self.height < 0:
            raise InvalidTransfer(f"block height must not be negative: {self.height}")
        if not self.hash:
            raise InvalidTransfer("block hash must not be empty")


def confirmations_for(block: BlockRef, tip: BlockRef) -> int:
    """Depth of ``block`` under ``tip``, counting the block itself as one."""
    if tip.height < block.height:
        return 0
    return tip.height - block.height + 1


def _as_amount(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise InvalidTransfer("amount must not be a float; use Decimal, int or str")
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(value)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise InvalidTransfer(f"amount is not a number: {value!r}") from exc
    if not amount.is_finite():
        raise InvalidTransfer("amount must be finite")
    if amount <= 0:
        raise InvalidTransfer(f"amount must be positive: {amount}")
    return amount


@dataclass(frozen=True, slots=True)
class Transfer:
    """An incoming payment to a watched address, as found in a block."""

    tx_id: str
    output_index: int
    address: str
    amount: Decimal
    asset: str
    block: BlockRef

    def __post_init__(self) -> None:
        if not self.tx_id:
            raise InvalidTransfer("tx_id must not be empty")
        if self.output_index < 0:
            raise InvalidTransfer(
                f"output_index must not be negative: {self.output_index}"
            )
        if not self.address:
            raise InvalidTransfer("address must not be empty")
        if not self.asset:
            raise InvalidTransfer("asset must not be empty")
        object.__setattr__(self, "amount", _as_amount(self.amount))

    @property
    def key(self) -> tuple[str, int]:
        """Identity of the payment on the chain, stable across polls."""
        return (self.tx_id, self.output_index)


@dataclass(frozen=True, slots=True)
class Deposit:
    """A transfer that reached the required depth, reported to the caller."""

    transfer: Transfer
    confirmations: int

    def __post_init__(self) -> None:
        if self.confirmations < 0:
            raise InvalidTransfer(
                f"confirmations must not be negative: {self.confirmations}"
            )

    @property
    def key(self) -> tuple[str, int]:
        return self.transfer.key

    @property
    def tx_id(self) -> str:
        return self.transfer.tx_id

    @property
    def output_index(self) -> int:
        return self.transfer.output_index

    @property
    def address(self) -> str:
        return self.transfer.address

    @property
    def amount(self) -> Decimal:
        return self.transfer.amount

    @property
    def asset(self) -> str:
        return self.transfer.asset

    @property
    def block(self) -> BlockRef:
        return self.transfer.block
