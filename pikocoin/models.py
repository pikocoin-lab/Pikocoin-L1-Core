"""Core data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import time


@dataclass(slots=True)
class Transaction:
    sender: str
    recipient: str
    amount: int
    nonce: int
    timestamp: float = field(default_factory=lambda: round(time.time(), 6))
    note: str = ""
    algorithm: str = "LAMPORT_SHA256"
    public_key: list[list[str]] = field(default_factory=list)
    signature: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Transaction":
        return cls(**payload)


@dataclass(slots=True)
class Block:
    index: int
    timestamp: float
    previous_hash: str
    nonce: int
    miner: str
    transactions: list[dict[str, Any]]
    merkle_root: str
    difficulty_prefix: str
    block_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Block":
        return cls(**payload)


@dataclass(slots=True)
class Vote:
    validator: str
    block_hash: str
    block_index: int
    timestamp: float = field(default_factory=lambda: round(time.time(), 6))
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Vote":
        return cls(**payload)
