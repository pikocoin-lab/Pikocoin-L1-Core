# Pikocoin Prototype Node

This repository now includes a runnable prototype blockchain node in the `pikocoin` package.

## What is included

- Post-quantum-flavored prototype wallet flow based on Lamport one-time signatures
- Account balances, nonces, mempool, proposer blocks, and persistent chain state
- Peer registry, longest-chain sync, and transaction rebroadcast over HTTP
- Shared genesis config with validator allowlist and deterministic proposer rotation
- Branded chain metadata and icon serving through `/metadata` and `/icon`
- Supermajority validator voting with finalized block tracking
- JSON HTTP node API implemented with the Python standard library
- Wallet CLI for creating wallets, sending transfers, generating genesis, peer management, and sync
- Tests for genesis state, transaction validation, one-time key reuse protection, chain replacement, validator rotation, EVM claims, and vote finality

## Quick start

```powershell
cd D:\Pikocoin-L1-Core
python -m unittest discover -s tests -v
python run_node.py
```

The node listens on `http://127.0.0.1:8080` by default.

The checked-in [`config/genesis.json`](/D:/Pikocoin-L1-Core/config/genesis.json) already includes:

- `PIKO` token branding and the checked-in icon at [`assets/pikocoin-icon.png`](/D:/Pikocoin-L1-Core/assets/pikocoin-icon.png)
- Founder and governance treasury allocated to `0x30514237625b9e4206c728ff551725b4bf9d4a85`
- A 1,000,000,000 PIKO genesis allocation plan across treasury, community, validator, liquidity, AI/privacy R&D, and operations reserves

That founder allocation is reserved to the external EVM address and can now be claimed into a native `piko1...` wallet through an Ethereum-compatible personal-sign flow.

If you want a fresh validator-specific genesis instead of the default checked-in one:

```powershell
python wallet_cli.py new-wallet --offline --out wallets\validator-1.json
python wallet_cli.py new-wallet --offline --out wallets\validator-2.json
python wallet_cli.py create-genesis --validator-wallet wallets\validator-1.json --validator-wallet wallets\validator-2.json --owner-address 0x30514237625b9e4206c728ff551725b4bf9d4a85 --out config\genesis.json
```

Run a second node:

```powershell
$env:PIKO_PORT="8081"
$env:PIKO_CHAIN_FILE="data/chain-8081.json"
$env:PIKO_PEERS_FILE="data/peers-8081.json"
$env:PIKO_GENESIS_FILE="config/genesis.json"
python run_node.py
```

## API examples

Create a wallet:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/wallet/new
```

Check node status:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8080/status
```

Read chain metadata:

```powershell
python wallet_cli.py metadata --node http://127.0.0.1:8080
```

Check the founder allocation claim status:

```powershell
python wallet_cli.py claim-status --node http://127.0.0.1:8080 --owner-address 0x30514237625b9e4206c728ff551725b4bf9d4a85
```

Create a native recipient wallet for the claim:

```powershell
python wallet_cli.py new-wallet --offline --out wallets\founder-claim.json
```

Generate the exact message your EVM wallet must sign:

```powershell
python wallet_cli.py claim-message --node http://127.0.0.1:8080 --owner-address 0x30514237625b9e4206c728ff551725b4bf9d4a85 --recipient-wallet wallets\founder-claim.json
```

After signing that message with the matching EVM wallet, submit the signature:

```powershell
python wallet_cli.py claim-evm --node http://127.0.0.1:8080 --owner-address 0x30514237625b9e4206c728ff551725b4bf9d4a85 --recipient-wallet wallets\founder-claim.json --signature 0xYOUR_SIGNATURE
```

The claim enters the mempool first. Propose or mine the next block to finalize it on-chain:

```powershell
python wallet_cli.py mine --node http://127.0.0.1:8080 --miner piko1yourmineraddress
```

Check consensus rotation:

```powershell
python wallet_cli.py consensus-status --node http://127.0.0.1:8080
```

