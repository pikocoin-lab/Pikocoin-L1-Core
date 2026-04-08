import { createHash } from "node:crypto";

export const textEncoder = new TextEncoder();

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

export function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

export function roundToSix(value) {
  return Number(Number(value).toFixed(6));
}

export function asPositiveInteger(value, fieldName) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isInteger(parsed)) {
    throw new HttpError(400, `${fieldName} must be an integer.`);
  }
  return parsed;
}

export function asNonNegativeInteger(value, fieldName) {
  const parsed = asPositiveInteger(value, fieldName);
  if (parsed < 0) {
    throw new HttpError(400, `${fieldName} must be zero or greater.`);
  }
  return parsed;
}

export function stableStringify(value, withSpaces = false) {
  const comma = withSpaces ? ", " : ",";
  const colon = withSpaces ? ": " : ":";
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item, withSpaces)).join(comma)}]`;
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
    const keys = Object.keys(value).filter((key) => value[key] !== undefined).sort();
    return `{${keys
      .map((key) => `${JSON.stringify(key)}${colon}${stableStringify(value[key], withSpaces)}`)
      .join(comma)}}`;
  }
  return "null";
}

export function toBytes(value) {
  if (value instanceof Uint8Array) {
    return value;
  }
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  }
  if (value instanceof ArrayBuffer) {
    return new Uint8Array(value);
  }
  return textEncoder.encode(String(value));
}

export function sha256Bytes(value) {
  return new Uint8Array(createHash("sha256").update(toBytes(value)).digest());
}

export function sha256Hex(value) {
  return createHash("sha256").update(toBytes(value)).digest("hex");
}

export function hexToBytes(hex) {
  const clean = String(hex).replace(/^0x/, "").trim().toLowerCase();
  if (!clean || clean.length % 2 !== 0 || /[^0-9a-f]/u.test(clean)) {
    throw new HttpError(400, "Invalid hex payload.");
  }
  return Uint8Array.from(Buffer.from(clean, "hex"));
}

export function bytesToHex(bytes) {
  return Buffer.from(bytes).toString("hex");
}
