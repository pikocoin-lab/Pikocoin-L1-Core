import { CHAIN_OBJECT_NAME, DEFAULT_GENESIS, ICON_URL, ZERO_HASH } from "./api-constants.mjs";
import { buildClaimMessage, normalizeEvmAddress, verifyPersonalSignature } from "./api-evm.mjs";
import {
  addressFromPublicKey,
  blockHash,
  canonicalTransactionPayloadBytes,
  merkleRoot,
  txDigest,
  verifyLamportSignature,
} from "./api-lamport.mjs";
import {
  HttpError,
  asNonNegativeInteger,
  asPositiveInteger,
  cloneJson,
  roundToSix,
} from "./api-utils.mjs";

function buildBlock({ index, previousHash, proposer, transactions, timestamp, difficultyPrefix }) {
  const blockTimestamp = roundToSix(timestamp ?? Date.now() / 1000);
  const merkleRootValue = merkleRoot(transactions);
  let nonce = 0;
  while (true) {
    const candidate = {
      index,
      timestamp: blockTimestamp,
      previous_hash: previousHash,
      nonce,
      miner: proposer,
      transactions,
      merkle_root: merkleRootValue,
      difficulty_prefix: difficultyPrefix,
      block_hash: "",
    };
    const candidateHash = blockHash(candidate);
    if (candidateHash.startsWith(difficultyPrefix)) {
      return { ...candidate, block_hash: candidateHash };
    }
    nonce += 1;
  }
}

export function createInitialState(genesisInput = DEFAULT_GENESIS) {
  const genesis = cloneJson(genesisInput);
  const genesisBlock = buildBlock({
    index: 0,
    previousHash: ZERO_HASH,
    proposer: "genesis",
    transactions: [],
    timestamp: genesis.genesis_time,
    difficultyPrefix: genesis.difficulty_prefix,
  });
  return {
    genesis,
    chain: [genesisBlock],
    pending_transactions: [],
    balances: { ...genesis.balances },
    nonces: {},
    spent_one_time_addresses: [],
    block_votes: {},
    finalized_height: 0,
    peers: [],
  };
}

export class PikocoinChainStateMachine {
  constructor(stateInput = null, genesisInput = DEFAULT_GENESIS) {
    this.state = stateInput ? cloneJson(stateInput) : createInitialState(genesisInput);
    this.genesis = this.state.genesis || cloneJson(genesisInput);
    if (!Array.isArray(this.state.chain) || this.state.chain.length === 0) {
      this.state = createInitialState(this.genesis);
      this.genesis = this.state.genesis;
    }
  }

  exportState() {
    return cloneJson(this.state);
  }

  validators() {
    return Array.isArray(this.genesis.validators) ? [...this.genesis.validators] : [];
  }

  consensusMode() {
    return this.validators().length ? "round_robin_validators" : "open-mining";
  }

  latestBlock() {
    return this.state.chain[this.state.chain.length - 1];
  }

  blockReward() {
    return Number(this.genesis.block_reward);
  }

  difficultyPrefix() {
    return this.genesis.difficulty_prefix;
  }

  voteThreshold() {
    const validators = this.validators();
    if (!validators.length) {
      return 0;
    }
    return Math.floor((2 * validators.length) / 3) + 1;
  }

  expectedProposer(blockIndex) {
    const validators = this.validators();
    if (!validators.length) {
      return null;
    }
    if (blockIndex <= 0) {
      return "genesis";
    }
    return validators[(blockIndex - 1) % validators.length];
  }

  canPropose(address, blockIndex = this.state.chain.length) {
    const expected = this.expectedProposer(blockIndex);
    if (expected === null) {
      return [true, "Open mining mode."];
    }
    if (address !== expected) {
      return [false, `Validator ${address} is not the selected proposer for block ${blockIndex}. Expected ${expected}.`];
    }
    return [true, "Validator is the selected proposer."];
  }

