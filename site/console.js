const founderAddress = "0x30514237625b9e4206c728ff551725b4bf9d4a85";
const walletStorageKey = "piko_native_wallet_v2";
const apiStorageKey = "piko_api_base";
const lamportBits = 256;

const state = {
  genesis: null,
  metadata: null,
  status: null,
  consensus: null,
  claim: null,
  nativeWallet: null,
  nativeBalance: null,
  evmWallet: null,
  claimMessage: "",
  activities: [],
};

const heroMetricsEl = document.getElementById("hero-metrics");
const networkStatsEl = document.getElementById("network-stats");
const allocationBarsEl = document.getElementById("allocation-bars");
const allocationListEl = document.getElementById("allocation-list");
const metadataJsonEl = document.getElementById("metadata-json");
const consensusJsonEl = document.getElementById("consensus-json");
const apiInputEl = document.getElementById("api-base");
const apiMessageEl = document.getElementById("api-message");
const metadataStateEl = document.getElementById("metadata-state");
const consensusStateEl = document.getElementById("consensus-state");
const claimGridEl = document.getElementById("claim-grid");
const claimStatusTagEl = document.getElementById("claim-status-tag");
const founderAddressEl = document.getElementById("founder-address");
const supplyInlineEl = document.getElementById("supply-inline");
const walletDetailsEl = document.getElementById("wallet-details");
const walletWarningEl = document.getElementById("wallet-warning");
const walletStatePillEl = document.getElementById("wallet-state-pill");
const evmDetailsEl = document.getElementById("evm-details");
const evmStatePillEl = document.getElementById("evm-state-pill");
const claimMessageBoxEl = document.getElementById("claim-message-box");
const operatorDetailsEl = document.getElementById("operator-details");
const blockActionNoteEl = document.getElementById("block-action-note");
const activityLogEl = document.getElementById("activity-log");
const activityCountEl = document.getElementById("activity-count");
const sendRecipientEl = document.getElementById("send-recipient");
const sendAmountEl = document.getElementById("send-amount");
const sendNoteEl = document.getElementById("send-note");
const importWalletFileEl = document.getElementById("import-wallet-file");

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function shortAddress(value) {
  if (!value || value.length < 14) {
    return value || "not connected";
  }
  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

function clampActivities() {
  if (state.activities.length > 20) {
    state.activities = state.activities.slice(0, 20);
  }
}

function logActivity(title, detail = "", tone = "info") {
  state.activities.unshift({
    title,
    detail,
    tone,
    timestamp: new Date().toLocaleTimeString(),
  });
  clampActivities();
  renderActivityLog();
}

function renderActivityLog() {
  activityCountEl.textContent = `${state.activities.length} event${state.activities.length === 1 ? "" : "s"}`;
  activityLogEl.innerHTML = state.activities
    .map(
      (item) => `
        <article class="activity-item activity-${item.tone}">
          <div class="activity-head">
            <strong>${item.title}</strong>
            <span>${item.timestamp}</span>
          </div>
          <p>${item.detail || "No extra details."}</p>
        </article>
      `,
    )
    .join("");
}

function setBusy(buttonId, busy, labelWhenBusy) {
  const button = document.getElementById(buttonId);
  if (!button) {
    return;
  }
  if (!button.dataset.defaultLabel) {
    button.dataset.defaultLabel = button.textContent;
  }
  button.disabled = busy;
  button.textContent = busy ? labelWhenBusy : button.dataset.defaultLabel;
}

function storageSet(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function storageGet(key) {
  const raw = localStorage.getItem(key);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.error(error);
    return null;
  }
}

function bytesToHex(bytes) {
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(hex) {
  const clean = String(hex).replace(/^0x/, "").trim();
  if (!clean || clean.length % 2 !== 0) {
    throw new Error("Invalid hex input.");
  }
  const bytes = new Uint8Array(clean.length / 2);
  for (let index = 0; index < clean.length; index += 2) {
    bytes[index / 2] = Number.parseInt(clean.slice(index, index + 2), 16);
  }
  return bytes;
}

function randomHex(byteLength) {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return bytesToHex(bytes);
}

function stableStringify(value) {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? JSON.stringify(value) : "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "object") {
    return `{${Object.keys(value)
      .filter((key) => value[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return "null";
}

async function sha256Bytes(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return new Uint8Array(digest);
}

async function sha256Hex(bytes) {
  return bytesToHex(await sha256Bytes(bytes));
}

function canonicalTransactionPayload(transaction) {
  return stableStringify({
    amount: Number(transaction.amount),
    nonce: Number(transaction.nonce),
    note: transaction.note || "",
    recipient: transaction.recipient,
    sender: transaction.sender,
    timestamp: transaction.timestamp,
  });
}

async function addressFromPublicKey(publicKey, algorithm = "LAMPORT_SHA256") {
  const payload = new TextEncoder().encode(stableStringify({ algorithm, public_key: publicKey }));
  const digest = await sha256Hex(payload);
  return `piko1${digest.slice(0, 40)}`;
}

async function validateWallet(wallet) {
  if (!wallet || wallet.algorithm !== "LAMPORT_SHA256") {
    throw new Error("Unsupported wallet payload.");
  }
  if (!Array.isArray(wallet.public_key) || !Array.isArray(wallet.private_key)) {
    throw new Error("Wallet is missing Lamport key material.");
  }
  if (wallet.public_key.length !== lamportBits || wallet.private_key.length !== lamportBits) {
    throw new Error("Wallet has an invalid Lamport key length.");
  }
  const derivedAddress = await addressFromPublicKey(wallet.public_key, wallet.algorithm);
  if (derivedAddress !== wallet.address) {
    throw new Error("Wallet address does not match the supplied public key.");
  }
  return wallet;
}

async function generateLamportWallet() {
  const publicKey = [];
  const privateKey = [];
  for (let index = 0; index < lamportBits; index += 1) {
    const zeroSecret = randomHex(32);
    const oneSecret = randomHex(32);
    privateKey.push([zeroSecret, oneSecret]);
    publicKey.push([await sha256Hex(hexToBytes(zeroSecret)), await sha256Hex(hexToBytes(oneSecret))]);
    if (index % 32 === 31) {
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    }
  }
  const address = await addressFromPublicKey(publicKey);
  return {
    address,
    algorithm: "LAMPORT_SHA256",
    public_key: publicKey,
    private_key: privateKey,
    warning: "Lamport keys are one-time only. Rotate to a fresh sender after every spend.",
  };
}

async function signLamportTransaction(transaction, wallet) {
  const digest = await sha256Bytes(new TextEncoder().encode(canonicalTransactionPayload(transaction)));
  const signature = [];
  let keyIndex = 0;
  for (const byte of digest) {
    for (let bit = 7; bit >= 0; bit -= 1) {
      const selector = (byte >> bit) & 1;
      signature.push(wallet.private_key[keyIndex][selector]);
      keyIndex += 1;
    }
  }
  return signature;
}

function requireApiBase() {
  const base = apiInputEl.value.trim().replace(/\/$/, "");
  if (!base) {
    throw new Error("Set a node API endpoint first.");
  }
  if (window.location.protocol === "https:" && base.startsWith("http://")) {
    throw new Error("This HTTPS page cannot call an insecure http:// node. Use an https:// API or open the page locally.");
  }
  return base;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.text();
  let payload = {};
  try {
    payload = body ? JSON.parse(body) : {};
  } catch (error) {
    console.error(error);
  }
  if (!response.ok) {
    throw new Error(payload.error || payload.message || `${response.status} ${response.statusText}`);
  }
  return payload;
}

async function fetchNodeJson(path, options = {}) {
  const base = requireApiBase();
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const body = options.body && typeof options.body !== "string" ? JSON.stringify(options.body) : options.body;
  return fetchJson(`${base}${path}`, { ...options, headers, body });
}

function renderMetricCards(items) {
  heroMetricsEl.innerHTML = items
    .map(
      (item) => `
        <article class="metric-card">
          <span class="metric-label">${item.label}</span>
          <span class="metric-value">${item.value}</span>
        </article>
      `,
    )
    .join("");
}

function renderStats(items) {
  networkStatsEl.innerHTML = items
    .map(
      (item) => `
        <article class="stat-card">
          <span class="stat-label">${item.label}</span>
          <strong class="stat-value">${item.value}</strong>
        </article>
      `,
    )
    .join("");
}

function renderAllocations(genesis) {
  const allocations = genesis.allocations || [];
  const totalSupply = allocations.reduce((sum, item) => sum + Number(item.amount || 0), 0);
  supplyInlineEl.textContent = formatNumber(totalSupply);

  allocationBarsEl.innerHTML = allocations
    .map((item) => {
      const share = totalSupply > 0 ? (Number(item.amount || 0) / totalSupply) * 100 : 0;
      return `
        <article class="allocation-strip">
          <div class="allocation-head">
            <div>
              <span class="allocation-label">${item.label}</span>
              <strong class="allocation-amount">${formatNumber(item.amount)} PIKO</strong>
            </div>
            <span class="allocation-label">${share.toFixed(1)}%</span>
          </div>
          <div class="allocation-progress"><span style="width:${share.toFixed(2)}%"></span></div>
        </article>
      `;
    })
    .join("");

  allocationListEl.innerHTML = allocations
    .map(
      (item) => `
        <article class="allocation-strip">
          <div class="allocation-head">
            <div>
              <span class="allocation-label">${item.label}</span>
              <strong class="allocation-amount mono">${item.address}</strong>
            </div>
            <span class="allocation-amount">${formatNumber(item.amount)} PIKO</span>
          </div>
          <p class="allocation-note">${item.note || "No note provided."}</p>
        </article>
      `,
    )
    .join("");
}

function normalizeClaimData(input) {
  return {
    external_address: input.address || input.external_address || founderAddress,
    amount: input.available_balance ?? input.amount ?? state.genesis?.balances?.[founderAddress] ?? 0,
    claim_nonce: input.claim_nonce ?? 0,
    claimed: Boolean(input.claimed),
    pending: Boolean(input.pending),
    eligible: input.eligible ?? true,
  };
}

function renderClaim(claim) {
  const rows = [
    ["Founder address", claim.external_address || founderAddress],
    ["Available balance", `${formatNumber(claim.amount || 0)} PIKO`],
    ["Eligible", claim.eligible ? "yes" : "no"],
    ["Pending in mempool", claim.pending ? "yes" : "no"],
    ["Already claimed", claim.claimed ? "yes" : "no"],
    ["Claim nonce", claim.claim_nonce ?? 0],
  ];
  claimGridEl.innerHTML = rows
    .map(
      ([label, value]) => `
        <div>
          <dt>${label}</dt>
          <dd class="${String(value).startsWith("0x") || String(value).startsWith("piko1") ? "mono" : ""}">${value}</dd>
        </div>
      `,
    )
    .join("");
}

function renderWalletDetails() {
  if (!state.nativeWallet) {
    walletStatePillEl.textContent = "no wallet";
    walletDetailsEl.innerHTML = `
      <div>
        <dt>Status</dt>
        <dd>No browser wallet loaded.</dd>
      </div>
      <div>
        <dt>Recommended next step</dt>
        <dd>Generate a local wallet or import a JSON wallet file.</dd>
      </div>
    `;
    walletWarningEl.textContent =
      "Lamport sender addresses are single-use in this prototype. After you spend from one wallet, rotate to a fresh wallet for the next send.";
    return;
  }

  const balance = state.nativeBalance || {};
  walletStatePillEl.textContent = balance.balance !== undefined ? "ready" : "stored";
  walletDetailsEl.innerHTML = `
    <div>
      <dt>Address</dt>
      <dd class="mono">${state.nativeWallet.address}</dd>
    </div>
    <div>
      <dt>Algorithm</dt>
      <dd>${state.nativeWallet.algorithm}</dd>
    </div>
    <div>
      <dt>Balance</dt>
      <dd>${balance.balance !== undefined ? `${formatNumber(balance.balance)} PIKO` : "Connect a live node to load balance."}</dd>
    </div>
    <div>
      <dt>Next nonce</dt>
      <dd>${balance.next_nonce ?? "unknown"}</dd>
    </div>
  `;
  walletWarningEl.textContent = state.nativeWallet.warning || walletWarningEl.textContent;
}

function renderEvmDetails() {
  const connected = state.evmWallet;
  const founderMatch = connected && connected.toLowerCase() === founderAddress.toLowerCase();
  evmStatePillEl.textContent = connected ? (founderMatch ? "founder wallet" : "connected") : "not connected";
  evmDetailsEl.innerHTML = `
    <div>
      <dt>Connected EVM wallet</dt>
      <dd class="mono">${connected || "Connect MetaMask to use founder-claim signing."}</dd>
    </div>
    <div>
      <dt>Founder match</dt>
      <dd>${founderMatch ? "yes" : "no"}</dd>
    </div>
  `;
}

function renderOperatorDetails() {
  const consensus = state.consensus || {};
  const walletAddress = state.nativeWallet?.address || "";
  const selectedProposer = consensus.next_proposer || "open mining";
  const canMineOpen = !selectedProposer || selectedProposer === "open mining";
  const isSelectedProposer = walletAddress && selectedProposer === walletAddress;
  operatorDetailsEl.innerHTML = `
    <div>
      <dt>Consensus mode</dt>
      <dd>${consensus.consensus_mode || "snapshot"}</dd>
    </div>
    <div>
      <dt>Next proposer</dt>
      <dd class="mono">${selectedProposer}</dd>
    </div>
    <div>
      <dt>Your wallet selected</dt>
      <dd>${canMineOpen || isSelectedProposer ? "yes" : "no"}</dd>
    </div>
    <div>
      <dt>Pending tx count</dt>
      <dd>${formatNumber(state.status?.pending_transactions || 0)}</dd>
    </div>
  `;
  blockActionNoteEl.textContent =
    canMineOpen || isSelectedProposer
      ? "Your active wallet can try to confirm the next block now."
      : "Validator mode is active and another address is selected as the next proposer.";
}

function renderRawJson() {
  metadataJsonEl.textContent = JSON.stringify(state.metadata || {}, null, 2);
  consensusJsonEl.textContent = JSON.stringify(
    {
      status: state.status || {},
      consensus: state.consensus || {},
      native_wallet_balance: state.nativeBalance || {},
    },
    null,
    2,
  );
}

function refreshOverview() {
  const genesis = state.genesis;
  if (!genesis) {
    return;
  }

  const totalSupply = Object.values(genesis.balances || {}).reduce((sum, item) => sum + Number(item || 0), 0);
  const founderReserve = state.claim?.amount ?? genesis.balances?.[founderAddress] ?? 0;
  const status = state.status || {};
  const consensus = state.consensus || {};
  const metadata = state.metadata || genesis;

  renderMetricCards([
    { label: "Genesis Supply", value: `${formatNumber(totalSupply)} PIKO` },
    { label: "Founder Reserve", value: `${formatNumber(founderReserve)} PIKO` },
    { label: "Consensus", value: consensus.consensus_mode || "snapshot" },
  ]);

  renderStats([
    { label: "Chain ID", value: metadata.chain_id || genesis.chain_id },
    { label: "Network", value: metadata.network_name || genesis.network_name },
    { label: "Height", value: formatNumber(status.height || 0) },
    { label: "Finalized Height", value: formatNumber(consensus.finalized_height || 0) },
    { label: "Pending Txs", value: formatNumber(status.pending_transactions || 0) },
    { label: "Validators", value: formatNumber((consensus.validators || genesis.validators || []).length) },
    { label: "Vote Threshold", value: formatNumber(consensus.vote_threshold || 0) },
    { label: "Block Reward", value: `${formatNumber(genesis.block_reward || 0)} PIKO` },
  ]);

  renderAllocations(genesis);
  renderClaim(state.claim || normalizeClaimData({}));
  renderWalletDetails();
  renderEvmDetails();
  renderOperatorDetails();
  renderRawJson();
}

function setStatusMode(mode, message) {
  metadataStateEl.textContent = mode;
  consensusStateEl.textContent = mode;
  claimStatusTagEl.textContent = mode;
  apiMessageEl.textContent = message;
}

async function loadSnapshot() {
  const genesis = await fetchJson("./data/genesis.json");
  state.genesis = genesis;
  state.metadata = { ...genesis, icon_url: "./assets/pikocoin-icon.png" };
  state.status = {
    height: 0,
    pending_transactions: 0,
  };
  state.consensus = {
    consensus_mode: genesis.validators?.length ? "round_robin_validators" : "open-mining",
    validators: genesis.validators || [],
    vote_threshold: genesis.validators?.length ? Math.floor((2 * genesis.validators.length) / 3) + 1 : 0,
    finalized_height: 0,
  };
  state.claim = normalizeClaimData({
    address: founderAddress,
    available_balance: genesis.balances?.[founderAddress] || 0,
    claim_nonce: 0,
    claimed: false,
    pending: false,
    eligible: true,
  });
  refreshOverview();
  setStatusMode("snapshot", "Static genesis snapshot loaded. Connect a live node for wallet, claim, and transfer actions.");
}

async function refreshNativeWalletStatus() {
  if (!state.nativeWallet) {
    state.nativeBalance = null;
    renderWalletDetails();
    renderOperatorDetails();
    return;
  }
  try {
    state.nativeBalance = await fetchNodeJson(`/balance/${state.nativeWallet.address}`);
    renderWalletDetails();
    renderOperatorDetails();
  } catch (error) {
    state.nativeBalance = null;
    renderWalletDetails();
    renderOperatorDetails();
    logActivity("Native wallet balance unavailable", error.message, "warn");
  }
}

async function refreshClaimStatus() {
  try {
    const claim = await fetchNodeJson(`/claims/status/${founderAddress}`);
    state.claim = normalizeClaimData(claim);
    renderClaim(state.claim);
  } catch (error) {
    logActivity("Founder claim status unavailable", error.message, "warn");
  }
}

async function connectApi() {
  let base;
  try {
    base = requireApiBase();
  } catch (error) {
    setStatusMode("error", error.message);
    logActivity("API endpoint rejected", error.message, "error");
    return;
  }

  try {
    const [metadata, status, consensus, claim] = await Promise.all([
      fetchNodeJson("/metadata"),
      fetchNodeJson("/status"),
      fetchNodeJson("/consensus/status"),
      fetchNodeJson(`/claims/status/${founderAddress}`),
    ]);

    localStorage.setItem(apiStorageKey, base);
    state.metadata = metadata;
    state.status = status;
    state.consensus = consensus;
    state.claim = normalizeClaimData(claim);
    if (state.genesis) {
      state.genesis = {
        ...state.genesis,
        allocations: metadata.allocations || state.genesis.allocations,
        network_name: metadata.network_name || state.genesis.network_name,
        token_name: metadata.token_name || state.genesis.token_name,
        token_symbol: metadata.token_symbol || state.genesis.token_symbol,
      };
    }
    await refreshNativeWalletStatus();
    refreshOverview();
    setStatusMode("live", `Connected to ${base}. Live node data is now active.`);
    logActivity("Node connected", `Live node endpoint: ${base}`, "success");
  } catch (error) {
    setStatusMode("error", error.message);
    logActivity("Node connection failed", error.message, "error");
  }
}

function persistWallet(wallet) {
  state.nativeWallet = wallet;
  if (wallet) {
    storageSet(walletStorageKey, wallet);
  } else {
    localStorage.removeItem(walletStorageKey);
  }
  renderWalletDetails();
  renderOperatorDetails();
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function handleGenerateWallet() {
  try {
    setBusy("generate-wallet", true, "Generating...");
    const wallet = await generateLamportWallet();
    persistWallet(wallet);
    await refreshNativeWalletStatus();
    refreshOverview();
    logActivity("Native wallet generated", `New local wallet: ${wallet.address}`, "success");
  } catch (error) {
    logActivity("Wallet generation failed", error.message, "error");
  } finally {
    setBusy("generate-wallet", false, "Generating...");
  }
}

async function handleWalletImport(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  try {
    const content = await file.text();
    const wallet = await validateWallet(JSON.parse(content));
    persistWallet(wallet);
    await refreshNativeWalletStatus();
    refreshOverview();
    logActivity("Wallet imported", `Imported native wallet ${wallet.address}`, "success");
  } catch (error) {
    logActivity("Wallet import failed", error.message, "error");
  } finally {
    importWalletFileEl.value = "";
  }
}

function handleWalletDownload() {
  if (!state.nativeWallet) {
    logActivity("Download skipped", "Generate or import a native wallet first.", "warn");
    return;
  }
  downloadJson(`${state.nativeWallet.address}.json`, state.nativeWallet);
  logActivity("Wallet downloaded", `Saved ${shortAddress(state.nativeWallet.address)} as JSON.`, "success");
}

function handleClearWallet() {
  persistWallet(null);
  state.nativeBalance = null;
  refreshOverview();
  logActivity("Local wallet cleared", "Browser-stored native wallet has been removed from local storage.", "warn");
}

async function connectEvmWallet() {
  if (!window.ethereum) {
    logActivity("MetaMask unavailable", "No injected EVM wallet was found in this browser.", "error");
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    state.evmWallet = accounts[0] || null;
    renderEvmDetails();
    logActivity("MetaMask connected", `Connected EVM wallet: ${state.evmWallet}`, "success");
  } catch (error) {
    logActivity("MetaMask connection failed", error.message, "error");
  }
}

async function prepareClaimMessage() {
  if (!state.nativeWallet) {
    throw new Error("Generate or import a native wallet first.");
  }
  const payload = await fetchNodeJson("/claims/message", {
    method: "POST",
    body: {
      external_address: founderAddress,
      recipient: state.nativeWallet.address,
    },
  });
  state.claimMessage = payload.message || "";
  claimMessageBoxEl.value = state.claimMessage;
  state.claim = normalizeClaimData(payload.claim_status || payload);
  renderClaim(state.claim);
  logActivity("Claim message prepared", `Node prepared the founder claim message for ${state.nativeWallet.address}.`, "success");
  return payload;
}

async function submitFounderClaim() {
  if (!state.nativeWallet) {
    throw new Error("Generate or import a native wallet first.");
  }
  if (!window.ethereum) {
    throw new Error("MetaMask is required for founder-claim signing.");
  }
  if (!state.evmWallet) {
    await connectEvmWallet();
  }
  if (!state.evmWallet || state.evmWallet.toLowerCase() !== founderAddress.toLowerCase()) {
    throw new Error("Connect the founder EVM address before submitting the checked-in claim.");
  }
  if (!state.claimMessage) {
    await prepareClaimMessage();
  }
  let signature;
  try {
    signature = await window.ethereum.request({
      method: "personal_sign",
      params: [state.claimMessage, state.evmWallet],
    });
  } catch (error) {
    throw new Error(`MetaMask signing failed: ${error.message}`);
  }
  const result = await fetchNodeJson("/claims/external/claim", {
    method: "POST",
    body: {
      external_address: founderAddress,
      recipient: state.nativeWallet.address,
      signature,
    },
  });
  await refreshNodeState();
  logActivity("Founder claim submitted", result.message || "Claim transaction accepted into the mempool.", "success");
  return result;
}

async function submitTransfer() {
  if (!state.nativeWallet) {
    throw new Error("Generate or import a native wallet first.");
  }
  const recipient = sendRecipientEl.value.trim();
  const amount = Number.parseInt(sendAmountEl.value, 10);
  const note = sendNoteEl.value.trim();

  if (!recipient) {
    throw new Error("Enter a recipient address.");
  }
  if (!Number.isInteger(amount) || amount <= 0) {
    throw new Error("Amount must be a positive integer.");
  }

  const balanceInfo = await fetchNodeJson(`/balance/${state.nativeWallet.address}`);
  state.nativeBalance = balanceInfo;

  const transaction = {
    sender: state.nativeWallet.address,
    recipient,
    amount,
    nonce: balanceInfo.next_nonce,
    timestamp: Number((Date.now() / 1000).toFixed(6)),
    note,
    algorithm: state.nativeWallet.algorithm,
    public_key: state.nativeWallet.public_key,
    signature: [],
    extra: {},
  };
  transaction.signature = await signLamportTransaction(transaction, state.nativeWallet);

  const result = await fetchNodeJson("/tx/submit", {
    method: "POST",
    body: transaction,
  });

  await refreshNodeState();
  logActivity(
    "Native transfer submitted",
    `${amount} PIKO from ${shortAddress(state.nativeWallet.address)} to ${shortAddress(recipient)}.`,
    result.accepted ? "success" : "warn",
  );
  return result;
}

async function confirmNextBlock() {
  if (!state.nativeWallet) {
    throw new Error("Generate or import a native wallet first.");
  }
  const result = await fetchNodeJson("/mine", {
    method: "POST",
    body: { miner: state.nativeWallet.address },
  });
  await refreshNodeState();
  logActivity("Next block confirmed", result.message || "Block proposal accepted.", "success");
  return result;
}

async function refreshNodeState() {
  try {
    const [status, consensus] = await Promise.all([fetchNodeJson("/status"), fetchNodeJson("/consensus/status")]);
    state.status = status;
    state.consensus = consensus;
    await Promise.all([refreshNativeWalletStatus(), refreshClaimStatus()]);
    refreshOverview();
  } catch (error) {
    logActivity("Node refresh failed", error.message, "warn");
  }
}

async function handleAction(buttonId, busyLabel, fn) {
  try {
    setBusy(buttonId, true, busyLabel);
    await fn();
  } catch (error) {
    logActivity("Action failed", error.message, "error");
  } finally {
    setBusy(buttonId, false, busyLabel);
  }
}

async function maybeRestoreEvmWallet() {
  if (!window.ethereum) {
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: "eth_accounts" });
    state.evmWallet = accounts[0] || null;
    renderEvmDetails();
  } catch (error) {
    console.error(error);
  }
}

document.getElementById("connect-api").addEventListener("click", connectApi);
document.getElementById("load-snapshot").addEventListener("click", async () => {
  await loadSnapshot();
  logActivity("Snapshot restored", "Static genesis snapshot loaded back into the UI.", "info");
});
document.getElementById("copy-founder").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(founderAddress);
    logActivity("Founder address copied", founderAddress, "success");
  } catch (error) {
    logActivity("Copy failed", error.message, "error");
  }
});
document.getElementById("generate-wallet").addEventListener("click", handleGenerateWallet);
document.getElementById("download-wallet").addEventListener("click", handleWalletDownload);
document.getElementById("clear-wallet").addEventListener("click", handleClearWallet);
document.getElementById("refresh-wallet").addEventListener("click", () => handleAction("refresh-wallet", "Refreshing...", refreshNativeWalletStatus));
document.getElementById("connect-evm").addEventListener("click", connectEvmWallet);
document.getElementById("prepare-claim").addEventListener("click", () => handleAction("prepare-claim", "Preparing...", prepareClaimMessage));
document.getElementById("submit-claim").addEventListener("click", () => handleAction("submit-claim", "Signing...", submitFounderClaim));
document.getElementById("send-transaction").addEventListener("click", () => handleAction("send-transaction", "Submitting...", submitTransfer));
document.getElementById("confirm-next-block").addEventListener("click", () => handleAction("confirm-next-block", "Confirming...", confirmNextBlock));
document.getElementById("refresh-node").addEventListener("click", () => handleAction("refresh-node", "Refreshing...", refreshNodeState));
importWalletFileEl.addEventListener("change", handleWalletImport);

async function boot() {
  founderAddressEl.textContent = founderAddress;
  const savedBase = localStorage.getItem(apiStorageKey);
  if (savedBase) {
    apiInputEl.value = savedBase;
  } else if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
    apiInputEl.value = "http://127.0.0.1:8080";
  } else {
    apiInputEl.value = "https://api.piko.eu.cc";
  }

  await loadSnapshot();

  const storedWallet = storageGet(walletStorageKey);
  if (storedWallet) {
    try {
      persistWallet(await validateWallet(storedWallet));
      logActivity("Wallet restored", `Recovered ${storedWallet.address} from browser storage.`, "info");
    } catch (error) {
      localStorage.removeItem(walletStorageKey);
      logActivity("Stored wallet discarded", error.message, "warn");
    }
  }

  await maybeRestoreEvmWallet();
  renderActivityLog();
  refreshOverview();

  if (apiInputEl.value.trim()) {
    await connectApi();
  }
}

boot().catch((error) => {
  console.error(error);
  setStatusMode("error", "Page boot failed. Check the static assets and reload.");
  logActivity("Page boot failed", error.message, "error");
});
