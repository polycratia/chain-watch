"""Track deposits and confirmations across chains."""

from .models import (
    BlockRef,
    Deposit,
    InvalidTransfer,
    Transfer,
    confirmations_for,
)
from .policy import ConfirmationPolicy, DepthSpec
from .source import ChainSource
from .watcher import DepositWatcher

__version__ = "0.1.0"

__all__ = [
    "BlockRef",
    "ChainSource",
    "ConfirmationPolicy",
    "Deposit",
    "DepositWatcher",
    "DepthSpec",
    "InvalidTransfer",
    "Transfer",
    "confirmations_for",
    "__version__",
]
