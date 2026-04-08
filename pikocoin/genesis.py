"""Genesis configuration helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json


DEFAULT_FAUCET_ADDRESS = "piko1genesisreserve000000000000000000000000"
DEFAULT_OWNER_ADDRESS = "0x30514237625b9e4206c728ff551725b4bf9d4a85"


def _normalize_allocation_address(address: str) -> str:
    value = address.strip()
    if value.lower().startswith("0x") and len(value) == 42:
        return value.lower()
    return value


def default_allocation_plan(owner_address: str = DEFAULT_OWNER_ADDRESS) -> tuple[dict[str, int], list[dict[str, Any]]]:
    allocations = [
        {
            "label": "Founder and Governance Treasury",
            "address": _normalize_allocation_address(owner_address),
            "amount": 180_000_000,
            "note": "Primary founder reserve and governance treasury.",
        },
        {
            "label": "Ecosystem Treasury",
            "address": "piko1ecosystemreserve0000000000000000000000",
            "amount": 220_000_000,
            "note": "Liquidity programs, ecosystem grants, and strategic growth.",
        },
        {
            "label": "Community Incentives",
            "address": "piko1communityrewards000000000000000000000",
            "amount": 200_000_000,
            "note": "Airdrops, quests, referrals, and community mining events.",
        },
        {
            "label": "Validator Security Rewards",
            "address": "piko1validatorrewards000000000000000000000",
            "amount": 150_000_000,
            "note": "Bootstraps validator incentives before ongoing block rewards take over.",
        },
        {
            "label": "Liquidity and Market Operations",
            "address": "piko1liquidityreserve000000000000000000000",
            "amount": 100_000_000,
            "note": "Cross-exchange liquidity, MM operations, and launch support.",
        },
        {
            "label": "AI and Privacy R&D Fund",
            "address": "piko1aiprivacyresearch00000000000000000000",
            "amount": 100_000_000,
            "note": "Funds zk, PQC, AI coprocessor, and privacy research.",
        },
        {
            "label": "Foundation Operations",
            "address": "piko1foundationops0000000000000000000000",
            "amount": 50_000_000,
            "note": "Audits, legal, infrastructure, and long-run operations.",
        },
    ]
    balances = {entry["address"]: int(entry["amount"]) for entry in allocations}
    return balances, allocations


@dataclass(slots=True)
class GenesisConfig:
    chain_id: str = "pikocoin-devnet"
    network_name: str = "Pikocoin Sovereign Network"
    token_name: str = "Pikocoin"
    token_symbol: str = "PIKO"
    token_decimals: int = 0
    icon_path: str = "assets/pikocoin-icon.png"
    description: str = "Privacy-oriented, validator-driven sovereign blockchain prototype."
    genesis_time: float = 0.0
    block_reward: int = 25
    difficulty_prefix: str = "0000"
    balances: dict[str, int] = field(default_factory=lambda: default_allocation_plan()[0])
    validators: list[str] = field(default_factory=list)
    allocations: list[dict[str, Any]] = field(default_factory=lambda: default_allocation_plan()[1])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GenesisConfig":
        return cls(
            chain_id=payload.get("chain_id", "pikocoin-devnet"),
            network_name=payload.get("network_name", "Pikocoin Sovereign Network"),
            token_name=payload.get("token_name", "Pikocoin"),
            token_symbol=payload.get("token_symbol", "PIKO"),
            token_decimals=int(payload.get("token_decimals", 0)),
            icon_path=payload.get("icon_path", "assets/pikocoin-icon.png"),
            description=payload.get(
                "description",
                "Privacy-oriented, validator-driven sovereign blockchain prototype.",
            ),
            genesis_time=float(payload.get("genesis_time", 0.0)),
            block_reward=int(payload.get("block_reward", 25)),
            difficulty_prefix=payload.get("difficulty_prefix", "0000"),
            balances={_normalize_allocation_address(key): int(value) for key, value in payload.get("balances", {}).items()},
            validators=list(payload.get("validators", [])),
            allocations=[
                item | {"address": _normalize_allocation_address(str(item.get("address", "")))}
                for item in payload.get("allocations", [])
            ],
        )


def default_genesis_config(
    chain_id: str = "pikocoin-devnet",
    block_reward: int = 25,
    difficulty_prefix: str = "0000",
    owner_address: str = DEFAULT_OWNER_ADDRESS,
) -> GenesisConfig:
    balances, allocations = default_allocation_plan(owner_address=owner_address)
    return GenesisConfig(
        chain_id=chain_id,
        network_name="Pikocoin Sovereign Network",
        token_name="Pikocoin",
        token_symbol="PIKO",
        token_decimals=0,
        icon_path="assets/pikocoin-icon.png",
        description="Privacy-oriented, validator-driven sovereign blockchain prototype.",
        genesis_time=0.0,
        block_reward=block_reward,
        difficulty_prefix=difficulty_prefix,
        balances=balances,
        allocations=allocations,
    )


def load_genesis_config(
    genesis_file: Path,
    chain_id: str,
    block_reward: int,
    difficulty_prefix: str,
    owner_address: str = DEFAULT_OWNER_ADDRESS,
) -> GenesisConfig:
    if genesis_file.exists():
        with genesis_file.open("r", encoding="utf-8") as handle:
            return GenesisConfig.from_dict(json.load(handle))
    return default_genesis_config(
        chain_id=chain_id,
        block_reward=block_reward,
        difficulty_prefix=difficulty_prefix,
        owner_address=owner_address,
    )


def save_genesis_config(genesis_file: Path, genesis: GenesisConfig) -> None:
    genesis_file.parent.mkdir(parents=True, exist_ok=True)
    with genesis_file.open("w", encoding="utf-8") as handle:
        json.dump(genesis.to_dict(), handle, ensure_ascii=False, indent=2)
