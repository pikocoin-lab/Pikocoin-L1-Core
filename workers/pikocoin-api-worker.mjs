import { DurableObject } from "cloudflare:workers";

import { CHAIN_OBJECT_NAME, ICON_URL } from "./api-constants.mjs";
import { HttpError } from "./api-utils.mjs";
import { PikocoinChainStateMachine, createInitialState } from "./pikocoin-api-core.mjs";

function corsHeaders(extra = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    ...extra,
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: corsHeaders({ "Content-Type": "application/json; charset=utf-8" }),
  });
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    throw new HttpError(400, "Invalid JSON body.");
  }
}

async function invokeStub(methodPromise, fallbackMessage = "Request failed.") {
  try {
    const result = await methodPromise;
    return jsonResponse(result.body, result.status);
  } catch (error) {
    const message = error instanceof Error ? error.message : fallbackMessage;
    return jsonResponse({ error: message }, 500);
  }
}

export class PikocoinChain extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    this.env = env;
    this.machine = new PikocoinChainStateMachine();
    this.ready = this.ctx.blockConcurrencyWhile(async () => {
      const stored = await this.ctx.storage.get("state");
      this.machine = new PikocoinChainStateMachine(stored || createInitialState());
      this.machine.recomputeFinality();
      await this.persist();
    });
  }

  async persist() {
    await this.ctx.storage.put("state", this.machine.exportState());
  }

  async getStatusRpc() {
    await this.ready;
    return { status: 200, body: this.machine.getStatus() };
  }

  async getMetadataRpc(baseUrl) {
    await this.ready;
    return { status: 200, body: this.machine.getMetadata(baseUrl) };
  }

  async getConsensusStatusRpc() {
    await this.ready;
    return { status: 200, body: this.machine.getConsensusStatus() };
  }

  async getClaimStatusRpc(externalAddress) {
    await this.ready;
    try {
      return { status: 200, body: this.machine.getClaimStatus(externalAddress) };
    } catch (error) {
      return { status: error.status || 400, body: { error: error.message } };
    }
  }

  async getBalanceRpc(address) {
    await this.ready;
    return { status: 200, body: this.machine.getBalance(address) };
  }

  async getBlockStatusRpc(blockRef) {
    await this.ready;
    try {
      return { status: 200, body: this.machine.getBlockStatus(blockRef) };
    } catch (error) {
      return { status: error.status || 404, body: { error: error.message } };
    }
  }

  async getChainRpc() {
    await this.ready;
    return { status: 200, body: this.machine.getChainSnapshot() };
  }

  async getRootRpc() {
    await this.ready;
    return {
      status: 200,
      body: {
        service: "pikocoin-edge-node",
        status: this.machine.getStatus(),
      },
    };
  }

  async buildClaimMessageRpc(payload) {
    await this.ready;
    const input = payload && typeof payload === "object" ? payload : {};
    try {
      return {
        status: 200,
        body: this.machine.getClaimMessage(input.external_address || "", input.recipient || ""),
      };
    } catch (error) {
      return { status: error.status || 400, body: { error: error.message } };
    }
  }

  async submitTransactionRpc(payload) {
    await this.ready;
    const input = payload && typeof payload === "object" ? payload : {};
    try {
      const result = this.machine.addTransaction(input);
      await this.persist();
      return { status: 202, body: { accepted: true, message: result.message } };
    } catch (error) {
      return { status: error.status || 400, body: { accepted: false, message: error.message } };
    }
  }

  async submitExternalClaimRpc(payload) {
    await this.ready;
    const input = payload && typeof payload === "object" ? payload : {};
    try {
      const claim = this.machine.getClaimMessage(input.external_address || "", input.recipient || "");
      const tx = {
        sender: claim.external_address,
        recipient: claim.recipient,
        amount: Number(claim.amount),
        nonce: Number(claim.claim_status?.claim_nonce ?? claim.claim_status?.nonce ?? 0),
        timestamp: Number((Date.now() / 1000).toFixed(6)),
        note: "External allocation claim",
        algorithm: "EVM_PERSONAL_CLAIM",
        public_key: [],
        signature: [],
        extra: {
          evm_signature: input.signature || "",
        },
      };
      const result = this.machine.addTransaction(tx);
      await this.persist();
      return {
        status: 202,
        body: {
          accepted: true,
          message: result.message,
          transaction: result.transaction,
        },
      };
    } catch (error) {
      return { status: error.status || 400, body: { accepted: false, message: error.message } };
    }
  }

  async mineRpc(payload) {
    await this.ready;
    const input = payload && typeof payload === "object" ? payload : {};
    try {
      const result = this.machine.mineBlock(input.miner || "");
      await this.persist();
      return { status: 200, body: result };
    } catch (error) {
      return { status: error.status || 400, body: { accepted: false, message: error.message } };
    }
  }
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      const path = url.pathname.replace(/\/$/, "") || "/";
      const chain = env.PIKO_CHAIN.getByName(CHAIN_OBJECT_NAME);

      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: corsHeaders() });
      }

      if (request.method === "GET" && path === "/") {
        return invokeStub(chain.getRootRpc());
      }
      if (request.method === "GET" && path === "/status") {
        return invokeStub(chain.getStatusRpc());
      }
      if (request.method === "GET" && path === "/metadata") {
        return invokeStub(chain.getMetadataRpc(url.origin));
      }
      if (request.method === "GET" && path === "/icon") {
        return Response.redirect(ICON_URL, 302);
      }
      if (request.method === "GET" && path.startsWith("/claims/status/")) {
        return invokeStub(chain.getClaimStatusRpc(path.slice("/claims/status/".length)));
      }
      if (request.method === "GET" && path === "/consensus/status") {
        return invokeStub(chain.getConsensusStatusRpc());
      }
      if (request.method === "GET" && path.startsWith("/balance/")) {
        return invokeStub(chain.getBalanceRpc(path.slice("/balance/".length)));
      }
      if (request.method === "GET" && path.startsWith("/blocks/status/")) {
        return invokeStub(chain.getBlockStatusRpc(path.slice("/blocks/status/".length)));
      }
      if (request.method === "GET" && path === "/chain") {
        return invokeStub(chain.getChainRpc());
      }

      if (request.method === "POST" && path === "/claims/message") {
        return invokeStub(chain.buildClaimMessageRpc(await readJson(request)));
      }
      if (request.method === "POST" && path === "/claims/external/claim") {
        return invokeStub(chain.submitExternalClaimRpc(await readJson(request)));
      }
      if (request.method === "POST" && path === "/tx/submit") {
        return invokeStub(chain.submitTransactionRpc(await readJson(request)));
      }
      if (request.method === "POST" && (path === "/mine" || path === "/consensus/propose")) {
        return invokeStub(chain.mineRpc(await readJson(request)));
      }

      return jsonResponse({ error: "Route not found." }, 404);
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      const message = error instanceof Error ? error.message : "Unexpected error.";
      return jsonResponse({ error: message }, status);
    }
  },
};
