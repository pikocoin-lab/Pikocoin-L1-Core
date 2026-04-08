const founderAddress = "0x30514237625b9e4206c728ff551725b4bf9d4a85";

const state = {
  genesis: null,
  metadata: null,
  status: null,
  consensus: null,
  claim: null,
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

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
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
              <strong class="allocation-amount">${item.address}</strong>
            </div>
            <span class="allocation-amount">${formatNumber(item.amount)} PIKO</span>
          </div>
          <p class="allocation-note">${item.note || "No note provided."}</p>
        </article>
      `,
    )
    .join("");
}

function renderClaim(claim) {
  const rows = [
    ["地址", claim.external_address || founderAddress],
    ["额度", `${formatNumber(claim.amount || 0)} PIKO`],
    ["是否已认领", claim.claimed ? "是" : "否"],
    ["claim nonce", claim.claim_nonce ?? 0],
    ["目标地址", claim.claimed_recipient || claim.pending_recipient || "待提交"],
  ];

  claimGridEl.innerHTML = rows
    .map(
      ([label, value]) => `
        <div>
          <dt>${label}</dt>
          <dd>${value}</dd>
        </div>
      `,
    )
    .join("");
}

function renderRawJson() {
  metadataJsonEl.textContent = JSON.stringify(state.metadata || {}, null, 2);
  consensusJsonEl.textContent = JSON.stringify(
    {
      status: state.status || {},
      consensus: state.consensus || {},
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
  const founderReserve = genesis.balances?.[founderAddress] || 0;
  const status = state.status || {};
  const consensus = state.consensus || {};
  const metadata = state.metadata || genesis;

  renderMetricCards([
    { label: "Genesis Supply", value: `${formatNumber(totalSupply)} PIKO` },
    { label: "Founder Reserve", value: `${formatNumber(founderReserve)} PIKO` },
    { label: "Consensus", value: consensus.consensus_mode || "genesis snapshot" },
  ]);

  renderStats([
    { label: "Chain ID", value: metadata.chain_id || genesis.chain_id },
    { label: "Network", value: metadata.network_name || genesis.network_name },
    { label: "Current Height", value: formatNumber(status.height || 0) },
    { label: "Finalized Height", value: formatNumber(consensus.finalized_height || 0) },
    { label: "Pending Txs", value: formatNumber(status.pending_transactions || 0) },
    { label: "Validators", value: formatNumber((consensus.validators || genesis.validators || []).length) },
    { label: "Vote Threshold", value: formatNumber(consensus.vote_threshold || 0) },
    { label: "Block Reward", value: `${formatNumber(genesis.block_reward || 0)} PIKO` },
  ]);

  renderRawJson();
  renderAllocations(genesis);
}

function setStatusMode(mode, message) {
  metadataStateEl.textContent = mode;
  consensusStateEl.textContent = mode;
  claimStatusTagEl.textContent = mode;
  apiMessageEl.textContent = message;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
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
    consensus_mode: genesis.validators?.length ? "validator_rotation" : "open_mining",
    validators: genesis.validators || [],
    vote_threshold: genesis.validators?.length ? Math.floor((2 * genesis.validators.length) / 3) + 1 : 0,
    finalized_height: 0,
  };
  state.claim = {
    external_address: founderAddress,
    amount: genesis.balances?.[founderAddress] || 0,
    claimed: false,
    claim_nonce: 0,
  };
  renderClaim(state.claim);
  refreshOverview();
  setStatusMode("snapshot", "当前展示的是仓库静态快照。接入节点 API 后，这里会自动切换到实时数据。");
}

async function connectApi() {
  const base = apiInputEl.value.trim().replace(/\/$/, "");
  if (!base) {
    setStatusMode("snapshot", "先填一个节点地址，例如 http://127.0.0.1:8080。");
    return;
  }

  localStorage.setItem("piko_api_base", base);

  try {
    const [metadata, status, consensus, claim] = await Promise.all([
      fetchJson(`${base}/metadata`),
      fetchJson(`${base}/status`),
      fetchJson(`${base}/consensus/status`),
      fetchJson(`${base}/claims/status/${founderAddress}`),
    ]);

    state.metadata = metadata;
    state.status = status;
    state.consensus = consensus;
    state.claim = claim;
    renderClaim(claim);
    refreshOverview();
    setStatusMode("live", `已连接 ${base}。页面正在展示实时节点状态。`);
  } catch (error) {
    console.error(error);
    setStatusMode("error", `连接 ${base} 失败。页面已保留静态快照，可稍后再接节点。`);
  }
}

document.getElementById("connect-api").addEventListener("click", connectApi);
document.getElementById("load-snapshot").addEventListener("click", loadSnapshot);
document.getElementById("copy-founder").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(founderAddress);
    founderAddressEl.textContent = `${founderAddress}  已复制`;
    window.setTimeout(() => {
      founderAddressEl.textContent = founderAddress;
    }, 1600);
  } catch (error) {
    console.error(error);
  }
});

async function boot() {
  founderAddressEl.textContent = founderAddress;
  const savedBase = localStorage.getItem("piko_api_base");
  if (savedBase) {
    apiInputEl.value = savedBase;
  } else if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
    apiInputEl.value = "http://127.0.0.1:8080";
  }

  await loadSnapshot();

  if (apiInputEl.value.trim()) {
    await connectApi();
  }
}

boot().catch((error) => {
  console.error(error);
  setStatusMode("error", "页面初始化失败，请检查静态文件是否完整。");
});