  recomputeFinality() {
    const validators = this.validators();
    if (!validators.length) {
      this.state.finalized_height = this.state.chain.length - 1;
      return;
    }
    const threshold = this.voteThreshold();
    let finalizedHeight = 0;
    for (const block of this.state.chain.slice(1)) {
      if (this.voteCount(block.block_hash) >= threshold) {
        finalizedHeight = block.index;
      } else {
        break;
      }
    }
    this.state.finalized_height = finalizedHeight;
  }

  recordVote(vote, allowDuplicate = false) {
    const votesForBlock = this.state.block_votes[vote.block_hash] || [];
    for (const existingVote of votesForBlock) {
      if (existingVote.validator === vote.validator) {
        if (allowDuplicate) {
          return [true, "Vote already tracked."];
        }
        return [false, "Validator already voted for this block."];
      }
    }
    for (const votes of Object.values(this.state.block_votes)) {
      for (const existingVote of votes) {
        if (existingVote.validator === vote.validator && Number(existingVote.block_index) === Number(vote.block_index)) {
          if (allowDuplicate && existingVote.block_hash === vote.block_hash) {
            return [true, "Vote already tracked."];
          }
          return [false, "Validator already cast a vote for this block height."];
        }
      }
    }
    this.state.block_votes[vote.block_hash] = [...votesForBlock, vote];
    return [true, "Vote recorded."];
  }

  voteCount(blockHashValue) {
    const votes = this.state.block_votes[blockHashValue] || [];
    return new Set(votes.map((vote) => vote.validator)).size;
  }

  getStatus() {
    const latest = this.latestBlock();
    return {
      chain_id: this.genesis.chain_id,
      height: this.state.chain.length - 1,
      latest_hash: latest.block_hash,
      pending_transactions: this.state.pending_transactions.length,
      difficulty_prefix: this.difficultyPrefix(),
      peer_count: this.state.peers.length,
      validator_count: this.validators().length,
      consensus_mode: this.consensusMode(),
      next_proposer: this.expectedProposer(this.state.chain.length),
      vote_threshold: this.voteThreshold(),
      finalized_height: this.state.finalized_height,
    };
  }

  getMetadata(baseUrl = "") {
    const metadata = {
      chain_id: this.genesis.chain_id,
      network_name: this.genesis.network_name,
      token_name: this.genesis.token_name,
      token_symbol: this.genesis.token_symbol,
      token_decimals: Number(this.genesis.token_decimals),
      description: this.genesis.description,
      icon_path: this.genesis.icon_path,
      icon_url: ICON_URL,
      total_supply: Object.values(this.genesis.balances).reduce((sum, value) => sum + Number(value), 0),
      allocations: cloneJson(this.genesis.allocations || []),
      consensus_mode: this.consensusMode(),
      validator_count: this.validators().length,
      vote_threshold: this.voteThreshold(),
    };
    if (baseUrl) {
      metadata.metadata_url = `${String(baseUrl).replace(/\/$/, "")}/metadata`;
    }
    return metadata;
  }

  getConsensusStatus() {
    return {
      consensus_mode: this.consensusMode(),
      validators: this.validators(),
      next_proposer: this.expectedProposer(this.state.chain.length),
      height: this.state.chain.length - 1,
      vote_threshold: this.voteThreshold(),
      finalized_height: this.state.finalized_height,
    };
  }

  getBalance(address) {
    return {
      address,
      balance: Number(this.state.balances[address] || 0),
      next_nonce: Number(this.state.nonces[address] || 0),
    };
  }

  getClaimStatus(externalAddress) {
    const normalized = normalizeEvmAddress(externalAddress);
    const pending = this.state.pending_transactions.some(
      (tx) => tx.algorithm === "EVM_PERSONAL_CLAIM" && String(tx.sender).toLowerCase() === normalized,
    );
    const balance = Number(this.state.balances[normalized] || 0);
    const nonce = Number(this.state.nonces[normalized] || 0);
    return {
      address: normalized,
      available_balance: balance,
      claim_nonce: nonce,
      claimed: balance === 0 && nonce > 0,
      pending,
      eligible: Object.prototype.hasOwnProperty.call(this.genesis.balances, normalized),
    };
  }

