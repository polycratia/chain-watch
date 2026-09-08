"""Every transition of the watcher, driven by a chain that misbehaves."""

import json

import pytest

from chain_watch import ConfirmationPolicy, DepositWatcher, WatcherState
from scripted_chain import ScriptedChain, pay


def keys(deposits):
    return [deposit.key for deposit in deposits]


def test_a_transfer_waits_until_it_reaches_the_required_depth():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=3)
    block = chain.mine(pay("tx-a"))

    assert not watcher.poll()
    assert keys(watcher.pending) == [("tx-a", 0)]

    chain.mine()
    assert not watcher.poll()

    chain.mine()
    result = watcher.poll()

    assert keys(result.confirmed) == [("tx-a", 0)]
    assert result.confirmed[0].confirmations == 3
    assert result.confirmed[0].block == block
    assert watcher.pending == ()
    assert keys(watcher.revertible) == [("tx-a", 0)]


def test_a_confirmed_deposit_is_never_reported_again():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=1)
    chain.mine(pay("tx-a"))

    assert len(watcher.poll().confirmed) == 1

    for _ in range(5):
        chain.stall()
        assert not watcher.poll()

    chain.mine(count=10)
    assert not watcher.poll()
    assert ("tx-a", 0) in watcher.settled


def test_a_stalled_chain_changes_nothing_at_all():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=3)
    chain.mine(pay("tx-a"))
    watcher.poll()
    before = watcher.state

    for _ in range(10):
        chain.stall()
        assert not watcher.poll()

    assert watcher.state == before


def test_each_asset_waits_for_its_own_depth():
    chain = ScriptedChain()
    watcher = DepositWatcher(
        chain,
        ["addr-1"],
        policy=ConfirmationPolicy(default=2, per_asset={"ETH": 4}),
    )
    assert watcher.reorg_depth == 4

    chain.mine(pay("tx-btc", asset="BTC"), pay("tx-eth", asset="ETH"))
    assert not watcher.poll()

    chain.mine()
    result = watcher.poll()
    assert keys(result.confirmed) == [("tx-btc", 0)]
    assert keys(watcher.pending) == [("tx-eth", 0)]

    chain.mine(count=2)
    result = watcher.poll()
    assert keys(result.confirmed) == [("tx-eth", 0)]
    assert result.confirmed[0].confirmations == 4


def test_results_are_ordered_by_block_then_transaction_output():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=1, reorg_depth=9)
    chain.mine(pay("tx-b", output_index=1), pay("tx-b"), pay("tx-a"))
    chain.mine(pay("tx-c"))

    result = watcher.poll()

    assert keys(result.confirmed) == [
        ("tx-a", 0),
        ("tx-b", 0),
        ("tx-b", 1),
        ("tx-c", 0),
    ]


def test_transfers_to_unwatched_addresses_are_dropped():
    chain = ScriptedChain(noisy=True)
    watcher = DepositWatcher(chain, [" addr-1 ", "addr-2"], policy=1)
    chain.mine(pay("tx-a", address="addr-1"), pay("tx-x", address="addr-9"))

    result = watcher.poll()

    assert watcher.addresses == frozenset({"addr-1", "addr-2"})
    assert keys(result.confirmed) == [("tx-a", 0)]


def test_every_poll_re_reads_the_reorg_window():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=1, reorg_depth=4)
    chain.mine(count=10)

    watcher.poll()

    assert chain.last_query == (("addr-1",), 7)


def test_start_height_keeps_the_watcher_off_older_blocks():
    chain = ScriptedChain()
    chain.mine(pay("tx-old"))
    chain.mine()
    watcher = DepositWatcher(
        chain, ["addr-1"], policy=1, start_height=2, reorg_depth=10
    )
    chain.mine(pay("tx-new"))

    result = watcher.poll()

    assert chain.last_query == (("addr-1",), 2)
    assert keys(result.confirmed) == [("tx-new", 0)]


def test_a_transfer_that_vanishes_before_confirming_is_never_reported():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=3, reorg_depth=5)
    chain.mine(pay("tx-a"))
    watcher.poll()
    assert watcher.pending

    chain.fork(1)
    result = watcher.poll()

    assert not result
    assert watcher.pending == ()


