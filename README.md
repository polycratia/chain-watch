# chain-watch

Track deposits and confirmations: follow addresses, count confirmations,
survive reorgs, and notify once and only once.

## Status

Early stage. The public API is not stable yet.

## Installation

```bash
pip install chain-watch
```

## Usage

Plug in any object that satisfies the `ChainSource` protocol (`tip()` and
`transfers(addresses=..., since_height=...)`) and poll for deposits:

```python
from chain_watch import DepositWatcher

watcher = DepositWatcher(source, ["addr-1", "addr-2"], min_confirmations=3)

for deposit in watcher.poll():
    print(deposit.address, deposit.amount, deposit.asset)
    print(deposit.confirmations, deposit.block.height, deposit.block.hash)
```

A deposit is returned once it reaches `min_confirmations`, and never returned
again, no matter how often the source keeps reporting the same transfer.
Transfers that are still too shallow stay in `watcher.pending`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## License

MIT, see [LICENSE](LICENSE).

---

Maintained by [polycratia](https://polycratia.com).
