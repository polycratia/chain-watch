"""How deep a block must be before a transfer counts as a deposit.

Depth is a policy, not a constant: a chain with fast blocks and a chain that
settles slowly do not deserve the same number. A :class:`ConfirmationPolicy`
carries one default plus per-asset overrides, and the watcher asks it about
every transfer it holds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

__all__ = ["ConfirmationPolicy", "DepthSpec"]


def _validate_depth(depth: int, label: str) -> int:
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise TypeError(f"confirmation depth for {label} must be an int: {depth!r}")
    if depth < 1:
        raise ValueError(f"confirmation depth for {label} must be at least 1: {depth}")
    return depth


@dataclass(frozen=True, slots=True)
class ConfirmationPolicy:
    """Required depth per asset, falling back to ``default``.

    >>> policy = ConfirmationPolicy(default=6, per_asset={"USDT": 12})
    >>> policy.depth_for("BTC"), policy.depth_for("USDT")
    (6, 12)

    Asset names are matched exactly, the way the chain source spells them.
    """

    default: int = 1
    per_asset: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_depth(self.default, "the default")
        overrides: dict[str, int] = {}
        for asset, depth in dict(self.per_asset).items():
            if not asset:
                raise ValueError("asset must not be empty")
            _validate_depth(depth, asset)
            overrides[asset] = depth
        object.__setattr__(self, "per_asset", MappingProxyType(overrides))

    @classmethod
    def coerce(cls, spec: DepthSpec) -> ConfirmationPolicy:
        """Accept a policy, a plain depth, or a mapping of per-asset depths.

        A mapping leaves the default at one confirmation, so an asset nobody
        listed is still reported rather than held forever.
        """
        if isinstance(spec, ConfirmationPolicy):
            return spec
        if isinstance(spec, Mapping):
            return cls(per_asset=spec)
        if isinstance(spec, int) and not isinstance(spec, bool):
            return cls(default=spec)
        raise TypeError(
            f"expected a ConfirmationPolicy, an int or a mapping of depths: {spec!r}"
        )

    def depth_for(self, asset: str) -> int:
        """Confirmations ``asset`` needs before a transfer is a deposit."""
        return self.per_asset.get(asset, self.default)

    def is_confirmed(self, asset: str, confirmations: int) -> bool:
        return confirmations >= self.depth_for(asset)

    @property
    def max_depth(self) -> int:
        """The deepest requirement anywhere in the policy."""
        return max([self.default, *self.per_asset.values()])

    def with_asset(self, asset: str, depth: int) -> ConfirmationPolicy:
        """Return a copy that requires ``depth`` for ``asset``."""
        return ConfirmationPolicy(self.default, {**self.per_asset, asset: depth})

    def __str__(self) -> str:
        overrides = ", ".join(
            f"{asset}={depth}" for asset, depth in sorted(self.per_asset.items())
        )
        return f"default={self.default}" + (f", {overrides}" if overrides else "")


DepthSpec = ConfirmationPolicy | Mapping[str, int] | int