def test_a_reorg_while_pending_restarts_the_count():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=3, reorg_depth=6)
    chain.mine(pay("tx-a"))
    chain.mine()
    assert not watcher.poll()

    chain.fork(1)
    chain.mine(pay("tx-a"))
    assert not watcher.poll()
    assert [transfer.block.height for transfer in watcher.pending] == [2]

    chain.mine(count=2)
    confirmed = watcher.poll().confirmed

    assert keys(confirmed) == [("tx-a", 0)]
    assert confirmed[0].confirmations == 3
    assert confirmed[0].block == chain.block_at(2)


def test_a_reorg_takes_back_a_deposit_it_already_reported():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=2, reorg_depth=6)
    original = chain.mine(pay("tx-a"))
    chain.mine()
    assert keys(watcher.poll().confirmed) == [("tx-a", 0)]

    chain.fork(1, length=2)
    result = watcher.poll()

    assert keys(result.reverted) == [("tx-a", 0)]
    assert result.reverted[0].block == original
    assert result.confirmed == ()
    assert watcher.revertible == ()
    assert watcher.pending == ()
    assert not watcher.poll()


def test_a_transfer_mined_again_is_reverted_and_confirmed_from_scratch():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=2, reorg_depth=6)
    original = chain.mine(pay("tx-a"))
    chain.mine()
    watcher.poll()

    chain.fork(1, pay("tx-a"), length=2)
    result = watcher.poll()

    assert keys(result.reverted) == [("tx-a", 0)]
    assert result.reverted[0].block == original
    assert keys(result.confirmed) == [("tx-a", 0)]
    assert result.confirmed[0].block == chain.block_at(1)
    assert result.confirmed[0].block != original
    assert not watcher.poll()


def test_a_shorter_chain_that_keeps_the_block_reverts_nothing():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=1, reorg_depth=5)
    chain.mine(pay("tx-a"))
    chain.mine(count=3)
    assert len(watcher.poll().confirmed) == 1

    chain.rollback(1)

    assert not watcher.poll()
    assert keys(watcher.revertible) == [("tx-a", 0)]


def test_a_deposit_below_the_window_survives_a_deeper_reorg():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=1, reorg_depth=2)
    chain.mine(pay("tx-a"))
    assert len(watcher.poll().confirmed) == 1

    chain.mine(count=3)
    assert not watcher.poll()
    assert ("tx-a", 0) in watcher.settled

    chain.fork(1, length=6)
    assert not watcher.poll()

    chain.mine(pay("tx-a"))
    assert not watcher.poll()
    assert watcher.pending == ()
    assert ("tx-a", 0) in watcher.settled


def test_a_snapshot_resumes_the_watcher_without_notifying_twice():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=2, reorg_depth=3)

    chain.mine(pay("tx-a"))
    chain.mine()
    assert keys(watcher.poll().confirmed) == [("tx-a", 0)]

    chain.mine(pay("tx-b"))
    assert not watcher.poll()

    chain.mine()
    assert keys(watcher.poll().confirmed) == [("tx-b", 0)]
    assert ("tx-a", 0) in watcher.settled

    chain.mine(pay("tx-c", amount="0.10000000"))
    assert not watcher.poll()

    snapshot = json.loads(json.dumps(watcher.state.to_dict()))
    resumed = DepositWatcher(
        chain,
        ["addr-1"],
        policy=2,
        reorg_depth=3,
        state=WatcherState.from_dict(snapshot),
    )
    assert resumed.state == watcher.state

    assert not resumed.poll()

    chain.mine()
    result = resumed.poll()

    assert keys(result.confirmed) == [("tx-c", 0)]
    assert str(result.confirmed[0].amount) == "0.10000000"
    assert result.reverted == ()


def test_a_snapshot_taken_mid_reorg_still_hands_the_deposit_back():
    chain = ScriptedChain()
    watcher = DepositWatcher(chain, ["addr-1"], policy=2, reorg_depth=6)
    original = chain.mine(pay("tx-a"))
    chain.mine()
    watcher.poll()

    snapshot = json.loads(json.dumps(watcher.state.to_dict()))
    resumed = DepositWatcher(
        chain,
        ["addr-1"],
        policy=2,
        reorg_depth=6,
        state=WatcherState.from_dict(snapshot),
    )

    chain.fork(1, length=2)
    result = resumed.poll()

    assert keys(result.reverted) == [("tx-a", 0)]
    assert result.reverted[0].block == original


def test_the_watcher_refuses_an_impossible_setup():
    chain = ScriptedChain()

    with pytest.raises(ValueError):
        DepositWatcher(chain, ["  ", ""])

    with pytest.raises(ValueError):
        DepositWatcher(
            chain, ["addr-1"], start_height=5, state=WatcherState(start_height=5)
        )
