import { LAMPORT_BITS } from "./api-constants.mjs";
import { hexToBytes, sha256Bytes, sha256Hex, stableStringify, textEncoder } from "./api-utils.mjs";

export function canonicalTransactionPayload(tx) {
  return stableStringify({
    amount: Number(tx.amount),
    nonce: Number(tx.nonce),
    note: tx.note || "",
    recipient: tx.recipient,
    sender: tx.sender,
    timestamp: Number(tx.timestamp),
  });
}

export function addressFromPublicKey(publicKey, algorithm = "LAMPORT_SHA256") {
  const payload = stableStringify({ algorithm, public_key: publicKey });
  return `piko1${sha256Hex(payload).slice(0, 40)}`;
}

export function blockHash(block) {
  return sha256Hex(stableStringify(block));
}

export function merkleRoot(transactions) {
  if (!transactions.length) {
    return sha256Hex(new Uint8Array());
  }
  let level = transactions.map((tx) => sha256Hex(stableStringify(tx, true)));
  while (level.length > 1) {
    if (level.length % 2 === 1) {
      level = [...level, level[level.length - 1]];
    }
    const nextLevel = [];
    for (let index = 0; index < level.length; index += 2) {
      nextLevel.push(sha256Hex(`${level[index]}${level[index + 1]}`));
    }
    level = nextLevel;
  }
  return level[0];
}

export function txDigest(payload) {
  return sha256Hex(stableStringify(payload, true));
}

export function verifyLamportSignature(messageBytes, publicKey, signature) {
  if (!Array.isArray(publicKey) || !Array.isArray(signature)) {
    return false;
  }
  if (publicKey.length !== LAMPORT_BITS || signature.length !== LAMPORT_BITS) {
    return false;
  }
  const digest = sha256Bytes(messageBytes);
  let keyIndex = 0;
  for (const byte of digest) {
    for (let bit = 7; bit >= 0; bit -= 1) {
      const selector = (byte >> bit) & 1;
      const row = publicKey[keyIndex];
      if (!Array.isArray(row) || row.length !== 2) {
        return false;
      }
      try {
        if (sha256Hex(hexToBytes(signature[keyIndex])) !== row[selector]) {
          return false;
        }
      } catch {
        return false;
      }
      keyIndex += 1;
    }
  }
  return true;
}

export function canonicalTransactionPayloadBytes(tx) {
  return textEncoder.encode(canonicalTransactionPayload(tx));
}
