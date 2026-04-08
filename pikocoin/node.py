"""JSON HTTP API for a local Pikocoin prototype node."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import json
from urllib import error, request

from .config import NodeConfig
from .crypto import canonical_transaction_payload, generate_lamport_keypair, sign_message
from .ledger import Ledger


class NodeRequestHandler(BaseHTTPRequestHandler):
    ledger: Ledger
    config: NodeConfig

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _binary_response(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _base_url(self) -> str:
        host = self.headers.get("Host", f"{self.config.host}:{self.config.port}")
        return f"http://{host}"

    def _resolve_icon_path(self) -> Path:
        icon_path = Path(self.ledger.genesis.icon_path)
        if icon_path.is_absolute():
            return icon_path
        repo_root = Path(__file__).resolve().parents[1]
        repo_candidate = repo_root / icon_path
        if repo_candidate.exists():
            return repo_candidate
        return (self.config.genesis_file.parent / icon_path).resolve()

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        return json.loads(raw_body.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.rstrip("/")
        if path == "":
            return self._json_response(HTTPStatus.OK, {"service": "pikocoin-node", "status": self.ledger.get_status()})
        if path == "/status":
            return self._json_response(HTTPStatus.OK, self.ledger.get_status())
        if path == "/metadata":
            return self._json_response(HTTPStatus.OK, self.ledger.get_metadata(self._base_url()))
        if path == "/icon":
            icon_path = self._resolve_icon_path()
            if not icon_path.exists():
                return self._json_response(HTTPStatus.NOT_FOUND, {"error": "Icon file not found."})
            content_type = "image/png" if icon_path.suffix.lower() == ".png" else "application/octet-stream"
            return self._binary_response(HTTPStatus.OK, icon_path.read_bytes(), content_type)
        if path.startswith("/claims/status/"):
            external_address = path.split("/", 3)[3]
            try:
                status = self.ledger.get_claim_status(external_address)
            except ValueError as exc:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return self._json_response(HTTPStatus.OK, status)
        if path == "/consensus/status":
            return self._json_response(
                HTTPStatus.OK,
                {
                    "consensus_mode": self.ledger.consensus_mode,
                    "validators": self.ledger.list_validators(),
                    "next_proposer": self.ledger.expected_proposer(len(self.ledger.chain)),
                    "height": self.ledger.get_status()["height"],
                    "vote_threshold": self.ledger.vote_threshold(),
                    "finalized_height": self.ledger.finalized_height,
                },
            )
        if path == "/chain":
            return self._json_response(
                HTTPStatus.OK,
                {
                    "chain": self.ledger.export_chain(),
                    "pending_transactions": self.ledger.export_pending_transactions(),
                    "block_votes": self.ledger.export_vote_state()["block_votes"],
                    "finalized_height": self.ledger.finalized_height,
                },
            )
        if path.startswith("/blocks/status/"):
            block_ref = path.split("/", 3)[3]
            try:
                status = self.ledger.get_block_status(block_ref)
            except ValueError as exc:
                return self._json_response(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return self._json_response(HTTPStatus.OK, status)
        if path == "/peers":
            return self._json_response(HTTPStatus.OK, {"peers": self.ledger.list_peers()})
        if path == "/validators":
            return self._json_response(HTTPStatus.OK, {"validators": self.ledger.list_validators()})
        if path.startswith("/balance/"):
            address = path.split("/", 2)[2]
            return self._json_response(
                HTTPStatus.OK,
                {
                    "address": address,
                    "balance": self.ledger.get_balance(address),
                    "next_nonce": self.ledger.get_next_nonce(address),
                },
            )
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "Route not found."})

    def do_POST(self) -> None:
        path = self.path.rstrip("/")
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body."})

        if path == "/wallet/new":
            keypair = generate_lamport_keypair()
            return self._json_response(
                HTTPStatus.CREATED,
                {
                    "address": keypair.address,
                    "algorithm": keypair.algorithm,
                    "public_key": keypair.public_key,
                    "private_key": keypair.private_key,
                    "warning": "Lamport keys are one-time only. Rotate to a new address after each spend.",
                },
            )

        if path == "/tx/send":
            try:
                sender = payload["sender"]
                recipient = payload["recipient"]
                amount = int(payload["amount"])
                note = payload.get("note", "")
                public_key = payload["public_key"]
                private_key = payload["private_key"]
                nonce = int(payload.get("nonce", self.ledger.get_next_nonce(sender)))
            except (KeyError, TypeError, ValueError):
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "Missing or invalid transaction fields."})

            tx = self.ledger.build_transaction(
                sender=sender,
                recipient=recipient,
                amount=amount,
                nonce=nonce,
                public_key=public_key,
                signature=[],
                note=note,
            )
            tx.signature = sign_message(canonical_transaction_payload(tx.to_dict()), private_key)
            accepted, message = self.ledger.add_transaction(tx)
            status = HTTPStatus.ACCEPTED if accepted else HTTPStatus.BAD_REQUEST
            if accepted:
                broadcast_transaction(self.ledger.list_peers(), tx.to_dict())
            return self._json_response(status, {"accepted": accepted, "message": message, "transaction": tx.to_dict()})

        if path == "/tx/submit":
            try:
                from .models import Transaction

                tx = Transaction.from_dict(payload)
            except TypeError:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "Malformed transaction payload."})

            accepted, message = self.ledger.add_transaction(tx)
            status = HTTPStatus.ACCEPTED if accepted else HTTPStatus.BAD_REQUEST
            return self._json_response(status, {"accepted": accepted, "message": message})

        if path == "/blocks/submit":
            accepted, message = self.ledger.add_block(payload)
            status = HTTPStatus.ACCEPTED if accepted else HTTPStatus.BAD_REQUEST
            return self._json_response(status, {"accepted": accepted, "message": message})

        if path == "/peers/register":
            peer = payload.get("peer", "")
            accepted, message = self.ledger.add_peer(peer)
            status = HTTPStatus.CREATED if accepted else HTTPStatus.BAD_REQUEST
            return self._json_response(status, {"accepted": accepted, "message": message, "peers": self.ledger.list_peers()})

        if path == "/sync":
            result = sync_from_peers(self.ledger)
            status = HTTPStatus.OK if result["updated"] else HTTPStatus.ACCEPTED
            return self._json_response(status, result)

        if path == "/consensus/vote":
            validator = payload.get("validator", "")
            block_hash = payload.get("block_hash", "")
            try:
                block_index = int(payload.get("block_index"))
            except (TypeError, ValueError):
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "block_index must be provided as an integer."})
            vote = self.ledger.build_vote(
                validator=validator,
                block_hash=block_hash,
                block_index=block_index,
                note=str(payload.get("note", "")),
                extra={"auth_mode": "genesis_identity"},
            )
            accepted, message = self.ledger.add_vote(vote)
            status = HTTPStatus.ACCEPTED if accepted else HTTPStatus.BAD_REQUEST
            if accepted:
                broadcast_vote(self.ledger.list_peers(), vote.to_dict())
            return self._json_response(
                status,
                {
                    "accepted": accepted,
                    "message": message,
                    "vote": vote.to_dict(),
                    "finalized_height": self.ledger.finalized_height,
                },
            )

        if path == "/claims/message":
            external_address = payload.get("external_address", "")
            recipient = payload.get("recipient", "")
            try:
                response = self.ledger.get_claim_message(external_address, recipient)
            except ValueError as exc:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return self._json_response(HTTPStatus.OK, response)

        if path == "/claims/external/claim":
            external_address = payload.get("external_address", "")
            recipient = payload.get("recipient", "")
            signature_hex = payload.get("signature", "")
            try:
                claim_details = self.ledger.get_claim_message(external_address, recipient)
                tx = self.ledger.build_transaction(
                    sender=claim_details["external_address"],
                    recipient=claim_details["recipient"],
                    amount=int(claim_details["amount"]),
                    nonce=int(claim_details["claim_status"]["claim_nonce"]),
                    public_key=[],
                    signature=[],
                    note="External allocation claim",
                    algorithm="EVM_PERSONAL_CLAIM",
                    extra={"evm_signature": signature_hex},
                )
            except ValueError as exc:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

            accepted, message = self.ledger.add_transaction(tx)
            status = HTTPStatus.ACCEPTED if accepted else HTTPStatus.BAD_REQUEST
            if accepted:
                broadcast_transaction(self.ledger.list_peers(), tx.to_dict())
            return self._json_response(
                status,
                {
                    "accepted": accepted,
                    "message": message,
                    "transaction": tx.to_dict(),
                },
            )

        if path == "/mine" or path == "/consensus/propose":
            miner = payload.get("miner")
            if not miner:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "Miner address is required."})
            try:
                block = self.ledger.mine_block(miner)
            except ValueError as exc:
                return self._json_response(HTTPStatus.CONFLICT, {"accepted": False, "message": str(exc)})
            broadcast_block(self.ledger.list_peers(), block.to_dict())
            return self._json_response(
                HTTPStatus.OK,
                {
                    "message": "Block proposed.",
                    "block": block.to_dict(),
                    "next_proposer": self.ledger.expected_proposer(len(self.ledger.chain)),
                },
            )

        self._json_response(HTTPStatus.NOT_FOUND, {"error": "Route not found."})

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_node(config: NodeConfig | None = None) -> None:
    node_config = config or NodeConfig.from_env()
    ledger = Ledger(node_config)
    NodeRequestHandler.ledger = ledger
    NodeRequestHandler.config = node_config
    server = ThreadingHTTPServer((node_config.host, node_config.port), NodeRequestHandler)
    print(f"Pikocoin node listening on http://{node_config.host}:{node_config.port}")
    print(f"Chain file: {node_config.chain_file}")
    server.serve_forever()


def _fetch_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url=url, data=body, method=method, headers=headers)
    with request.urlopen(req, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def broadcast_transaction(peers: list[str], transaction: dict[str, Any]) -> None:
    for peer in peers:
        try:
            _fetch_json(f"{peer}/tx/submit", method="POST", payload=transaction)
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            continue


def broadcast_block(peers: list[str], block: dict[str, Any]) -> None:
    for peer in peers:
        try:
            _fetch_json(f"{peer}/blocks/submit", method="POST", payload=block)
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            continue


def broadcast_vote(peers: list[str], vote: dict[str, Any]) -> None:
    for peer in peers:
        try:
            _fetch_json(f"{peer}/consensus/vote", method="POST", payload=vote)
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            continue


def sync_from_peers(ledger: Ledger) -> dict[str, Any]:
    best_chain = None
    best_pending = None
    best_votes = None
    best_finalized_height = None
    source_peer = None
    current_height = ledger.get_status()["height"]
    current_finalized_height = ledger.finalized_height
    vote_sync_peers: list[str] = []
    vote_sync_payloads: list[tuple[dict[str, Any], int]] = []
    for peer in ledger.list_peers():
        try:
            response = _fetch_json(f"{peer}/chain")
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        candidate_chain = response.get("chain", [])
        candidate_pending = response.get("pending_transactions", [])
        candidate_votes = response.get("block_votes", {})
        candidate_finalized_height = response.get("finalized_height", 0)
        if len(candidate_chain) - 1 > current_height:
            valid, _ = ledger.validate_chain(candidate_chain)
            if valid:
                best_chain = candidate_chain
                best_pending = candidate_pending
                best_votes = candidate_votes
                best_finalized_height = candidate_finalized_height
                source_peer = peer
                current_height = len(candidate_chain) - 1
        elif len(candidate_chain) - 1 == current_height and candidate_finalized_height > current_finalized_height:
            valid, _ = ledger.validate_chain(candidate_chain)
            if valid:
                vote_sync_peers.append(peer)
                vote_sync_payloads.append((candidate_votes, candidate_finalized_height))

    if best_chain is not None:
        updated, message = ledger.replace_chain(best_chain, best_pending, best_votes, best_finalized_height)
        return {
            "updated": updated,
            "message": message,
            "source_peer": source_peer,
            "height": ledger.get_status()["height"],
            "finalized_height": ledger.finalized_height,
        }

    merged = False
    merged_from = []
    for peer, (vote_payload, peer_finalized_height) in zip(vote_sync_peers, vote_sync_payloads):
        updated, _ = ledger.merge_vote_state(vote_payload, peer_finalized_height)
        if updated:
            merged = True
            merged_from.append(peer)

    if merged:
        return {
            "updated": True,
            "message": "Merged validator vote state from peers.",
            "source_peer": ", ".join(merged_from),
            "height": ledger.get_status()["height"],
            "finalized_height": ledger.finalized_height,
        }

    return {"updated": False, "message": "No longer valid chain or vote state found among peers."}
