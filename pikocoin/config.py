"""Configuration helpers for the prototype node."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class NodeConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    chain_file: Path = Path("data") / "chain.json"
    peers_file: Path = Path("data") / "peers.json"
    genesis_file: Path = Path("config") / "genesis.json"
    chain_id: str = "pikocoin-devnet"
    block_reward: int = 25
    mining_difficulty_prefix: str = "0000"

    def __post_init__(self) -> None:
        if not isinstance(self.chain_file, Path):
            self.chain_file = Path(self.chain_file)
        if not isinstance(self.peers_file, Path):
            self.peers_file = Path(self.peers_file)
        if not isinstance(self.genesis_file, Path):
            self.genesis_file = Path(self.genesis_file)

    @classmethod
    def from_env(cls) -> "NodeConfig":
        chain_file = Path(os.getenv("PIKO_CHAIN_FILE", str(Path("data") / "chain.json")))
        peers_file = Path(os.getenv("PIKO_PEERS_FILE", str(Path("data") / "peers.json")))
        genesis_file = Path(os.getenv("PIKO_GENESIS_FILE", str(Path("config") / "genesis.json")))
        return cls(
            host=os.getenv("PIKO_HOST", "127.0.0.1"),
            port=int(os.getenv("PIKO_PORT", "8080")),
            chain_file=chain_file,
            peers_file=peers_file,
            genesis_file=genesis_file,
            chain_id=os.getenv("PIKO_CHAIN_ID", "pikocoin-devnet"),
            block_reward=int(os.getenv("PIKO_BLOCK_REWARD", "25")),
            mining_difficulty_prefix=os.getenv("PIKO_DIFFICULTY_PREFIX", "0000"),
        )
