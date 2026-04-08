from pathlib import Path
import shutil
import unittest
import uuid

from pikocoin.config import NodeConfig
from pikocoin.crypto import canonical_transaction_payload, generate_lamport_keypair, sign_message
from pikocoin.evm import (
    address_from_private_key_hex,
    build_claim_message,
    keccak256,
    sign_personal_message,
    verify_personal_signature,
)
from pikocoin.genesis import GenesisConfig, save_genesis_config
from pikocoin.ledger import Ledger


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path("D:/Pikocoin-L1-Core/.tmp-tests") / str(uuid.uuid4())
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.chain_file = self.tmpdir / "chain.json"
        self.genesis = "piko1genesisreserve000000000000000000000000"
        save_genesis_config(
            self.tmpdir / "genesis.json",
            GenesisConfig(
                chain_id="pikocoin-test-suite",
                network_name="Pikocoin Test Suite",
                token_name="Pikocoin",
                token_symbol="PIKO",
                token_decimals=0,
                icon_path="assets/pikocoin-icon.png",
                description="Isolated unit test genesis.",
                genesis_time=0.0,
                block_reward=10,
                difficulty_prefix="00",
                balances={self.genesis: 10_000_000},
                validators=[],
                allocations=[
                    {
                        "label": "Test Faucet",
                        "address": self.genesis,
                        "amount": 10_000_000,
                        "note": "Unit test faucet supply.",
                    }
                ],
            ),
        )
        self.config = NodeConfig(
            chain_file=self.chain_file,
            peers_file=self.tmpdir / "peers.json",
            genesis_file=self.tmpdir / "genesis.json",
            mining_difficulty_prefix="00",
            block_reward=10,
        )
        self.ledger = Ledger(self.config)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_genesis_state(self) -> None:
        self.assertEqual(self.ledger.get_balance(self.genesis), 10_000_000)
        self.assertEqual(self.ledger.get_status()["height"], 0)

    def test_metadata_snapshot(self) -> None:
        metadata = self.ledger.get_metadata()
        self.assertEqual(metadata["token_symbol"], "PIKO")
        self.assertEqual(metadata["total_supply"], 10_000_000)
        self.assertEqual(metadata["allocations"][0]["address"], self.genesis)

    def test_keccak_and_signature_roundtrip(self) -> None:
        self.assertEqual(
            keccak256(b"").hex(),
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
        )
        private_key = "0x1"
        address = address_from_private_key_hex(private_key)
        message = "Pikocoin signature roundtrip"
        signature = sign_personal_message(private_key, message)
        self.assertTrue(verify_personal_signature(address, message, signature))

    def test_accept_transaction_and_mine(self) -> None:
        sender = generate_lamport_keypair()
        recipient = generate_lamport_keypair()
        self.ledger.balances[sender.address] = 500
        tx = self.ledger.build_transaction(
            sender=sender.address,
            recipient=recipient.address,
            amount=125,
            nonce=0,
            public_key=sender.public_key,
            signature=[],
            note="seed transfer",
        )
        tx.signature = sign_message(canonical_transaction_payload(tx.to_dict()), sender.private_key)
        accepted, message = self.ledger.add_transaction(tx)
        self.assertTrue(accepted, message)

        block = self.ledger.mine_block(miner_address=recipient.address)
        self.assertEqual(block.index, 1)
        self.assertEqual(self.ledger.get_balance(sender.address), 375)
        self.assertEqual(self.ledger.get_balance(recipient.address), 135)
        self.assertEqual(self.ledger.get_next_nonce(sender.address), 1)

    def test_reject_reuse_of_one_time_address(self) -> None:
        sender = generate_lamport_keypair()
        recipient = generate_lamport_keypair()
        self.ledger.balances[sender.address] = 500

        first_tx = self.ledger.build_transaction(
            sender=sender.address,
            recipient=recipient.address,
            amount=100,
            nonce=0,
            public_key=sender.public_key,
            signature=[],
        )
        first_tx.signature = sign_message(canonical_transaction_payload(first_tx.to_dict()), sender.private_key)
        accepted, _ = self.ledger.add_transaction(first_tx)
        self.assertTrue(accepted)
        self.ledger.mine_block(miner_address=recipient.address)

        second_tx = self.ledger.build_transaction(
            sender=sender.address,
            recipient=recipient.address,
            amount=100,
            nonce=1,
            public_key=sender.public_key,
            signature=[],
        )
        second_tx.signature = sign_message(canonical_transaction_payload(second_tx.to_dict()), sender.private_key)
        accepted, message = self.ledger.add_transaction(second_tx)
        self.assertFalse(accepted)
        self.assertIn("Rotate", message)

    def test_replace_chain_with_longer_valid_chain(self) -> None:
        miner = generate_lamport_keypair()
        self.ledger.mine_block(miner_address=miner.address)

        replacement_config = NodeConfig(
            chain_file=self.tmpdir / "other-chain.json",
            peers_file=self.tmpdir / "other-peers.json",
            genesis_file=self.tmpdir / "genesis.json",
            mining_difficulty_prefix="00",
            block_reward=10,
        )
        replacement = Ledger(replacement_config)
        replacement.mine_block(miner_address=miner.address)
        replacement_miner_two = generate_lamport_keypair()
        replacement.mine_block(miner_address=replacement_miner_two.address)

        updated, message = self.ledger.replace_chain(replacement.export_chain(), replacement.export_pending_transactions())
        self.assertTrue(updated, message)
        self.assertEqual(self.ledger.get_status()["height"], 2)

    def test_validator_rotation_and_block_acceptance(self) -> None:
        validator_one = generate_lamport_keypair()
        validator_two = generate_lamport_keypair()
        genesis = GenesisConfig(
            chain_id="pikocoin-validator-net",
            genesis_time=12345.0,
            block_reward=7,
            difficulty_prefix="00",
            balances={
                validator_one.address: 1000,
                validator_two.address: 1000,
            },
            validators=[validator_one.address, validator_two.address],
        )
        genesis_path = self.tmpdir / "validator-genesis.json"
        save_genesis_config(genesis_path, genesis)

        leader = Ledger(
            NodeConfig(
                chain_file=self.tmpdir / "leader-chain.json",
                peers_file=self.tmpdir / "leader-peers.json",
                genesis_file=genesis_path,
                mining_difficulty_prefix="00",
            )
        )
        follower = Ledger(
            NodeConfig(
                chain_file=self.tmpdir / "follower-chain.json",
                peers_file=self.tmpdir / "follower-peers.json",
                genesis_file=genesis_path,
                mining_difficulty_prefix="00",
            )
        )

        self.assertEqual(leader.expected_proposer(1), validator_one.address)
        with self.assertRaises(ValueError):
            leader.mine_block(validator_two.address)

        block_one = leader.mine_block(validator_one.address)
        accepted, message = follower.add_block(block_one.to_dict())
        self.assertTrue(accepted, message)
        self.assertEqual(follower.get_status()["height"], 1)
        self.assertEqual(follower.expected_proposer(2), validator_two.address)
        self.assertEqual(follower.get_block_status(1)["vote_count"], 1)
        self.assertFalse(follower.get_block_status(1)["finalized"])

    def test_validator_votes_finalize_block(self) -> None:
        validators = [generate_lamport_keypair() for _ in range(4)]
        genesis = GenesisConfig(
            chain_id="pikocoin-finality-net",
            network_name="Pikocoin Finality Net",
            token_name="Pikocoin",
            token_symbol="PIKO",
            token_decimals=0,
            icon_path="assets/pikocoin-icon.png",
            description="Validator finality test.",
            genesis_time=22222.0,
            block_reward=11,
            difficulty_prefix="00",
            balances={wallet.address: 1000 for wallet in validators},
            validators=[wallet.address for wallet in validators],
            allocations=[
                {
                    "label": "Validator Bootstrap",
                    "address": wallet.address,
                    "amount": 1000,
                    "note": "Validator balance for tests.",
                }
                for wallet in validators
            ],
        )
        genesis_path = self.tmpdir / "finality-genesis.json"
        save_genesis_config(genesis_path, genesis)
        ledger = Ledger(
            NodeConfig(
                chain_file=self.tmpdir / "finality-chain.json",
                peers_file=self.tmpdir / "finality-peers.json",
                genesis_file=genesis_path,
                mining_difficulty_prefix="00",
                block_reward=11,
            )
        )

        block = ledger.mine_block(validators[0].address)
        self.assertEqual(ledger.vote_threshold(), 3)
        self.assertEqual(ledger.get_block_status(block.index)["vote_count"], 1)
        self.assertFalse(ledger.get_block_status(block.index)["finalized"])

        vote_two = ledger.build_vote(validators[1].address, block.block_hash, block.index, note="Validator two vote")
        accepted, message = ledger.add_vote(vote_two)
        self.assertTrue(accepted, message)
        self.assertFalse(ledger.get_block_status(block.index)["finalized"])

        vote_three = ledger.build_vote(validators[2].address, block.block_hash, block.index, note="Validator three vote")
        accepted, message = ledger.add_vote(vote_three)
        self.assertTrue(accepted, message)
        self.assertTrue(ledger.get_block_status(block.index)["finalized"])
        self.assertEqual(ledger.finalized_height, 1)

        duplicate_vote = ledger.build_vote(validators[2].address, block.block_hash, block.index, note="Duplicate")
        accepted, message = ledger.add_vote(duplicate_vote)
        self.assertFalse(accepted)
        self.assertIn("already voted", message)

    def test_merge_vote_state_updates_finality_without_chain_replacement(self) -> None:
        validators = [generate_lamport_keypair() for _ in range(4)]
        genesis = GenesisConfig(
            chain_id="pikocoin-vote-sync-net",
            network_name="Pikocoin Vote Sync Net",
            token_name="Pikocoin",
            token_symbol="PIKO",
            token_decimals=0,
            icon_path="assets/pikocoin-icon.png",
            description="Vote sync regression test.",
            genesis_time=33333.0,
            block_reward=13,
            difficulty_prefix="00",
            balances={wallet.address: 1000 for wallet in validators},
            validators=[wallet.address for wallet in validators],
            allocations=[
                {
                    "label": "Validator Bootstrap",
                    "address": wallet.address,
                    "amount": 1000,
                    "note": "Validator balance for tests.",
                }
                for wallet in validators
            ],
        )
        genesis_path = self.tmpdir / "vote-sync-genesis.json"
        save_genesis_config(genesis_path, genesis)
        leader = Ledger(
            NodeConfig(
                chain_file=self.tmpdir / "vote-sync-leader-chain.json",
                peers_file=self.tmpdir / "vote-sync-leader-peers.json",
                genesis_file=genesis_path,
                mining_difficulty_prefix="00",
                block_reward=13,
            )
        )
        follower = Ledger(
            NodeConfig(
                chain_file=self.tmpdir / "vote-sync-follower-chain.json",
                peers_file=self.tmpdir / "vote-sync-follower-peers.json",
                genesis_file=genesis_path,
                mining_difficulty_prefix="00",
                block_reward=13,
            )
        )

        block = leader.mine_block(validators[0].address)
        follower.add_block(block.to_dict())
        leader.add_vote(leader.build_vote(validators[1].address, block.block_hash, block.index))
        leader.add_vote(leader.build_vote(validators[2].address, block.block_hash, block.index))

        self.assertFalse(follower.get_block_status(block.index)["finalized"])
        updated, message = follower.merge_vote_state(leader.export_vote_state()["block_votes"], leader.finalized_height)
        self.assertTrue(updated, message)
        self.assertTrue(follower.get_block_status(block.index)["finalized"])
        self.assertEqual(follower.finalized_height, 1)

    def test_external_claim_flow(self) -> None:
        private_key = "0x1"
        external_address = address_from_private_key_hex(private_key)
        recipient = generate_lamport_keypair()
        claim_genesis = GenesisConfig(
            chain_id="pikocoin-claim-net",
            network_name="Pikocoin Claim Net",
            token_name="Pikocoin",
            token_symbol="PIKO",
            token_decimals=0,
            icon_path="assets/pikocoin-icon.png",
            description="Claim flow regression test.",
            genesis_time=1000.0,
            block_reward=9,
            difficulty_prefix="00",
            balances={external_address: 500},
            validators=[],
            allocations=[
                {
                    "label": "Founder Treasury",
                    "address": external_address,
                    "amount": 500,
                    "note": "External claim test allocation.",
                }
            ],
        )
        claim_genesis_path = self.tmpdir / "claim-genesis.json"
        save_genesis_config(claim_genesis_path, claim_genesis)
        claim_ledger = Ledger(
            NodeConfig(
                chain_file=self.tmpdir / "claim-chain.json",
                peers_file=self.tmpdir / "claim-peers.json",
                genesis_file=claim_genesis_path,
                mining_difficulty_prefix="00",
                block_reward=9,
            )
        )

        claim_details = claim_ledger.get_claim_message(external_address, recipient.address)
        signature = sign_personal_message(private_key, claim_details["message"])
        claim_tx = claim_ledger.build_transaction(
            sender=external_address,
            recipient=recipient.address,
            amount=500,
            nonce=0,
            public_key=[],
            signature=[],
            note="External allocation claim",
            algorithm="EVM_PERSONAL_CLAIM",
            extra={"evm_signature": signature},
        )
        accepted, message = claim_ledger.add_transaction(claim_tx)
        self.assertTrue(accepted, message)

        miner = generate_lamport_keypair()
        claim_ledger.mine_block(miner.address)
        self.assertEqual(claim_ledger.get_balance(external_address), 0)
        self.assertEqual(claim_ledger.get_balance(recipient.address), 500)
        self.assertEqual(claim_ledger.get_next_nonce(external_address), 1)


if __name__ == "__main__":
    unittest.main()