Propose a validator block:

```powershell
python wallet_cli.py propose --node http://127.0.0.1:8080 --wallet wallets\validator-1.json
```

Inspect the latest block's finality state:

```powershell
python wallet_cli.py block-status --node http://127.0.0.1:8080
```

Cast a validator vote for the latest canonical block:

```powershell
python wallet_cli.py vote --node http://127.0.0.1:8080 --wallet wallets\validator-2.json
```

Once the configured supermajority threshold is reached, the block status moves to `finalized`.

Register a peer and sync:

```powershell
python wallet_cli.py add-peer --node http://127.0.0.1:8080 --peer http://127.0.0.1:8081
python wallet_cli.py sync --node http://127.0.0.1:8080
```

Create a wallet file:

```powershell
python wallet_cli.py new-wallet --node http://127.0.0.1:8080 --out wallets\miner.json
```

## Important limitations

This is a prototype, not a production mainnet. It does not yet provide:

- Signed validator votes, finality gadgets, or Byzantine-fault-tolerant fork choice
- Real gossip networking, mempool anti-spam, or peer reputation
- Zero-knowledge privacy proofs
- Production-grade post-quantum signatures such as ML-DSA
- Smart contracts, rollups, or bridge security
- Full direct-account EVM execution. The current bridge is a secure one-time claim into native `piko1` accounts rather than full EVM account abstraction.

Current validator voting tradeoff:

- Votes are tracked against the validator addresses declared in genesis and are sufficient for prototyping finality behavior.
- Validator vote authentication is still a placeholder identity mode, not a dedicated rotating vote-key scheme. The next hardening step is adding validator signing keys or BLS/ed25519-style vote credentials.

The current package is a clean base we can extend toward those milestones.

## Frontend and Cloudflare Pages

The repository now also includes a static frontend in [`site/`](/D:/Pikocoin-L1-Core/site/index.html) designed for Cloudflare Pages.

What it includes:

- Brand landing page using the checked-in Pikocoin icon
- Genesis tokenomics view for the current 1,000,000,000 PIKO allocation plan
- Founder claim walkthrough for `0x30514237625b9e4206c728ff551725b4bf9d4a85`
- Browser-generated Lamport wallet flow stored in local storage and exportable as JSON
- MetaMask founder-claim signing flow for the checked-in EVM treasury allocation
- Client-side signed transfer submission through `/tx/submit`
- Lightweight operator console that can mine or propose the next block from the active wallet

Suggested Cloudflare Pages build settings for this repo:

- Production branch: `main`
- Build command: leave empty
- Build output directory: `site`

Because the frontend may live on a different domain than the Python node, the node now sends permissive CORS headers for `GET`, `POST`, and `OPTIONS`.

Important browser caveat:

- The production site is served over HTTPS, so browsers will block calls to an insecure `http://` node endpoint because of mixed-content rules.
- For local development against `http://127.0.0.1:8080`, open the frontend locally or put the node behind an HTTPS endpoint such as `https://api.piko.eu.cc`.

## Cloudflare Worker API

This repository now also includes a Cloudflare Worker API implementation under [`workers/`](/D:/Pikocoin-L1-Core/workers/pikocoin-api-worker.mjs).

What it provides:

- Durable Object backed canonical chain state for the live browser console
- HTTPS endpoints compatible with the current frontend:
  - `GET /status`
  - `GET /metadata`
  - `GET /consensus/status`
  - `GET /claims/status/:external_address`
  - `GET /balance/:address`
  - `POST /claims/message`
  - `POST /claims/external/claim`
  - `POST /tx/submit`
  - `POST /mine`
- Native Lamport transfer verification
- EVM `personal_sign` founder-claim verification
- Redirected `/icon` support using the checked-in project branding

The frontend defaults to `https://api.piko.eu.cc` whenever it is opened outside `localhost`, so the public console can talk to the Worker-backed node without manual endpoint setup.
