export const ICON_URL = "https://piko.eu.cc/assets/pikocoin-icon.png";
export const CHAIN_OBJECT_NAME = "pikocoin-mainnet-alpha";
export const FOUNDER_ADDRESS = "0x30514237625b9e4206c728ff551725b4bf9d4a85";
export const ZERO_HASH = "0".repeat(64);
export const LAMPORT_BITS = 256;
export const UINT64_MASK = (1n << 64n) - 1n;
export const KECCAK_RATE_BYTES = 136;
export const ROTATION_OFFSETS = [
  [0, 36, 3, 41, 18],
  [1, 44, 10, 45, 2],
  [62, 6, 43, 15, 61],
  [28, 55, 25, 21, 56],
  [27, 20, 39, 8, 14],
];
export const ROUND_CONSTANTS = [
  0x0000000000000001n,
  0x0000000000008082n,
  0x800000000000808an,
  0x8000000080008000n,
  0x000000000000808bn,
  0x0000000080000001n,
  0x8000000080008081n,
  0x8000000000008009n,
  0x000000000000008an,
  0x0000000000000088n,
  0x0000000080008009n,
  0x000000008000000an,
  0x000000008000808bn,
  0x800000000000008bn,
  0x8000000000008089n,
  0x8000000000008003n,
  0x8000000000008002n,
  0x8000000000000080n,
  0x000000000000800an,
  0x800000008000000an,
  0x8000000080008081n,
  0x8000000000008080n,
  0x0000000080000001n,
  0x8000000080008008n,
];
export const SECP256K1_P = 0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2fn;
export const SECP256K1_N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
export const SECP256K1_GX = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798n;
export const SECP256K1_GY = 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8n;
export const GENERATOR = [SECP256K1_GX, SECP256K1_GY];

export const DEFAULT_GENESIS = {
  chain_id: "pikocoin-mainnet-alpha",
  network_name: "Pikocoin Sovereign Network",
  token_name: "Pikocoin",
  token_symbol: "PIKO",
  token_decimals: 0,
  icon_path: "assets/pikocoin-icon.png",
  description: "Privacy-oriented, validator-driven sovereign blockchain prototype.",
  genesis_time: 1775625600.0,
  block_reward: 25,
  difficulty_prefix: "00",
  balances: {
    "0x30514237625b9e4206c728ff551725b4bf9d4a85": 180000000,
    piko1ecosystemreserve0000000000000000000000: 220000000,
    piko1communityrewards000000000000000000000: 200000000,
    piko1validatorrewards000000000000000000000: 150000000,
    piko1liquidityreserve000000000000000000000: 100000000,
    piko1aiprivacyresearch00000000000000000000: 100000000,
    piko1foundationops0000000000000000000000: 50000000,
  },
  validators: [],
  allocations: [
    {
      label: "Founder and Governance Treasury",
      address: "0x30514237625b9e4206c728ff551725b4bf9d4a85",
      amount: 180000000,
      note: "Primary founder reserve and governance treasury.",
    },
    {
      label: "Ecosystem Treasury",
      address: "piko1ecosystemreserve0000000000000000000000",
      amount: 220000000,
      note: "Liquidity programs, ecosystem grants, and strategic growth.",
    },
    {
      label: "Community Incentives",
      address: "piko1communityrewards000000000000000000000",
      amount: 200000000,
      note: "Airdrops, quests, referrals, and community mining events.",
    },
    {
      label: "Validator Security Rewards",
      address: "piko1validatorrewards000000000000000000000",
      amount: 150000000,
      note: "Bootstraps validator incentives before ongoing block rewards take over.",
    },
    {
      label: "Liquidity and Market Operations",
      address: "piko1liquidityreserve000000000000000000000",
      amount: 100000000,
      note: "Cross-exchange liquidity, MM operations, and launch support.",
    },
    {
      label: "AI and Privacy R&D Fund",
      address: "piko1aiprivacyresearch00000000000000000000",
      amount: 100000000,
      note: "Funds zk, PQC, AI coprocessor, and privacy research.",
    },
    {
      label: "Foundation Operations",
      address: "piko1foundationops0000000000000000000000",
      amount: 50000000,
      note: "Audits, legal, infrastructure, and long-run operations.",
    },
  ],
};