  getClaimMessage(externalAddress, recipient) {
    if (!String(recipient || "").startsWith("piko1")) {
      throw new HttpError(400, "External claims must target a native piko1 address.");
    }
    const normalized = normalizeEvmAddress(externalAddress);
    const amount = Number(this.state.balances[normalized] || 0);
    return {
      external_address: normalized,
      recipient,
      amount,
      message: buildClaimMessage(this.genesis.chain_id, normalized, recipient, amount),
      claim_status: this.getClaimStatus(normalized),
    };
  }

  validateClaimTransaction(tx, balances, nonces) {
    const sender = normalizeEvmAddress(tx.sender);
    const recipient = String(tx.recipient || "");
    const amount = Number(tx.amount);
    if (!recipient.startsWith("piko1")) {
      throw new HttpError(400, "External claims must target a native piko1 address.");
    }
    if (!Object.prototype.hasOwnProperty.call(this.genesis.balances, sender)) {
      throw new HttpError(400, "External address is not part of the genesis allocation table.");
    }
    if (Number(tx.nonce) !== Number(nonces[sender] || 0)) {
      throw new HttpError(400, "Invalid claim nonce.");
    }
    if (!Number.isInteger(amount) || amount <= 0) {
      throw new HttpError(400, "Claim amount must be positive.");
    }
    if (Number(balances[sender] || 0) <= 0) {
      throw new HttpError(400, "No unclaimed allocation remains for this external address.");
    }
    if (amount !== Number(balances[sender] || 0)) {
      throw new HttpError(400, "Claim amount must equal the remaining external allocation.");
    }
    const signatureHex = String(tx.extra?.evm_signature || "").trim();
    if (!signatureHex) {
      throw new HttpError(400, "Missing EVM signature.");
    }
    const expectedMessage = buildClaimMessage(this.genesis.chain_id, sender, recipient, amount);
    if (!verifyPersonalSignature(sender, expectedMessage, signatureHex)) {
      throw new HttpError(400, "EVM claim signature verification failed.");
    }
  }

  validateNativeTransaction(tx) {
    const amount = Number(tx.amount);
    if (!Number.isInteger(amount) || amount <= 0) {
      throw new HttpError(400, "Amount must be positive.");
    }
    if (tx.sender === tx.recipient) {
      throw new HttpError(400, "Sender and recipient must differ.");
    }
    if (this.state.spent_one_time_addresses.includes(tx.sender)) {
      throw new HttpError(400, "Lamport address already spent. Rotate to a new address.");
    }
    if (this.state.pending_transactions.some((pending) => pending.sender === tx.sender)) {
      throw new HttpError(400, "A pending transaction already exists for this sender.");
    }
    if (addressFromPublicKey(tx.public_key, tx.algorithm) !== tx.sender) {
      throw new HttpError(400, "Sender does not match the supplied public key.");
    }
    if (Number(tx.nonce) !== Number(this.state.nonces[tx.sender] || 0)) {
      throw new HttpError(400, "Invalid nonce.");
    }
    if (Number(this.state.balances[tx.sender] || 0) < amount) {
      throw new HttpError(400, "Insufficient balance.");
    }
    if (!verifyLamportSignature(canonicalTransactionPayloadBytes(tx), tx.public_key, tx.signature)) {
      throw new HttpError(400, "Signature verification failed.");
    }
  }

