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

watcher = DepositWatcher(source, ["addr-1", "addr-2"], policy=3)

for deposit in watcher.poll():
    print(deposit.address, deposit.amount, deposit.asset)
    print(deposit.confirmations, deposit.block.height, deposit.block.hash)
```

A deposit is returned once it reaches the required depth, and never returned
again, no matter how often the source keeps reporting the same transfer.
Transfers that are still too shallow stay in `watcher.pending`.

## Confirmation depth

How deep is deep enough is the caller's call, and it differs per asset:

```python
from chain_watch import ConfirmationPolicy, DepositWatcher

policy = ConfirmationPolicy(default=6, per_asset={"ETH": 12, "USDT": 12})
watcher = DepositWatcher(source, ["addr-1"], policy=policy)

policy.depth_for("BTC")   # 6, the default
policy.depth_for("USDT")  # 12, the override
```

A bare `int` sets the default for everything; a mapping sets overrides and
leaves the default at one confirmation, so an asset nobody listed is still
reported rather than held forever. Asset names are matched exactly as the
chain source spells them.

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
