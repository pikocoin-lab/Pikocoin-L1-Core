import {
  GENERATOR,
  KECCAK_RATE_BYTES,
  ROTATION_OFFSETS,
  ROUND_CONSTANTS,
  SECP256K1_N,
  SECP256K1_P,
  UINT64_MASK,
} from "./api-constants.mjs";
import { HttpError, bytesToHex, hexToBytes, textEncoder, toBytes } from "./api-utils.mjs";

function mod(value, modulus) {
  const result = value % modulus;
  return result >= 0n ? result : result + modulus;
}

function rotl64(value, shift) {
  const normalized = BigInt(shift);
  if (normalized === 0n) {
    return value & UINT64_MASK;
  }
  return ((value << normalized) | (value >> (64n - normalized))) & UINT64_MASK;
}

function leBytesToBigInt(bytes) {
  let value = 0n;
  for (let index = bytes.length - 1; index >= 0; index -= 1) {
    value = (value << 8n) | BigInt(bytes[index]);
  }
  return value;
}

function bigIntToLeBytes(value, byteLength = 8) {
  const output = new Uint8Array(byteLength);
  let remaining = value;
  for (let index = 0; index < byteLength; index += 1) {
    output[index] = Number(remaining & 0xffn);
    remaining >>= 8n;
  }
  return output;
}

function keccakF(state) {
  for (const roundConstant of ROUND_CONSTANTS) {
    const c = [];
    for (let x = 0; x < 5; x += 1) {
      c[x] = state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20];
    }
    const d = [];
    for (let x = 0; x < 5; x += 1) {
      d[x] = c[(x + 4) % 5] ^ rotl64(c[(x + 1) % 5], 1);
    }
    for (let x = 0; x < 5; x += 1) {
      for (let y = 0; y < 5; y += 1) {
        state[x + 5 * y] ^= d[x];
      }
    }

    const b = new Array(25).fill(0n);
    for (let x = 0; x < 5; x += 1) {
      for (let y = 0; y < 5; y += 1) {
        b[y + 5 * ((2 * x + 3 * y) % 5)] = rotl64(state[x + 5 * y], ROTATION_OFFSETS[x][y]);
      }
    }

    for (let x = 0; x < 5; x += 1) {
      for (let y = 0; y < 5; y += 1) {
        state[x + 5 * y] =
          b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y] & UINT64_MASK) & b[(x + 2) % 5 + 5 * y]);
      }
    }

    state[0] ^= roundConstant;
  }
}

export function keccak256(data) {
  const state = new Array(25).fill(0n);
  const padded = Array.from(toBytes(data));
  padded.push(0x01);
  while (padded.length % KECCAK_RATE_BYTES !== KECCAK_RATE_BYTES - 1) {
    padded.push(0x00);
  }
  padded.push(0x80);

  for (let offset = 0; offset < padded.length; offset += KECCAK_RATE_BYTES) {
    const block = padded.slice(offset, offset + KECCAK_RATE_BYTES);
    for (let laneIndex = 0; laneIndex < KECCAK_RATE_BYTES / 8; laneIndex += 1) {
      const start = laneIndex * 8;
      state[laneIndex] ^= leBytesToBigInt(block.slice(start, start + 8));
    }
    keccakF(state);
  }

  const output = [];
  while (output.length < 32) {
    for (const lane of state.slice(0, KECCAK_RATE_BYTES / 8)) {
      output.push(...bigIntToLeBytes(lane));
      if (output.length >= 32) {
        break;
      }
    }
    if (output.length >= 32) {
      break;
    }
    keccakF(state);
  }
  return Uint8Array.from(output.slice(0, 32));
}

function personalMessageHash(message) {
  const payload = typeof message === "string" ? textEncoder.encode(message) : toBytes(message);
  const prefix = textEncoder.encode(`\x19Ethereum Signed Message:\n${payload.length}`);
  const combined = new Uint8Array(prefix.length + payload.length);
  combined.set(prefix, 0);
  combined.set(payload, prefix.length);
  return keccak256(combined);
}

export function normalizeEvmAddress(address) {
  const value = String(address || "").trim().toLowerCase();
  if (!value.startsWith("0x") || value.length !== 42 || /[^0-9a-f]/u.test(value.slice(2))) {
    throw new HttpError(400, "Expected a 20-byte hex EVM address.");
  }
  return value;
}

export function buildClaimMessage(chainId, externalAddress, recipient, amount) {
  return (
    "Pikocoin External Allocation Claim\n" +
    `chain_id:${chainId}\n` +
    `source:${normalizeEvmAddress(externalAddress)}\n` +
    `recipient:${recipient}\n` +
    `amount:${Number(amount)}\n` +
    "action:claim_external_allocation"
  );
}

function powMod(base, exponent, modulus) {
  let result = 1n;
  let factor = mod(base, modulus);
  let power = exponent;
  while (power > 0n) {
    if (power & 1n) {
      result = mod(result * factor, modulus);
    }
    factor = mod(factor * factor, modulus);
    power >>= 1n;
  }
  return result;
}

function inverseMod(value, modulus) {
  return powMod(mod(value, modulus), modulus - 2n, modulus);
}