  addTransaction(txInput) {
    const tx = cloneJson(txInput);
    tx.amount = asPositiveInteger(tx.amount, "amount");
    tx.nonce = asNonNegativeInteger(tx.nonce, "nonce");
    tx.timestamp = roundToSix(tx.timestamp ?? Date.now() / 1000);
    tx.note = String(tx.note || "");
    tx.algorithm = tx.algorithm || "LAMPORT_SHA256";
    tx.public_key = Array.isArray(tx.public_key) ? tx.public_key : [];
    tx.signature = Array.isArray(tx.signature) ? tx.signature : [];
    tx.extra = tx.extra && typeof tx.extra === "object" ? tx.extra : {};

    if (tx.algorithm === "EVM_PERSONAL_CLAIM") {
      tx.sender = normalizeEvmAddress(tx.sender);
      this.validateClaimTransaction(tx, this.state.balances, this.state.nonces);
      if (
        this.state.pending_transactions.some(
          (pending) => pending.algorithm === "EVM_PERSONAL_CLAIM" && String(pending.sender).toLowerCase() === tx.sender,
        )
      ) {
        throw new HttpError(400, "A pending claim already exists for this external address.");
      }
      this.state.pending_transactions.push(tx);
      return { accepted: true, message: "External allocation claim accepted.", transaction: tx };
    }

    this.validateNativeTransaction(tx);
    this.state.pending_transactions.push(tx);
    return { accepted: true, message: "Transaction accepted.", transaction: tx };
  }

  applyTransactionsToState(block, balances, nonces, spentAddresses) {
    const transactions = block.transactions || [];
    if (!transactions.length) {
      throw new HttpError(400, "Block must contain a coinbase transaction.");
    }

    const coinbase = transactions[0];
    if (coinbase.sender !== "COINBASE") {
      throw new HttpError(400, "First transaction must be coinbase.");
    }
    if (Number(coinbase.amount) !== this.blockReward()) {
      throw new HttpError(400, "Invalid block reward.");
    }
    if (coinbase.recipient !== block.miner) {
      throw new HttpError(400, "Coinbase recipient must match block proposer.");
    }
    balances[coinbase.recipient] = Number(balances[coinbase.recipient] || 0) + Number(coinbase.amount);

    for (const tx of transactions.slice(1)) {
      if (tx.algorithm === "EVM_PERSONAL_CLAIM") {
        this.validateClaimTransaction(tx, balances, nonces);
        balances[tx.sender] = Number(balances[tx.sender] || 0) - Number(tx.amount);
        balances[tx.recipient] = Number(balances[tx.recipient] || 0) + Number(tx.amount);
        nonces[tx.sender] = Number(nonces[tx.sender] || 0) + 1;
        continue;
      }

      if (tx.sender === "COINBASE") {
        throw new HttpError(400, "Coinbase transaction can only appear once.");
      }
      if (Number(tx.amount) <= 0) {
        throw new HttpError(400, "Transaction amount must be positive.");
      }
      if (tx.sender === tx.recipient) {
        throw new HttpError(400, "Sender and recipient must differ.");
      }
      if (spentAddresses.has(tx.sender)) {
        throw new HttpError(400, `One-time address reused in block ${block.index}: ${tx.sender}`);
      }
      if (Number(balances[tx.sender] || 0) < Number(tx.amount)) {
        throw new HttpError(400, `Insufficient balance for ${tx.sender} in block ${block.index}`);
      }
      if (Number(tx.nonce) !== Number(nonces[tx.sender] || 0)) {
        throw new HttpError(400, `Invalid nonce for ${tx.sender} in block ${block.index}`);
      }
      if (addressFromPublicKey(tx.public_key, tx.algorithm) !== tx.sender) {
        throw new HttpError(400, `Address mismatch in block ${block.index}`);
      }
      if (!verifyLamportSignature(canonicalTransactionPayloadBytes(tx), tx.public_key, tx.signature)) {
        throw new HttpError(400, `Invalid signature in block ${block.index}`);
      }

      balances[tx.sender] = Number(balances[tx.sender] || 0) - Number(tx.amount);
      balances[tx.recipient] = Number(balances[tx.recipient] || 0) + Number(tx.amount);
      nonces[tx.sender] = Number(nonces[tx.sender] || 0) + 1;
      spentAddresses.add(tx.sender);
    }
  }

