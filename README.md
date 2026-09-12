# chain-watch

Track deposits and confirmations: follow addresses, count confirmations,
survive reorgs, and notify once and only once.

Crediting a deposit is a one-way door: once the balance moves, the customer can
spend it. A chain is under no such obligation and may change its mind about
what happened a few blocks ago. chain-watch sits between the two. It holds
every transfer until it is buried deep enough, reports it once, and hands it
back if the chain takes the block away.

## Status

Early stage. The public API is not stable yet.

## Installation

```bash
pip install chain-watch
```

## The model

One protocol and a handful of immutable values. Nothing here opens a socket or
writes a row; where the data comes from and where the credit lands are both
yours.

**`ChainSource`** is the one thing you implement: `tip()` returns the best
block, `transfers(addresses=..., since_height=...)` returns the incoming
payments to those addresses at or above that height. It is a view of the chain
as it looks right now, not a log of what was ever seen.

**`Transfer`** is what the source found: `tx_id`, `output_index`, `address`,
`amount`, `asset`, and the `block` it currently sits in. It validates on
construction — the amount must be positive and finite, and a `float` is refused
outright in favour of `Decimal`, `int` or `str`, so no payment is rounded on
its way in. Anything impossible raises `InvalidTransfer` rather than becoming a
quiet zero.

**`DepositKey`** is the `(tx_id, output_index)` pair: the transaction output
the payment landed on. It names *what* was paid, not *where* it was mined.

**`Deposit`** is a transfer that reached the required depth, plus the
`confirmations` it had when it was reported. It forwards the transfer's fields,
so `deposit.address`, `deposit.amount` and `deposit.block` all work directly.

**`PollResult`** is what one poll changed: `confirmed` and `reverted`. It is
falsy when both are empty, so `if not watcher.poll()` reads as "nothing
happened".

**`WatcherState`** is everything the watcher remembers, as a value you can
serialise.

## Usage

Plug in the source and poll on whatever schedule your chain deserves:

```python
from chain_watch import DepositWatcher

watcher = DepositWatcher(source, ["addr-1", "addr-2"], policy=3)

result = watcher.poll()
for deposit in result.confirmed:
    print(deposit.address, deposit.amount, deposit.asset)
    print(deposit.confirmations, deposit.block.height, deposit.block.hash)
```

Depth counts the block itself, so a transfer sitting in the tip has one
confirmation. A deposit is returned once it reaches the depth its asset needs,
and never returned again, no matter how often the source keeps reporting the
same transfer. Transfers that are still too shallow wait in `watcher.pending`.

Addresses are matched exactly after stripping surrounding whitespace, and a
source that answers with more than it was asked for is filtered: a transfer to
an address you are not watching is dropped rather than credited.

## The depth policy

How deep is deep enough is the caller's call, and it differs per asset. A chain
with ten-second blocks and a chain that settles in minutes do not deserve the
same number, and a stablecoin worth more per transfer than the coin it rides on
may deserve a stricter one than its own chain.

```python
from chain_watch import ConfirmationPolicy, DepositWatcher

policy = ConfirmationPolicy(default=6, per_asset={"ETH": 12, "USDT": 12})
watcher = DepositWatcher(source, ["addr-1"], policy=policy)

policy.depth_for("BTC")   # 6, the default
policy.depth_for("USDT")  # 12, the override
```

The `policy=` argument takes a policy, a bare `int` or a mapping:

| Passed | Means |
| --- | --- |
| `ConfirmationPolicy(...)` | used as is |
| `3` | three confirmations for every asset |
| `{"ETH": 12}` | twelve for ETH, one for everything else |

A mapping deliberately leaves the default at one confirmation rather than at
infinity: an asset nobody listed is still reported, so a new token appearing on
a watched address shows up as a shallow deposit instead of disappearing into a
queue forever. Depths must be integers of at least one; zero would mean
crediting a payment that is not yet in a block.

Asset names are matched exactly as the chain source spells them. `"usdt"` and
`"USDT"` are two different assets, and only one of them has an override.