function pointAdd(left, right) {
  if (!left) {
    return right;
  }
  if (!right) {
    return left;
  }
  const [x1, y1] = left;
  const [x2, y2] = right;
  if (x1 === x2 && mod(y1 + y2, SECP256K1_P) === 0n) {
    return null;
  }
  let slope;
  if (x1 === x2 && y1 === y2) {
    slope = mod(3n * x1 * x1 * inverseMod(2n * y1, SECP256K1_P), SECP256K1_P);
  } else {
    slope = mod((y2 - y1) * inverseMod(x2 - x1, SECP256K1_P), SECP256K1_P);
  }
  const x3 = mod(slope * slope - x1 - x2, SECP256K1_P);
  const y3 = mod(slope * (x1 - x3) - y1, SECP256K1_P);
  return [x3, y3];
}

function pointNeg(point) {
  if (!point) {
    return null;
  }
  return [point[0], mod(-point[1], SECP256K1_P)];
}

function pointMul(scalar, point) {
  const normalized = mod(scalar, SECP256K1_N);
  if (!point || normalized === 0n) {
    return null;
  }
  if (scalar < 0n) {
    return pointMul(-scalar, pointNeg(point));
  }
  let result = null;
  let addend = point;
  let k = scalar;
  while (k > 0n) {
    if (k & 1n) {
      result = pointAdd(result, addend);
    }
    addend = pointAdd(addend, addend);
    k >>= 1n;
  }
  return result;
}

function liftX(xValue, yParity) {
  const alpha = mod(powMod(xValue, 3n, SECP256K1_P) + 7n, SECP256K1_P);
  const beta = powMod(alpha, (SECP256K1_P + 1n) / 4n, SECP256K1_P);
  const yValue = Number(beta % 2n) === yParity ? beta : mod(-beta, SECP256K1_P);
  if (powMod(yValue, 2n, SECP256K1_P) !== alpha) {
    throw new HttpError(400, "Invalid secp256k1 x-coordinate.");
  }
  return [xValue, yValue];
}

function bigIntFromBytes(bytes) {
  let value = 0n;
  for (const byte of bytes) {
    value = (value << 8n) | BigInt(byte);
  }
  return value;
}

function bigIntToBeBytes(value, byteLength = 32) {
  const output = new Uint8Array(byteLength);
  let remaining = value;
  for (let index = byteLength - 1; index >= 0; index -= 1) {
    output[index] = Number(remaining & 0xffn);
    remaining >>= 8n;
  }
  return output;
}

function addressFromPublicPoint(point) {
  const encoded = new Uint8Array(65);
  encoded[0] = 0x04;
  encoded.set(bigIntToBeBytes(point[0], 32), 1);
  encoded.set(bigIntToBeBytes(point[1], 32), 33);
  return `0x${bytesToHex(keccak256(encoded.slice(1)).slice(-20))}`;
}

function verifyDigest(publicPoint, digest, r, s) {
  if (!(1n <= r && r < SECP256K1_N && 1n <= s && s < SECP256K1_N)) {
    return false;
  }
  const digestInt = mod(bigIntFromBytes(digest), SECP256K1_N);
  const sInverse = inverseMod(s, SECP256K1_N);
  const u1 = mod(digestInt * sInverse, SECP256K1_N);
  const u2 = mod(r * sInverse, SECP256K1_N);
  const point = pointAdd(pointMul(u1, GENERATOR), pointMul(u2, publicPoint));
  return point !== null && mod(point[0], SECP256K1_N) === r;
}

function recoverPublicPoint(digest, signatureHex) {
  const signatureBytes = hexToBytes(signatureHex);
  if (signatureBytes.length !== 65) {
    throw new HttpError(400, "Expected a 65-byte hex Ethereum signature.");
  }
  const r = bigIntFromBytes(signatureBytes.slice(0, 32));
  const s = bigIntFromBytes(signatureBytes.slice(32, 64));
  const v = signatureBytes[64];
  if (!(1n <= r && r < SECP256K1_N && 1n <= s && s < SECP256K1_N)) {
    throw new HttpError(400, "Signature scalars are out of range.");
  }

  let recoveryId;
  if (v === 27 || v === 28) {
    recoveryId = v - 27;
  } else if (v >= 0 && v <= 3) {
    recoveryId = v;
  } else if (v >= 35) {
    recoveryId = (v - 35) % 2;
  } else {
    throw new HttpError(400, "Unsupported recovery id.");
  }

  const xValue = r + BigInt(Math.floor(recoveryId / 2)) * SECP256K1_N;
  if (xValue >= SECP256K1_P) {
    throw new HttpError(400, "Recovered x-coordinate is outside the curve field.");
  }
  const pointR = liftX(xValue, recoveryId % 2);
  if (pointMul(SECP256K1_N, pointR) !== null) {
    throw new HttpError(400, "Recovered point is not on the secp256k1 subgroup.");
  }

  const digestInt = mod(bigIntFromBytes(digest), SECP256K1_N);
  const rInverse = inverseMod(r, SECP256K1_N);
  const publicPoint = pointAdd(
    pointMul(mod(s * rInverse, SECP256K1_N), pointR),
    pointMul(mod(-digestInt * rInverse, SECP256K1_N), GENERATOR),
  );
  if (!publicPoint || !verifyDigest(publicPoint, digest, r, s)) {
    throw new HttpError(400, "Recovered public key does not verify the signature.");
  }
  return publicPoint;
}

export function verifyPersonalSignature(address, message, signatureHex) {
  try {
    const expected = normalizeEvmAddress(address);
    const publicPoint = recoverPublicPoint(personalMessageHash(message), signatureHex);
    return expected === addressFromPublicPoint(publicPoint);
  } catch {
    return false;
  }
}

export const testing = {
  pointAdd,
  pointMul,
  recoverPublicPoint,
};
