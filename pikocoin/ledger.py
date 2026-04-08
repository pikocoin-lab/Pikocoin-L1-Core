"""Prototype blockchain state machine."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from threading import RLock
from typing import Any
import json
import time

from .config import NodeConfig
from .crypto import (
    address_from_public_key,
    block_hash,
    canonical_transaction_payload,
    verify_post_quantum_signature,
)
from .evm import build_claim_message, normalize_evm_address, verify_personal_signature
from .genesis import GenesisConfig, load_genesis_config
from .models import Block, Transaction, Vote


def _merkle_root(transactions: list[dict[str, Any]]) -> str:
    if not transactions:
        return sha256(b"").hexdigest()
    level = [sha256(json.dumps(tx, sort_keys=True).encode("utf-8")).hexdigest() for tx in transactions]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            sha256(f"{level[index]}{level[index + 1]}".encode("utf-8")).hexdigest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def _tx_digest(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class Ledger:
    """Single-node prototype ledger with persistent state."""

    def __init__(self, config: NodeConfig):
        self.config = config
        self.genesis: GenesisConfig = load_genesis_config(
            config.genesis_file,
            chain_id=config.chain_id,
            block_reward=config.block_reward,
            difficulty_prefix=config.mining_difficulty_prefix,
        )
        self.chain_id = self.genesis.chain_id
        self.block_reward = self.genesis.block_reward
        self.difficulty_prefix = self.genesis.difficulty_prefix
        self.validators = list(self.genesis.validators)
        self.consensus_mode = "round_robin_validators" if self.validators else "open-mining"
        self.chain: list[Block] = []
        self.pending_transactions: list[Transaction] = []
        self.balances: dict[str, int] = defaultdict(int, self.genesis.balances)
        self.nonces: dict[str, int] = defaultdict(int)
        self.spent_one_time_addresses: set[str] = set()
        self.peers: set[str] = set()
        self.block_votes: dict[str, list[Vote]] = {}
        self.finalized_height: int = 0
        self.lock = RLock()
        self.config.chain_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.peers_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.chain_id = self.chain_id
        self.config.block_reward = self.block_reward
        self.config.mining_difficulty_prefix = self.difficulty_prefix
        self.expected_genesis_block = self._build_block(
            index=0,
            previous_hash="0" * 64,
            proposer="genesis",
            transactions=[],
            timestamp=self.genesis.genesis_time,
        )
        if self.config.chain_file.exists():
            self._load()
        else:
            self._create_genesis_block()
        self._load_peers()

    def _create_genesis_block(self) -> None:
        self.balances = defaultdict(int, self.genesis.balances)
        self.chain = [self.expected_genesis_block]
        self.block_votes = {}
        self.finalized_height = 0
        self._save()

    def _load(self) -> None:
        with self.config.chain_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        self.chain = [Block.from_dict(item) for item in payload["chain"]]
        self.pending_transactions = [Transaction.from_dict(item) for item in payload["pending_transactions"]]
        self.balances = defaultdict(int, payload["balances"])
        self.nonces = defaultdict(int, payload["nonces"])
        self.spent_one_time_addresses = set(payload["spent_one_time_addresses"])
        self.block_votes = {
            block_hash: [Vote.from_dict(item) for item in votes]
            for block_hash, votes in payload.get("block_votes", {}).items()
        }
        self.finalized_height = int(payload.get("finalized_height", 0))
        self._bootstrap_vote_state()

    def _load_peers(self) -> None:
        if not self.config.peers_file.exists():
            return
        with self.config.peers_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.peers = set(payload.get("peers", []))

    def _save(self) -> None:
        payload = {
            "chain": [block.to_dict() for block in self.chain],
            "pending_transactions": [tx.to_dict() for tx in self.pending_transactions],
            "balances": dict(self.balances),
            "nonces": dict(self.nonces),
            "spent_one_time_addresses": sorted(self.spent_one_time_addresses),
            "block_votes": {
                block_hash: [vote.to_dict() for vote in votes]
                for block_hash, votes in self.block_votes.items()
            },
            "finalized_height": self.finalized_height,
            "meta": {
                "chain_id": self.chain_id,
                "height": len(self.chain) - 1,
                "consensus_mode": self.consensus_mode,
                "validators": self.validators,
            },
        }
        with self.config.chain_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        self._save_peers()

    def _save_peers(self) -> None:
        with self.config.peers_file.open("w", encoding="utf-8") as handle:
            json.dump({"peers": sorted(self.peers)}, handle, ensure_ascii=False, indent=2)

    def _bootstrap_vote_state(self) -> None:
        if not self.validators:
            self.finalized_height = len(self.chain) - 1
            return
        for block in self.chain[1:]:
            self._record_vote(
                Vote(
                    validator=block.miner,
                    block_hash=block.block_hash,
                    block_index=block.index,
                    note="Implicit proposer vote",
                    extra={"implicit": True},
                ),
                allow_duplicate=True,
            )
        self._recompute_finality()

    def _build_block(
        self,
        index: int,
        previous_hash: str,
        proposer: str,
        transactions: list[dict[str, Any]],
        timestamp: float | None = None,
    ) -> Block:
        block = Block(
            index=index,
            timestamp=round(time.time(), 6) if timestamp is None else round(float(timestamp), 6),
            previous_hash=previous_hash,
            nonce=0,
            miner=proposer,
            transactions=transactions,
            merkle_root=_merkle_root(transactions),
            difficulty_prefix=self.difficulty_prefix,
        )
        while True:
            candidate = block.to_dict() | {"block_hash": ""}
            candidate_hash = block_hash(candidate)
            if candidate_hash.startswith(self.difficulty_prefix):
                block.block_hash = candidate_hash
                return block
            block.nonce += 1

    def _initial_state(self) -> tuple[dict[str, int], dict[str, int], set[str]]:
        return defaultdict(int, self.genesis.balances), defaultdict(int), set()

    def vote_threshold(self) -> int:
        if not self.validators:
            return 0
        return (2 * len(self.validators)) // 3 + 1

    def _record_vote(self, vote: Vote, allow_duplicate: bool = False) -> tuple[bool, str]:
        existing_for_block = self.block_votes.setdefault(vote.block_hash, [])
        for existing_vote in existing_for_block:
            if existing_vote.validator == vote.validator:
                if allow_duplicate:
                    return True, "Vote already tracked."
                return False, "Validator already voted for this block."
        for votes in self.block_votes.values():
            for existing_vote in votes:
                if existing_vote.validator == vote.validator and existing_vote.block_index == vote.block_index:
                    if allow_duplicate and existing_vote.block_hash == vote.block_hash:
                        return True, "Vote already tracked."
                    return False, "Validator already cast a vote for this block height."
        existing_for_block.append(vote)
        return True, "Vote recorded."

    def _vote_count(self, block_hash: str) -> int:
        return len({vote.validator for vote in self.block_votes.get(block_hash, [])})

    def _recompute_finality(self) -> None:
        if not self.validators:
            self.finalized_height = len(self.chain) - 1
            return
        threshold = self.vote_threshold()
        finalized_height = 0
        for block in self.chain[1:]:
            if self._vote_count(block.block_hash) >= threshold:
                finalized_height = block.index
            else:
                break
        self.finalized_height = finalized_height

    def _validate_header(self, block_dict: dict[str, Any], expected_index: int, previous_hash: str) -> tuple[bool, str]:
        if block_dict["index"] != expected_index:
            return False, f"Unexpected block index {block_dict['index']}, expected {expected_index}."
        if block_dict["previous_hash"] != previous_hash:
            return False, "Previous hash mismatch."
        if block_dict["difficulty_prefix"] != self.difficulty_prefix:
            return False, "Difficulty prefix mismatch."
        expected_proposer = self.expected_proposer(expected_index)
        if expected_proposer and block_dict["miner"] != expected_proposer:
            return False, f"Unexpected proposer {block_dict['miner']}, expected {expected_proposer}."
        if block_dict["merkle_root"] != _merkle_root(block_dict["transactions"]):
            return False, "Merkle root mismatch."
        candidate = dict(block_dict)
        recorded_hash = candidate.get("block_hash", "")
        candidate["block_hash"] = ""
        if block_hash(candidate) != recorded_hash:
            return False, "Block hash mismatch."
        if not recorded_hash.startswith(self.difficulty_prefix):
            return False, "Block does not satisfy difficulty prefix."
        return True, "Block header is valid."

    def _apply_transactions_to_state(
        self,
        block_dict: dict[str, Any],
        balances: dict[str, int],
        nonces: dict[str, int],
        spent_addresses: set[str],
    ) -> tuple[bool, str]:
        transactions = block_dict["transactions"]
        if not transactions:
            return False, "Block must contain a coinbase transaction."
        coinbase = transactions[0]
        if coinbase["sender"] != "COINBASE":
            return False, "First transaction must be coinbase."
        if int(coinbase["amount"]) != self.block_reward:
            return False, "Invalid block reward."
        if coinbase["recipient"] != block_dict["miner"]:
            return False, "Coinbase recipient must match block proposer."
        balances[coinbase["recipient"]] += int(coinbase["amount"])

        for tx_dict in transactions[1:]:
            sender = tx_dict["sender"]
            recipient = tx_dict["recipient"]
            amount = int(tx_dict["amount"])
            if tx_dict.get("algorithm") == "EVM_PERSONAL_CLAIM":
                valid, message = self._validate_claim_transaction(tx_dict, balances, nonces)
                if not valid:
                    return False, message
                balances[sender] -= amount
                balances[recipient] += amount
                nonces[sender] += 1
                continue
            if sender == "COINBASE":
                return False, "Coinbase transaction can only appear once."
            if amount <= 0:
                return False, "Transaction amount must be positive."
            if sender == recipient:
                return False, "Sender and recipient must differ."
            if sender in spent_addresses:
                return False, f"One-time address reused in block {block_dict['index']}: {sender}"
            if balances[sender] < amount:
                return False, f"Insufficient balance for {sender} in block {block_dict['index']}"
            if tx_dict["nonce"] != nonces[sender]:
                return False, f"Invalid nonce for {sender} in block {block_dict['index']}"
            if address_from_public_key(tx_dict["public_key"], tx_dict["algorithm"]) != sender:
                return False, f"Address mismatch in block {block_dict['index']}"
            message_bytes = canonical_transaction_payload(tx_dict)
            if not verify_post_quantum_signature(
                message_bytes,
                tx_dict["algorithm"],
                tx_dict["public_key"],
                tx_dict["signature"],
            ):
                return False, f"Invalid signature in block {block_dict['index']}"
            balances[sender] -= amount
            balances[recipient] += amount
            nonces[sender] += 1
            spent_addresses.add(sender)
        return True, "Block transactions are valid."

    def _remove_included_pending(self, transactions: list[dict[str, Any]]) -> None:
        included = {_tx_digest(tx) for tx in transactions[1:]}
        self.pending_transactions = [
            tx for tx in self.pending_transactions
            if _tx_digest(tx.to_dict()) not in included
        ]

    def _apply_committed_block(self, block: Block) -> None:
        self._apply_transactions_to_state(block.to_dict(), self.balances, self.nonces, self.spent_one_time_addresses)
        self.chain.append(block)
        if self.validators and block.miner in self.validators:
            self._record_vote(
                Vote(
                    validator=block.miner,
                    block_hash=block.block_hash,
                    block_index=block.index,
                    note="Implicit proposer vote",
                    extra={"implicit": True},
                ),
                allow_duplicate=True,
            )
        self._remove_included_pending(block.transactions)
        self._recompute_finality()
        self._save()

    def get_status(self) -> dict[str, Any]:
        latest = self.chain[-1]
        return {
            "chain_id": self.chain_id,
            "height": len(self.chain) - 1,
            "latest_hash": latest.block_hash,
            "pending_transactions": len(self.pending_transactions),
            "difficulty_prefix": self.difficulty_prefix,
            "peer_count": len(self.peers),
            "validator_count": len(self.validators),
            "consensus_mode": self.consensus_mode,
            "next_proposer": self.expected_proposer(len(self.chain)),
            "vote_threshold": self.vote_threshold(),
            "finalized_height": self.finalized_height,
        }

    def get_metadata(self, base_url: str | None = None) -> dict[str, Any]:
        metadata = {
            "chain_id": self.chain_id,
            "network_name": self.genesis.network_name,
            "token_name": self.genesis.token_name,
            "token_symbol": self.genesis.token_symbol,
            "token_decimals": self.genesis.token_decimals,
            "description": self.genesis.description,
            "icon_path": self.genesis.icon_path,
            "total_supply": sum(int(amount) for amount in self.genesis.balances.values()),
            "allocations": list(self.genesis.allocations),
            "consensus_mode": self.consensus_mode,
            "validator_count": len(self.validators),
            "vote_threshold": self.vote_threshold(),
        }
        if base_url:
            metadata["icon_url"] = f"{base_url.rstrip('/')}/icon"
            metadata["metadata_url"] = f"{base_url.rstrip('/')}/metadata"
        return metadata

    def get_balance(self, address: str) -> int:
        return self.balances[address]

    def get_next_nonce(self, address: str) -> int:
        return self.nonces[address]

    def list_peers(self) -> list[str]:
        return sorted(self.peers)

    def list_validators(self) -> list[str]:
        return list(self.validators)

    def _get_block_by_reference(self, block_ref: str | int) -> Block | None:
        if isinstance(block_ref, int) or str(block_ref).isdigit():
            block_index = int(block_ref)
            if 0 <= block_index < len(self.chain):
                return self.chain[block_index]
            return None
        block_hash = str(block_ref)
        for block in self.chain:
            if block.block_hash == block_hash:
                return block
        return None

    def get_block_status(self, block_ref: str | int) -> dict[str, Any]:
        block = self._get_block_by_reference(block_ref)
        if block is None:
            raise ValueError("Block not found.")
        votes = [vote.to_dict() for vote in self.block_votes.get(block.block_hash, [])]
        threshold = self.vote_threshold()
        vote_count = self._vote_count(block.block_hash)
        finalized = block.index <= self.finalized_height
        if block.index == 0:
            confirmation_status = "finalized"
        elif finalized:
            confirmation_status = "finalized"
        elif threshold == 0:
            confirmation_status = "confirmed"
        elif vote_count > 0:
            confirmation_status = "voting"
        else:
            confirmation_status = "proposed"
        return {
            "block_hash": block.block_hash,
            "block_index": block.index,
            "proposer": block.miner,
            "vote_count": vote_count,
            "vote_threshold": threshold,
            "finalized": finalized,
            "finalized_height": self.finalized_height,
            "confirmation_status": confirmation_status,
            "votes": votes,
        }

    def export_vote_state(self) -> dict[str, Any]:
        return {
            "block_votes": {
                block_hash: [vote.to_dict() for vote in votes]
                for block_hash, votes in self.block_votes.items()
            },
            "finalized_height": self.finalized_height,
            "vote_threshold": self.vote_threshold(),
        }

    def expected_proposer(self, block_index: int) -> str | None:
        if not self.validators:
            return None
        if block_index <= 0:
            return "genesis"
        return self.validators[(block_index - 1) % len(self.validators)]

    def can_propose(self, address: str, block_index: int | None = None) -> tuple[bool, str]:
        target_index = block_index if block_index is not None else len(self.chain)
        expected = self.expected_proposer(target_index)
        if expected is None:
            return True, "Open mining mode."
        if address != expected:
            return False, f"Validator {address} is not the selected proposer for block {target_index}. Expected {expected}."
        return True, "Validator is the selected proposer."

    def get_claim_status(self, external_address: str) -> dict[str, Any]:
        normalized = normalize_evm_address(external_address)
        pending = any(
            tx.algorithm == "EVM_PERSONAL_CLAIM" and tx.sender.lower() == normalized
            for tx in self.pending_transactions
        )
        return {
            "address": normalized,
            "available_balance": self.balances[normalized],
            "claim_nonce": self.nonces[normalized],
            "claimed": self.balances[normalized] == 0 and self.nonces[normalized] > 0,
            "pending": pending,
            "eligible": normalized in self.genesis.balances,
        }

    def get_claim_message(self, external_address: str, recipient: str) -> dict[str, Any]:
        normalized = normalize_evm_address(external_address)
        amount = self.balances[normalized]
        return {
            "external_address": normalized,
            "recipient": recipient,
            "amount": amount,
            "message": build_claim_message(self.chain_id, normalized, recipient, amount),
            "claim_status": self.get_claim_status(normalized),
        }

    def _validate_claim_transaction(self, tx_dict: dict[str, Any], balances: dict[str, int], nonces: dict[str, int]) -> tuple[bool, str]:
        try:
            sender = normalize_evm_address(tx_dict["sender"])
        except ValueError as exc:
            return False, str(exc)
        recipient = tx_dict["recipient"]
        amount = int(tx_dict["amount"])
        if not recipient.startswith("piko1"):
            return False, "External claims must target a native piko1 address."
        if sender not in self.genesis.balances:
            return False, "External address is not part of the genesis allocation table."
        if tx_dict["nonce"] != nonces[sender]:
            return False, "Invalid claim nonce."
        if amount <= 0:
            return False, "Claim amount must be positive."
        if balances[sender] <= 0:
            return False, "No unclaimed allocation remains for this external address."
        if amount != balances[sender]:
            return False, "Claim amount must equal the remaining external allocation."
        signature_hex = str(tx_dict.get("extra", {}).get("evm_signature", "")).strip()
        if not signature_hex:
            return False, "Missing EVM signature."
        expected_message = build_claim_message(self.chain_id, sender, recipient, amount)
        if not verify_personal_signature(sender, expected_message, signature_hex):
            return False, "EVM claim signature verification failed."
        return True, "External claim is valid."

    def build_vote(
        self,
        validator: str,
        block_hash: str,
        block_index: int,
        note: str = "",
        extra: dict[str, Any] | None = None,
    ) -> Vote:
        return Vote(
            validator=validator,
            block_hash=block_hash,
            block_index=block_index,
            note=note,
            extra=extra or {},
        )

    def add_vote(self, vote: Vote) -> tuple[bool, str]:
        with self.lock:
            if not self.validators:
                return False, "Voting is disabled in open-mining mode."
            if vote.validator not in self.validators:
                return False, "Validator is not in the active validator set."
            if vote.block_index <= 0:
                return False, "Genesis block does not require validator votes."
            if vote.block_index >= len(self.chain):
                return False, "Target block index is not on the local chain."

            block = self.chain[vote.block_index]
            if block.block_hash != vote.block_hash:
                return False, "Block hash does not match the local canonical block."

            accepted, message = self._record_vote(vote)
            if not accepted:
                return False, message
            self._recompute_finality()
            self._save()
            if vote.block_index <= self.finalized_height:
                return True, "Vote accepted and block is finalized."
            return True, "Vote accepted."

    def merge_vote_state(
        self,
        vote_payload: dict[str, list[dict[str, Any]]] | None,
        finalized_height: int | None = None,
    ) -> tuple[bool, str]:
        with self.lock:
            if not self.validators:
                return False, "Vote sync is not required in open-mining mode."
            if not vote_payload:
                return False, "No vote state supplied."

            before_counts = {block_hash: self._vote_count(block_hash) for block_hash in self.block_votes}
            before_finalized = self.finalized_height
            for block_hash, votes in vote_payload.items():
                block = self._get_block_by_reference(block_hash)
                if block is None:
                    continue
                for vote_dict in votes:
                    vote = Vote.from_dict(vote_dict)
                    if vote.validator not in self.validators:
                        continue
                    if vote.block_hash != block.block_hash or int(vote.block_index) != block.index:
                        continue
                    self._record_vote(vote, allow_duplicate=True)

            self._recompute_finality()
            if finalized_height is not None:
                self.finalized_height = min(int(finalized_height), self.finalized_height)

            after_counts = {block_hash: self._vote_count(block_hash) for block_hash in self.block_votes}
            if after_counts == before_counts and self.finalized_height == before_finalized:
                return False, "Vote state already up to date."
            self._save()
            return True, "Vote state merged."

    def add_peer(self, peer: str) -> tuple[bool, str]:
        normalized = peer.strip().rstrip("/")
        if not normalized.startswith("http://") and not normalized.startswith("https://"):
            return False, "Peer must start with http:// or https://"
        if normalized in self.peers:
            return False, "Peer already registered."
        self.peers.add(normalized)
        self._save_peers()
        return True, "Peer registered."

    def build_transaction(
        self,
        sender: str,
        recipient: str,
        amount: int,
        nonce: int,
        public_key: list[list[str]],
        signature: list[str],
        note: str = "",
        algorithm: str = "LAMPORT_SHA256",
        extra: dict[str, Any] | None = None,
    ) -> Transaction:
        return Transaction(
            sender=sender,
            recipient=recipient,
            amount=amount,
            nonce=nonce,
            public_key=public_key,
            signature=signature,
            note=note,
            algorithm=algorithm,
            extra=extra or {},
        )

    def add_transaction(self, tx: Transaction) -> tuple[bool, str]:
        with self.lock:
            if tx.algorithm == "EVM_PERSONAL_CLAIM":
                tx.sender = normalize_evm_address(tx.sender)
                valid, message = self._validate_claim_transaction(tx.to_dict(), self.balances, self.nonces)
                if not valid:
                    return False, message
                if any(
                    pending.sender.lower() == tx.sender and pending.algorithm == "EVM_PERSONAL_CLAIM"
                    for pending in self.pending_transactions
                ):
                    return False, "A pending claim already exists for this external address."
                self.pending_transactions.append(tx)
                self._save()
                return True, "External allocation claim accepted."
            if tx.amount <= 0:
                return False, "Amount must be positive."
            if tx.sender == tx.recipient:
                return False, "Sender and recipient must differ."
            if tx.sender in self.spent_one_time_addresses:
                return False, "Lamport address already spent. Rotate to a new address."
            if address_from_public_key(tx.public_key, tx.algorithm) != tx.sender:
                return False, "Sender does not match the supplied public key."
            if tx.nonce != self.nonces[tx.sender]:
                return False, "Invalid nonce."
            if self.balances[tx.sender] < tx.amount:
                return False, "Insufficient balance."

            message = canonical_transaction_payload(tx.to_dict())
            if not verify_post_quantum_signature(message, tx.algorithm, tx.public_key, tx.signature):
                return False, "Signature verification failed."

            self.pending_transactions.append(tx)
            self._save()
            return True, "Transaction accepted."

    def mine_block(self, miner_address: str) -> Block:
        with self.lock:
            allowed, message = self.can_propose(miner_address, len(self.chain))
            if not allowed:
                raise ValueError(message)
            reward = Transaction(
                sender="COINBASE",
                recipient=miner_address,
                amount=self.block_reward,
                nonce=0,
                note="Block reward",
                algorithm="SYSTEM",
                public_key=[],
                signature=[],
            )
            transactions = [reward.to_dict(), *[tx.to_dict() for tx in self.pending_transactions]]
            block = self._build_block(
                index=len(self.chain),
                previous_hash=self.chain[-1].block_hash,
                proposer=miner_address,
                transactions=transactions,
            )
            self._apply_committed_block(block)
            return block

    def add_block(self, block_payload: dict[str, Any]) -> tuple[bool, str]:
        with self.lock:
            expected_index = len(self.chain)
            previous_hash = self.chain[-1].block_hash
            valid, message = self._validate_header(block_payload, expected_index, previous_hash)
            if not valid:
                return False, message

            balances = defaultdict(int, self.balances)
            nonces = defaultdict(int, self.nonces)
            spent = set(self.spent_one_time_addresses)
            valid, message = self._apply_transactions_to_state(block_payload, balances, nonces, spent)
            if not valid:
                return False, message

            self.balances = balances
            self.nonces = nonces
            self.spent_one_time_addresses = spent
            self.chain.append(Block.from_dict(block_payload))
            if self.validators and block_payload["miner"] in self.validators:
                self._record_vote(
                    Vote(
                        validator=block_payload["miner"],
                        block_hash=block_payload["block_hash"],
                        block_index=int(block_payload["index"]),
                        note="Implicit proposer vote",
                        extra={"implicit": True},
                    ),
                    allow_duplicate=True,
                )
            self._remove_included_pending(block_payload["transactions"])
            self._recompute_finality()
            self._save()
            return True, "Block accepted."

    def export_chain(self) -> list[dict[str, Any]]:
        return [block.to_dict() for block in self.chain]

    def export_pending_transactions(self) -> list[dict[str, Any]]:
        return [tx.to_dict() for tx in self.pending_transactions]

    def validate_chain(self, chain_payload: list[dict[str, Any]]) -> tuple[bool, str]:
        if not chain_payload:
            return False, "Chain payload is empty."
        if chain_payload[0] != self.expected_genesis_block.to_dict():
            return False, "Genesis block does not match local genesis configuration."

        balances, nonces, spent_addresses = self._initial_state()
        previous_hash = chain_payload[0]["block_hash"]
        for expected_index, block_dict in enumerate(chain_payload[1:], start=1):
            valid, message = self._validate_header(block_dict, expected_index, previous_hash)
            if not valid:
                return False, message
            valid, message = self._apply_transactions_to_state(block_dict, balances, nonces, spent_addresses)
            if not valid:
                return False, message
            previous_hash = block_dict["block_hash"]
        return True, "Chain is valid."

    def replace_chain(
        self,
        chain_payload: list[dict[str, Any]],
        pending_payload: list[dict[str, Any]] | None = None,
        vote_payload: dict[str, list[dict[str, Any]]] | None = None,
        finalized_height: int | None = None,
    ) -> tuple[bool, str]:
        with self.lock:
            valid, message = self.validate_chain(chain_payload)
            if not valid:
                return False, message
            if len(chain_payload) <= len(self.chain):
                return False, "Incoming chain is not longer than the current chain."

            balances, nonces, spent_addresses = self._initial_state()
            for block_dict in chain_payload[1:]:
                valid, message = self._apply_transactions_to_state(block_dict, balances, nonces, spent_addresses)
                if not valid:
                    return False, message

            self.chain = [Block.from_dict(item) for item in chain_payload]
            self.pending_transactions = []
            self.balances = balances
            self.nonces = nonces
            self.spent_one_time_addresses = spent_addresses
            self.block_votes = {}
            self._bootstrap_vote_state()
            if vote_payload:
                self.merge_vote_state(vote_payload, finalized_height)
            elif finalized_height is not None:
                self.finalized_height = min(int(finalized_height), self.finalized_height)
            self._save()
            return True, "Chain replaced."
