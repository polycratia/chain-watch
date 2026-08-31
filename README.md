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
`transfers(addresses=..., since_height=...)`) and poll:

```python
from chain_watch import DepositWatcher

watcher = DepositWatcher(source, ["addr-1", "addr-2"], policy=3)

result = watcher.poll()
for deposit in result.confirmed:
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

## Reorgs

Blocks disappear. Every poll re-reads the last `reorg_depth` blocks below the
tip and compares them with what it saw before. A deposit whose block is gone,
or whose transfer turned up in a different block, is handed back so the credit
can be withdrawn:

```python
watcher = DepositWatcher(source, ["addr-1"], policy=3, reorg_depth=20)

result = watcher.poll()
for deposit in result.confirmed:
    credit(deposit)
for deposit in result.reverted:
    withdraw(deposit)
```

`reorg_depth` defaults to the deepest confirmation the policy asks for; set it
higher to keep watching after a deposit is credited. A transfer that is mined
again is held from scratch and confirms a second time. Below the window a
deposit is final: it is never reverted and never reported again.

This makes one demand on the chain source: `transfers()` must describe the
current best chain, so a transfer it stops returning is a transfer the chain
no longer has.

## Exactly-once notification

The dedup key is `DepositKey`, the `(tx_id, output_index)` pair naming the
transaction output a payment landed on. It says what was paid, not where it was
mined, so it holds across polls, duplicated blocks, restarts and reorgs. Every
deposit carries it as `deposit.key`, which is also the key to deduplicate on
downstream. The watcher guarantees:

- a transfer the source returns on every poll is confirmed once;
- a source that replays a range it already served changes nothing;
- a key that was reverted may confirm again, but only after the revert was
  reported, so credits and withdrawals always alternate;
- a key below the reorg window is settled: never reverted, never reported
  again, whatever the source says afterwards.

Memory is not a guarantee, so the bookkeeping is a value you can persist and
hand back after a restart:

```python
import json
from chain_watch import DepositWatcher, WatcherState

state = WatcherState.from_dict(json.loads(snapshot.read_text()))
watcher = DepositWatcher(source, ["addr-1"], policy=3, state=state)

result = watcher.poll()
notify(result)
snapshot.write_text(json.dumps(watcher.state.to_dict()))
```

`state` and `start_height` are mutually exclusive: a snapshot carries its own
starting point. `to_dict()` is JSON-ready, with amounts as strings so no
decimal is rounded on the way out and back.

Where the snapshot is written decides what the whole pipeline delivers. Storing
it in the same transaction as the notification gives exactly once; storing it
after gives at least once, because a crash in between replays the poll; storing
it before gives at most once, because the same crash drops the notification.

Settled keys are kept for the lifetime of the state, which is what makes a
replay from height zero safe, and what makes the snapshot grow with the number
of deposits ever seen.

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