  removeIncludedPending(transactions) {
    const included = new Set(transactions.slice(1).map((tx) => txDigest(tx)));
    this.state.pending_transactions = this.state.pending_transactions.filter((tx) => !included.has(txDigest(tx)));
  }

  mineBlock(minerAddress) {
    const miner = String(minerAddress || "").trim();
    if (!miner) {
      throw new HttpError(400, "Miner address is required.");
    }
    const [allowed, message] = this.canPropose(miner, this.state.chain.length);
    if (!allowed) {
      throw new HttpError(409, message);
    }

    const reward = {
      sender: "COINBASE",
      recipient: miner,
      amount: this.blockReward(),
      nonce: 0,
      timestamp: roundToSix(Date.now() / 1000),
      note: "Block reward",
      algorithm: "SYSTEM",
      public_key: [],
      signature: [],
      extra: {},
    };
    const transactions = [reward, ...this.state.pending_transactions.map((tx) => cloneJson(tx))];
    const block = buildBlock({
      index: this.state.chain.length,
      previousHash: this.latestBlock().block_hash,
      proposer: miner,
      transactions,
      timestamp: Date.now() / 1000,
      difficultyPrefix: this.difficultyPrefix(),
    });

    const balances = { ...this.state.balances };
    const nonces = { ...this.state.nonces };
    const spentAddresses = new Set(this.state.spent_one_time_addresses);
    this.applyTransactionsToState(block, balances, nonces, spentAddresses);

    this.state.balances = balances;
    this.state.nonces = nonces;
    this.state.spent_one_time_addresses = [...spentAddresses].sort();
    this.state.chain.push(block);
    if (this.validators().includes(miner)) {
      this.recordVote(
        {
          validator: miner,
          block_hash: block.block_hash,
          block_index: block.index,
          timestamp: roundToSix(Date.now() / 1000),
          note: "Implicit proposer vote",
          extra: { implicit: true },
        },
        true,
      );
    }
    this.removeIncludedPending(block.transactions);
    this.recomputeFinality();

    return {
      message: "Block proposed.",
      block,
      next_proposer: this.expectedProposer(this.state.chain.length),
    };
  }

  getBlockStatus(blockRef = "latest") {
    let block = null;
    if (blockRef === "latest") {
      block = this.latestBlock();
    } else if (/^\d+$/u.test(String(blockRef))) {
      block = this.state.chain[Number(blockRef)] || null;
    } else {
      block = this.state.chain.find((candidate) => candidate.block_hash === blockRef) || null;
    }
    if (!block) {
      throw new HttpError(404, "Block not found.");
    }
    const votes = cloneJson(this.state.block_votes[block.block_hash] || []);
    const voteCount = this.voteCount(block.block_hash);
    const threshold = this.voteThreshold();
    const finalized = block.index <= this.state.finalized_height;
    let confirmationStatus = "proposed";
    if (block.index === 0 || finalized) {
      confirmationStatus = "finalized";
    } else if (threshold === 0) {
      confirmationStatus = "confirmed";
    } else if (voteCount > 0) {
      confirmationStatus = "voting";
    }
    return {
      block_hash: block.block_hash,
      block_index: block.index,
      proposer: block.miner,
      vote_count: voteCount,
      vote_threshold: threshold,
      finalized,
      finalized_height: this.state.finalized_height,
      confirmation_status: confirmationStatus,
      votes,
    };
  }

  getChainSnapshot() {
    return {
      chain: cloneJson(this.state.chain),
      pending_transactions: cloneJson(this.state.pending_transactions),
      block_votes: cloneJson(this.state.block_votes),
      finalized_height: this.state.finalized_height,
    };
  }
}

export const workerMeta = {
  chainObjectName: CHAIN_OBJECT_NAME,
};
