"""The fake has to behave like a chain before it can prove anything."""

from chain_watch import ChainSource
from scripted_chain import ScriptedChain, pay


def test_the_scripted_chain_satisfies_the_source_protocol():
    assert isinstance(ScriptedChain(), ChainSource)


def test_mining_extends_the_chain_and_stalling_leaves_it_alone():
    chain = ScriptedChain()

    chain.mine(count=3)
    assert chain.tip().height == 3

    assert chain.stall() == chain.tip()
    assert chain.tip().height == 3


def test_a_fork_rebuilds_the_chain_with_new_hashes():
    chain = ScriptedChain()
    chain.mine(count=3)
    before = [chain.block_at(height) for height in range(4)]

    chain.fork(2, length=2)

    assert [chain.block_at(height) for height in (0, 1)] == before[:2]
    assert chain.block_at(2) != before[2]
    assert chain.tip().height == 3


def test_transfers_describe_the_current_best_chain_only():
    chain = ScriptedChain()
    chain.mine(pay("tx-a"))

    served = chain.transfers(addresses=["addr-1"], since_height=0)
    assert [transfer.key for transfer in served] == [("tx-a", 0)]

    chain.fork(1)
    assert chain.transfers(addresses=["addr-1"], since_height=0) == []


def test_since_height_and_addresses_narrow_the_answer():
    chain = ScriptedChain()
    chain.mine(pay("tx-a"), pay("tx-x", address="addr-9"))
    chain.mine(pay("tx-b"))

    served = chain.transfers(addresses=["addr-1"], since_height=2)

    assert [transfer.key for transfer in served] == [("tx-b", 0)]
    assert chain.last_query == (("addr-1",), 2)
