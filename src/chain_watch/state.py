"""The bookkeeping a watcher carries across a restart to notify only once.

The watcher deduplicates by ``DepositKey``, the ``(tx_id, output_index)`` pair
that names one transaction output. Holding that bookkeeping in memory alone
would let a restart replay the chain and notify a second time, so it is exposed
here as a plain value: :meth:`WatcherState.to_dict` renders JSON-ready data and
:meth:`WatcherState.from_dict` reads it back.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .models import BlockRef, Deposit, DepositKey, InvalidTransfer, Transfer

__all__ = ["STATE_VERSION", "InvalidState", "WatcherState"]

STATE_VERSION = 1


class InvalidState(ValueError):
    """A snapshot cannot be read back into a watcher."""


def _field(data: Mapping[str, object], name: str, label: str) -> object:
    if name not in data:
        raise InvalidState(f"{label} is missing {name!r}")
    return data[name]


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidState(f"{label} must be an int: {value!r}")
    return value


def _as_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidState(f"{label} must be a string: {value!r}")
    return value


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidState(f"{label} must be a mapping: {value!r}")
    return value


def _as_sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidState(f"{label} must be a list: {value!r}")
    return value


def _block_to_dict(block: BlockRef) -> dict[str, object]:
    return {"height": block.height, "hash": block.hash}


def _block_from_dict(value: object) -> BlockRef:
    data = _as_mapping(value, "block")
    return BlockRef(
        height=_as_int(_field(data, "height", "block"), "block height"),
        hash=_as_str(_field(data, "hash", "block"), "block hash"),
    )


def _transfer_to_dict(transfer: Transfer) -> dict[str, object]:
    return {
        "tx_id": transfer.tx_id,
        "output_index": transfer.output_index,
        "address": transfer.address,
        "amount": str(transfer.amount),
        "asset": transfer.asset,
        "block": _block_to_dict(transfer.block),
    }


def _transfer_from_dict(value: object) -> Transfer:
    data = _as_mapping(value, "transfer")
    return Transfer(
        tx_id=_as_str(_field(data, "tx_id", "transfer"), "tx_id"),
        output_index=_as_int(
            _field(data, "output_index", "transfer"), "output_index"
        ),
        address=_as_str(_field(data, "address", "transfer"), "address"),
        amount=_as_str(_field(data, "amount", "transfer"), "amount"),
        asset=_as_str(_field(data, "asset", "transfer"), "asset"),
        block=_block_from_dict(_field(data, "block", "transfer")),
    )


def _deposit_to_dict(deposit: Deposit) -> dict[str, object]:
    return {
        "transfer": _transfer_to_dict(deposit.transfer),
        "confirmations": deposit.confirmations,
    }


def _deposit_from_dict(value: object) -> Deposit:
    data = _as_mapping(value, "deposit")
    return Deposit(
        transfer=_transfer_from_dict(_field(data, "transfer", "deposit")),
        confirmations=_as_int(
            _field(data, "confirmations", "deposit"), "confirmations"
        ),
    )


def _key_from_list(value: object) -> DepositKey:
    pair = _as_sequence(value, "deposit key")
    if len(pair) != 2:
        raise InvalidState(f"deposit key must hold two items: {value!r}")
    return (_as_str(pair[0], "tx_id"), _as_int(pair[1], "output_index"))


@dataclass(frozen=True, slots=True)
class WatcherState:
    """Everything a watcher remembers between polls.

    ``pending`` are transfers seen but not deep enough yet, ``reported`` are
    deposits already notified but still inside the reorg window, and
    ``settled`` are the keys of deposits buried below it: final, never reverted
    and never notified again. ``settled`` only grows, which is what the
    guarantee costs.
    """

    start_height: int = 0
    pending: tuple[Transfer, ...] = ()
    reported: tuple[Deposit, ...] = ()
    settled: tuple[DepositKey, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Render the state as JSON-ready data; amounts become strings."""
        return {
            "version": STATE_VERSION,
            "start_height": self.start_height,
            "pending": [_transfer_to_dict(transfer) for transfer in self.pending],
            "reported": [_deposit_to_dict(deposit) for deposit in self.reported],
            "settled": [[tx_id, index] for tx_id, index in self.settled],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WatcherState:
        """Read back what :meth:`to_dict` wrote."""
        payload = _as_mapping(data, "state")
        version = _as_int(_field(payload, "version", "state"), "version")
        if version != STATE_VERSION:
            raise InvalidState(f"unsupported state version: {version}")
        try:
            return cls(
                start_height=_as_int(
                    _field(payload, "start_height", "state"), "start_height"
                ),
                pending=tuple(
                    _transfer_from_dict(item)
                    for item in _as_sequence(
                        _field(payload, "pending", "state"), "pending"
                    )
                ),
                reported=tuple(
                    _deposit_from_dict(item)
                    for item in _as_sequence(
                        _field(payload, "reported", "state"), "reported"
                    )
                ),
                settled=tuple(
                    _key_from_list(item)
                    for item in _as_sequence(
                        _field(payload, "settled", "state"), "settled"
                    )
                ),
            )
        except InvalidTransfer as exc:
            raise InvalidState(f"snapshot holds unusable data: {exc}") from exc
