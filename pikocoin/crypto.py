"""Hash-based signature primitives and upgrade hooks for future crypto."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_bytes
from typing import Iterable
import json


HASH_SIZE = 32
LAMPORT_BITS = 256


def _hash_bytes(value: bytes) -> bytes:
    return sha256(value).digest()


def _hash_hex(value: bytes) -> str:
    return sha256(value).hexdigest()


def _canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(slots=True)
class LamportKeypair:
    public_key: list[list[str]]
    private_key: list[list[str]]
    address: str
    algorithm: str = "LAMPORT_SHA256"


def generate_lamport_keypair() -> LamportKeypair:
    private_key: list[list[str]] = []
    public_key: list[list[str]] = []
    for _ in range(LAMPORT_BITS):
        zero_secret = token_bytes(HASH_SIZE)
        one_secret = token_bytes(HASH_SIZE)
        private_key.append([zero_secret.hex(), one_secret.hex()])
        public_key.append([_hash_hex(zero_secret), _hash_hex(one_secret)])

    address_material = _canonical_json(
        {
            "algorithm": "LAMPORT_SHA256",
            "public_key": public_key,
        }
    )
    address = f"piko1{sha256(address_material).hexdigest()[:40]}"
    return LamportKeypair(public_key=public_key, private_key=private_key, address=address)


def _message_digest(message: bytes) -> bytes:
    return sha256(message).digest()


def sign_message(message: bytes, private_key: list[list[str]]) -> list[str]:
    digest = _message_digest(message)
    bits = "".join(f"{byte:08b}" for byte in digest)
    return [private_key[index][int(bit)] for index, bit in enumerate(bits)]


def verify_signature(message: bytes, public_key: list[list[str]], signature: Iterable[str]) -> bool:
    digest = _message_digest(message)
    bits = "".join(f"{byte:08b}" for byte in digest)
    signature_list = list(signature)
    if len(signature_list) != LAMPORT_BITS or len(public_key) != LAMPORT_BITS:
        return False

    for index, bit in enumerate(bits):
        revealed_secret = bytes.fromhex(signature_list[index])
        if _hash_hex(revealed_secret) != public_key[index][int(bit)]:
            return False
    return True


def address_from_public_key(public_key: list[list[str]], algorithm: str = "LAMPORT_SHA256") -> str:
    payload = _canonical_json({"algorithm": algorithm, "public_key": public_key})
    return f"piko1{sha256(payload).hexdigest()[:40]}"


def canonical_transaction_payload(tx_dict: dict) -> bytes:
    payload = {
        "amount": tx_dict["amount"],
        "nonce": tx_dict["nonce"],
        "note": tx_dict.get("note", ""),
        "recipient": tx_dict["recipient"],
        "sender": tx_dict["sender"],
        "timestamp": tx_dict["timestamp"],
    }
    return _canonical_json(payload)


def block_hash(block_dict: dict) -> str:
    return sha256(_canonical_json(block_dict)).hexdigest()


def verify_post_quantum_signature(message: bytes, algorithm: str, public_key: list[list[str]], signature: list[str]) -> bool:
    if algorithm == "LAMPORT_SHA256":
        return verify_signature(message, public_key, signature)
    return False
