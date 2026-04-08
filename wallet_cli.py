from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib import request

from pikocoin.crypto import generate_lamport_keypair
from pikocoin.genesis import GenesisConfig, default_allocation_plan, save_genesis_config


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def cmd_new(args: argparse.Namespace) -> None:
    if args.offline:
        keypair = generate_lamport_keypair()
        wallet = {
            "address": keypair.address,
            "algorithm": keypair.algorithm,
            "public_key": keypair.public_key,
            "private_key": keypair.private_key,
            "warning": "Lamport keys are one-time only. Rotate to a new address after each spend.",
        }
    else:
        wallet = _post_json(f"{args.node}/wallet/new", {})
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(wallet, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wallet saved to {output}")
    print(wallet["address"])


def cmd_balance(args: argparse.Namespace) -> None:
    data = _get_json(f"{args.node}/balance/{args.address}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_metadata(args: argparse.Namespace) -> None:
    data = _get_json(f"{args.node}/metadata")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _resolve_recipient(args: argparse.Namespace) -> str:
    if getattr(args, "recipient_wallet", None):
        wallet = json.loads(Path(args.recipient_wallet).read_text(encoding="utf-8"))
        return wallet["address"]
    return args.recipient


def cmd_claim_status(args: argparse.Namespace) -> None:
    data = _get_json(f"{args.node}/claims/status/{args.owner_address}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_claim_message(args: argparse.Namespace) -> None:
    recipient = _resolve_recipient(args)
    data = _post_json(
        f"{args.node}/claims/message",
        {"external_address": args.owner_address, "recipient": recipient},
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_claim_evm(args: argparse.Namespace) -> None:
    recipient = _resolve_recipient(args)
    data = _post_json(
        f"{args.node}/claims/external/claim",
        {
            "external_address": args.owner_address,
            "recipient": recipient,
            "signature": args.signature,
        },
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_send(args: argparse.Namespace) -> None:
    wallet = json.loads(Path(args.wallet).read_text(encoding="utf-8"))
    payload = {
        "sender": wallet["address"],
        "recipient": args.to,
        "amount": args.amount,
        "note": args.note or "",
        "public_key": wallet["public_key"],
        "private_key": wallet["private_key"],
    }
    if args.nonce is not None:
        payload["nonce"] = args.nonce
    data = _post_json(f"{args.node}/tx/send", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_mine(args: argparse.Namespace) -> None:
    data = _post_json(f"{args.node}/mine", {"miner": args.miner})
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_propose(args: argparse.Namespace) -> None:
    wallet = json.loads(Path(args.wallet).read_text(encoding="utf-8"))
    data = _post_json(f"{args.node}/consensus/propose", {"miner": wallet["address"]})
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_peer_add(args: argparse.Namespace) -> None:
    data = _post_json(f"{args.node}/peers/register", {"peer": args.peer})
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_sync(args: argparse.Namespace) -> None:
    data = _post_json(f"{args.node}/sync", {})
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_consensus_status(args: argparse.Namespace) -> None:
    data = _get_json(f"{args.node}/consensus/status")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _latest_block_ref(node_url: str) -> tuple[int, str]:
    data = _get_json(f"{node_url}/chain")
    chain = data["chain"]
    latest = chain[-1]
    return int(latest["index"]), latest["block_hash"]


def cmd_block_status(args: argparse.Namespace) -> None:
    block_ref = args.block_hash or args.block_index
    if block_ref is None:
        latest_index, _ = _latest_block_ref(args.node)
        block_ref = latest_index
    data = _get_json(f"{args.node}/blocks/status/{block_ref}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_vote(args: argparse.Namespace) -> None:
    wallet = json.loads(Path(args.wallet).read_text(encoding="utf-8"))
    block_index = args.block_index
    block_hash = args.block_hash
    if block_index is None or block_hash is None:
        latest_index, latest_hash = _latest_block_ref(args.node)
        if block_index is None:
            block_index = latest_index
        if block_hash is None:
            block_hash = latest_hash
    payload = {
        "validator": wallet["address"],
        "block_index": block_index,
        "block_hash": block_hash,
        "note": args.note or "",
    }
    data = _post_json(f"{args.node}/consensus/vote", payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _parse_allocations(items: list[str]) -> dict[str, int]:
    balances: dict[str, int] = {}
    for item in items:
        address, amount = item.split("=", 1)
        balances[address] = int(amount)
    return balances


def cmd_create_genesis(args: argparse.Namespace) -> None:
    validators = []
    for wallet_path in args.validator_wallet:
        wallet = json.loads(Path(wallet_path).read_text(encoding="utf-8"))
        validators.append(wallet["address"])

    if args.alloc:
        balances = _parse_allocations(args.alloc)
        allocations = [
            {"label": "Custom Allocation", "address": address, "amount": amount, "note": "Created via CLI override."}
            for address, amount in balances.items()
        ]
    else:
        balances, allocations = default_allocation_plan(owner_address=args.owner_address)
    for wallet_path in args.validator_wallet:
        wallet = json.loads(Path(wallet_path).read_text(encoding="utf-8"))
        balances.setdefault(wallet["address"], args.validator_stake)
        allocations.append(
            {
                "label": "Validator Bootstrap Stake",
                "address": wallet["address"],
                "amount": args.validator_stake,
                "note": "Bootstrap balance injected for validator startup.",
            }
        )

    genesis = GenesisConfig(
        chain_id=args.chain_id,
        network_name=args.network_name,
        token_name=args.token_name,
        token_symbol=args.token_symbol,
        token_decimals=args.token_decimals,
        icon_path=args.icon_path,
        description=args.description,
        genesis_time=round(time.time(), 6),
        block_reward=args.block_reward,
        difficulty_prefix=args.difficulty_prefix,
        balances=balances,
        validators=validators,
        allocations=allocations,
    )
    output = Path(args.out)
    save_genesis_config(output, genesis)
    print(f"genesis saved to {output}")
    print(json.dumps(genesis.to_dict(), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pikocoin wallet and node utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    wallet_new = subparsers.add_parser("new-wallet", help="Generate a new Lamport wallet via node API")
    wallet_new.add_argument("--node", default="http://127.0.0.1:8080")
    wallet_new.add_argument("--out", default="wallets/wallet.json")
    wallet_new.add_argument("--offline", action="store_true")
    wallet_new.set_defaults(func=cmd_new)

    balance = subparsers.add_parser("balance", help="Check balance for an address")
    balance.add_argument("address")
    balance.add_argument("--node", default="http://127.0.0.1:8080")
    balance.set_defaults(func=cmd_balance)

    metadata = subparsers.add_parser("metadata", help="Read chain branding and token metadata")
    metadata.add_argument("--node", default="http://127.0.0.1:8080")
    metadata.set_defaults(func=cmd_metadata)

    claim_status = subparsers.add_parser("claim-status", help="Inspect an external allocation claim status")
    claim_status.add_argument("--owner-address", required=True)
    claim_status.add_argument("--node", default="http://127.0.0.1:8080")
    claim_status.set_defaults(func=cmd_claim_status)

    claim_message = subparsers.add_parser("claim-message", help="Build the message your EVM wallet must sign")
    claim_message.add_argument("--owner-address", required=True)
    claim_message.add_argument("--recipient", default="")
    claim_message.add_argument("--recipient-wallet")
    claim_message.add_argument("--node", default="http://127.0.0.1:8080")
    claim_message.set_defaults(func=cmd_claim_message)

    claim_evm = subparsers.add_parser("claim-evm", help="Submit a signed EVM allocation claim to the node")
    claim_evm.add_argument("--owner-address", required=True)
    claim_evm.add_argument("--recipient", default="")
    claim_evm.add_argument("--recipient-wallet")
    claim_evm.add_argument("--signature", required=True)
    claim_evm.add_argument("--node", default="http://127.0.0.1:8080")
    claim_evm.set_defaults(func=cmd_claim_evm)

    send = subparsers.add_parser("send", help="Send a transaction using a saved wallet")
    send.add_argument("--wallet", required=True)
    send.add_argument("--to", required=True)
    send.add_argument("--amount", required=True, type=int)
    send.add_argument("--note", default="")
    send.add_argument("--nonce", type=int)
    send.add_argument("--node", default="http://127.0.0.1:8080")
    send.set_defaults(func=cmd_send)

    mine = subparsers.add_parser("mine", help="Mine a block with the given miner address")
    mine.add_argument("--miner", required=True)
    mine.add_argument("--node", default="http://127.0.0.1:8080")
    mine.set_defaults(func=cmd_mine)

    propose = subparsers.add_parser("propose", help="Propose the next validator block using a wallet file")
    propose.add_argument("--wallet", required=True)
    propose.add_argument("--node", default="http://127.0.0.1:8080")
    propose.set_defaults(func=cmd_propose)

    peer_add = subparsers.add_parser("add-peer", help="Register a peer node")
    peer_add.add_argument("--peer", required=True)
    peer_add.add_argument("--node", default="http://127.0.0.1:8080")
    peer_add.set_defaults(func=cmd_peer_add)

    sync = subparsers.add_parser("sync", help="Sync chain state from known peers")
    sync.add_argument("--node", default="http://127.0.0.1:8080")
    sync.set_defaults(func=cmd_sync)

    consensus_status = subparsers.add_parser("consensus-status", help="Read validator rotation status from a node")
    consensus_status.add_argument("--node", default="http://127.0.0.1:8080")
    consensus_status.set_defaults(func=cmd_consensus_status)

    block_status = subparsers.add_parser("block-status", help="Read voting and finality state for a block")
    block_status.add_argument("--block-index")
    block_status.add_argument("--block-hash")
    block_status.add_argument("--node", default="http://127.0.0.1:8080")
    block_status.set_defaults(func=cmd_block_status)

    vote = subparsers.add_parser("vote", help="Cast a validator vote for a block using a wallet file")
    vote.add_argument("--wallet", required=True)
    vote.add_argument("--block-index", type=int)
    vote.add_argument("--block-hash")
    vote.add_argument("--note", default="")
    vote.add_argument("--node", default="http://127.0.0.1:8080")
    vote.set_defaults(func=cmd_vote)

    create_genesis = subparsers.add_parser("create-genesis", help="Generate a shared genesis file for validators")
    create_genesis.add_argument("--validator-wallet", action="append", default=[])
    create_genesis.add_argument("--alloc", action="append", default=[])
    create_genesis.add_argument("--owner-address", default="0x30514237625b9e4206c728ff551725b4bf9d4a85")
    create_genesis.add_argument("--validator-stake", type=int, default=1000)
    create_genesis.add_argument("--chain-id", default="pikocoin-mainnet-alpha")
    create_genesis.add_argument("--network-name", default="Pikocoin Sovereign Network")
    create_genesis.add_argument("--token-name", default="Pikocoin")
    create_genesis.add_argument("--token-symbol", default="PIKO")
    create_genesis.add_argument("--token-decimals", type=int, default=0)
    create_genesis.add_argument("--icon-path", default="assets/pikocoin-icon.png")
    create_genesis.add_argument(
        "--description",
        default="Privacy-oriented, validator-driven sovereign blockchain prototype.",
    )
    create_genesis.add_argument("--block-reward", type=int, default=25)
    create_genesis.add_argument("--difficulty-prefix", default="00")
    create_genesis.add_argument("--out", default="config/genesis.json")
    create_genesis.set_defaults(func=cmd_create_genesis)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
