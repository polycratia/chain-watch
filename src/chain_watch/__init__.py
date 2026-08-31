"""Track deposits and confirmations across chains."""

from .models import (
    BlockRef,
    Deposit,
    DepositKey,
    InvalidTransfer,
    Transfer,
    confirmations_for,
)
from .policy import ConfirmationPolicy, DepthSpec
from .source import ChainSource
from .state import STATE_VERSION, InvalidState, WatcherState
from .watcher import DepositWatcher, PollResult

__version__ = "0.1.0"

__all__ = [
    "STATE_VERSION",
    "BlockRef",
    "ChainSource",
    "ConfirmationPolicy",
    "Deposit",
    "DepositKey",
    "DepositWatcher",
    "DepthSpec",
    "InvalidState",
    "InvalidTransfer",
    "PollResult",
    "Transfer",
    "WatcherState",
    "confirmations_for",
    "__version__",
]