`policy.max_depth` is the deepest requirement anywhere in the policy, and
`policy.with_asset(asset, depth)` returns a copy with one more override — the
policy is frozen, so tightening a requirement never mutates a policy some other
watcher is already using.

## The reorg contract

Blocks disappear. Every poll re-reads the bottom of the chain and compares it
with what the watcher saw last time.

The window is the last `reorg_depth` blocks below the tip. Its floor is
`tip.height - reorg_depth + 1`, never below `start_height`, and that floor is
exactly the `since_height` the source is asked for. Everything at or above it
is provisional; everything below it is history.

```python
watcher = DepositWatcher(source, ["addr-1"], policy=3, reorg_depth=20)

result = watcher.poll()
for deposit in result.confirmed:
    credit(deposit)
for deposit in result.reverted:
    withdraw(deposit)
```

Inside the window, three rules:

- a pending transfer the source stops returning is dropped silently — it was
  never credited, so there is nothing to take back;
- a reported deposit whose block is gone, or whose transfer turned up in a
  different block, comes back in `reverted` so the credit can be withdrawn;
- a transfer that is mined again is held from scratch and confirms a second
  time, on the new block, with a fresh confirmation count.

Below the window a deposit is settled: never reverted, never reported again,
whatever the source says afterwards. That is the whole point of the number —
`reorg_depth` is how long you are still willing to change your mind.

It defaults to `policy.max_depth`, which means a deposit settles the moment it
is credited: the cheapest possible bookkeeping, and the right choice only if a
reorg deeper than your confirmation depth is something you would handle by
hand anyway. Set it higher to keep watching after the credit — with
`policy=3, reorg_depth=20` a deposit is credited at three confirmations and
stays revertible for another seventeen blocks.

A shorter chain is not by itself a reorg. If the tip drops but the block
holding the transfer survives, nothing is reverted; only a block that is gone
or replaced takes a deposit back.

This makes one demand on the chain source, and it is the demand everything else
rests on: `transfers()` must describe the current best chain. A transfer it
stops returning is a transfer the chain no longer has. A source that answers
from an append-only log of everything it ever saw will never revert anything,
because nothing ever vanishes from its answer.

Three properties expose the window at any moment: `watcher.pending` (seen, not
deep enough), `watcher.revertible` (reported, still inside the window) and
`watcher.settled` (keys below it).

## Exactly-once notification

The dedup key is `DepositKey`, the `(tx_id, output_index)` pair. Because it
says what was paid and not where it was mined, it survives the block moving
underneath it: duplicated blocks, replayed ranges, restarts and reorgs all
yield the same key. Every deposit carries it as `deposit.key`, which is also
the key to deduplicate on downstream.

The watcher guarantees:

- a transfer the source returns on every poll is confirmed once;
- a source that replays a range it already served changes nothing;
- a key that was reverted may confirm again, but only after the revert was
  reported, so credits and withdrawals always alternate;
- a key below the reorg window is settled: never reverted, never reported
  again, whatever the source says afterwards.

### Surviving a restart

Memory is not a guarantee, so the bookkeeping is a value you can persist and
hand back:

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
starting point, and passing both is refused rather than resolved by guessing.
`to_dict()` is JSON-ready, with amounts as strings so no decimal is rounded on
the way out and back; `from_dict()` checks the version and raises
`InvalidState` on anything it cannot read, instead of resuming from a snapshot
it half understood.

Where the snapshot is written decides what the whole pipeline delivers:

| Snapshot written | Delivery | Why |
| --- | --- | --- |
| in the same transaction as the notification | exactly once | both land or neither does |
| after the notification | at least once | a crash in between replays the poll |
| before the notification | at most once | the same crash drops the notification |

The watcher can only promise the first column is reachable; which one you get
is a property of your storage, not of this library.

Settled keys are kept for the lifetime of the state. That is what makes a
replay from height zero safe, and what makes the snapshot grow with the number
of deposits ever seen.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

The suite runs against a scripted chain (`tests/scripted_chain.py`) that mines,
stalls, forks and rolls back on demand, so every transition the watcher knows
is driven by a chain misbehaving rather than by a mock.

## License

MIT, see [LICENSE](LICENSE).

---

Maintained by [polycratia](https://polycratia.com).
