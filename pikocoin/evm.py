"""Minimal EVM-style signing helpers for allocation claims."""

from __future__ import annotations

from hashlib import sha256
from hmac import new as hmac_new
from typing import Final


SECP256K1_P: Final[int] = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP256K1_N: Final[int] = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_GX: Final[int] = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
SECP256K1_GY: Final[int] = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
_UINT64_MASK: Final[int] = (1 << 64) - 1
_KECCAK_RATE_BYTES: Final[int] = 136
_ROTATION_OFFSETS: Final[list[list[int]]] = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_ROUND_CONSTANTS: Final[list[int]] = [
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
]
_GENERATOR: Final[tuple[int, int]] = (SECP256K1_GX, SECP256K1_GY)


def normalize_evm_address(address: str) -> str:
    value = address.strip().lower()
    if not value.startswith("0x") or len(value) != 42:
        raise ValueError("Expected a 20-byte hex EVM address.")
    int(value[2:], 16)
    return value


def build_claim_message(chain_id: str, external_address: str, recipient: str, amount: int) -> str:
    return (
        "Pikocoin External Allocation Claim\n"
        f"chain_id:{chain_id}\n"
        f"source:{normalize_evm_address(external_address)}\n"
        f"recipient:{recipient}\n"
        f"amount:{int(amount)}\n"
        "action:claim_external_allocation"
    )


def keccak256(data: bytes) -> bytes:
    state = [0] * 25
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _KECCAK_RATE_BYTES != _KECCAK_RATE_BYTES - 1:
        padded.append(0x00)
    padded.append(0x80)

    for offset in range(0, len(padded), _KECCAK_RATE_BYTES):
        block = padded[offset : offset + _KECCAK_RATE_BYTES]
        for lane_index in range(_KECCAK_RATE_BYTES // 8):
            start = lane_index * 8
            state[lane_index] ^= int.from_bytes(block[start : start + 8], "little")
        _keccak_f(state)

    output = bytearray()
    while len(output) < 32:
        for lane in state[: _KECCAK_RATE_BYTES // 8]:
            output.extend(lane.to_bytes(8, "little"))
        if len(output) >= 32:
            break
        _keccak_f(state)
    return bytes(output[:32])


def personal_message_hash(message: str | bytes) -> bytes:
    payload = message.encode("utf-8") if isinstance(message, str) else message
    prefix = f"\x19Ethereum Signed Message:\n{len(payload)}".encode("utf-8")
    return keccak256(prefix + payload)


def address_from_private_key_hex(private_key_hex: str) -> str:
    private_key = _parse_private_key(private_key_hex)
    public_point = _point_mul(private_key, _GENERATOR)
    if public_point is None:
        raise ValueError("Invalid private key.")
    return address_from_public_point(public_point)


def address_from_public_point(point: tuple[int, int]) -> str:
    encoded = b"\x04" + point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")
    return "0x" + keccak256(encoded[1:])[-20:].hex()


def sign_personal_message(private_key_hex: str, message: str) -> str:
    private_key = _parse_private_key(private_key_hex)
    digest = personal_message_hash(message)
    r, s, recovery_id = _sign_digest(private_key, digest)
    return "0x" + r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex() + bytes([27 + recovery_id]).hex()


def recover_evm_address(message: str, signature_hex: str) -> str:
    digest = personal_message_hash(message)
    public_point = _recover_public_point(digest, signature_hex)
    if public_point is None:
        raise ValueError("Unable to recover a valid secp256k1 public key from the signature.")
    return address_from_public_point(public_point)


def verify_personal_signature(address: str, message: str, signature_hex: str) -> bool:
    try:
        expected = normalize_evm_address(address)
        recovered = recover_evm_address(message, signature_hex)
    except ValueError:
        return False
    return expected == recovered


def _parse_private_key(private_key_hex: str) -> int:
    value = private_key_hex.strip().lower()
    if value.startswith("0x"):
        value = value[2:]
    private_key = int(value, 16)
    if not 1 <= private_key < SECP256K1_N:
        raise ValueError("Private key is out of range for secp256k1.")
    return private_key


def _rotl64(value: int, shift: int) -> int:
    if shift == 0:
        return value & _UINT64_MASK
    return ((value << shift) | (value >> (64 - shift))) & _UINT64_MASK


def _keccak_f(state: list[int]) -> None:
    for round_constant in _ROUND_CONSTANTS:
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]

        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl64(state[x + 5 * y], _ROTATION_OFFSETS[x][y])

        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])

        state[0] ^= round_constant


def _inverse_mod(value: int, modulus: int) -> int:
    return pow(value % modulus, -1, modulus)


def _point_add(
    left: tuple[int, int] | None,
    right: tuple[int, int] | None,
) -> tuple[int, int] | None:
    if left is None:
        return right
    if right is None:
        return left

    x1, y1 = left
    x2, y2 = right
    if x1 == x2 and (y1 + y2) % SECP256K1_P == 0:
        return None

    if left == right:
        slope = (3 * x1 * x1) * _inverse_mod(2 * y1, SECP256K1_P)
    else:
        slope = (y2 - y1) * _inverse_mod(x2 - x1, SECP256K1_P)
    slope %= SECP256K1_P

    x3 = (slope * slope - x1 - x2) % SECP256K1_P
    y3 = (slope * (x1 - x3) - y1) % SECP256K1_P
    return (x3, y3)


def _point_neg(point: tuple[int, int] | None) -> tuple[int, int] | None:
    if point is None:
        return None
    return (point[0], (-point[1]) % SECP256K1_P)


def _point_mul(scalar: int, point: tuple[int, int] | None) -> tuple[int, int] | None:
    if point is None or scalar % SECP256K1_N == 0:
        return None
    if scalar < 0:
        return _point_mul(-scalar, _point_neg(point))

    result = None
    addend = point
    k = scalar
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    return result


def _lift_x(x_value: int, y_parity: int) -> tuple[int, int]:
    alpha = (pow(x_value, 3, SECP256K1_P) + 7) % SECP256K1_P
    beta = pow(alpha, (SECP256K1_P + 1) // 4, SECP256K1_P)
    y_value = beta if beta % 2 == y_parity else (-beta) % SECP256K1_P
    if pow(y_value, 2, SECP256K1_P) != alpha:
        raise ValueError("Invalid secp256k1 x-coordinate.")
    return (x_value, y_value)


def _int2octets(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _bits2octets(data: bytes) -> bytes:
    return _int2octets(int.from_bytes(data, "big") % SECP256K1_N)


def _rfc6979_generate_k(private_key: int, digest: bytes) -> int:
    v = b"\x01" * 32
    k = b"\x00" * 32
    x = _int2octets(private_key)
    h1 = _bits2octets(digest)

    k = hmac_new(k, v + b"\x00" + x + h1, sha256).digest()
    v = hmac_new(k, v, sha256).digest()
    k = hmac_new(k, v + b"\x01" + x + h1, sha256).digest()
    v = hmac_new(k, v, sha256).digest()

    while True:
        candidate = b""
        while len(candidate) < 32:
            v = hmac_new(k, v, sha256).digest()
            candidate += v
        secret = int.from_bytes(candidate[:32], "big")
        if 1 <= secret < SECP256K1_N:
            return secret
        k = hmac_new(k, v + b"\x00", sha256).digest()
        v = hmac_new(k, v, sha256).digest()


def _sign_digest(private_key: int, digest: bytes) -> tuple[int, int, int]:
    digest_int = int.from_bytes(digest, "big") % SECP256K1_N
    while True:
        k = _rfc6979_generate_k(private_key, digest)
        point_r = _point_mul(k, _GENERATOR)
        if point_r is None:
            continue
        r = point_r[0] % SECP256K1_N
        if r == 0:
            continue
        s = (_inverse_mod(k, SECP256K1_N) * (digest_int + r * private_key)) % SECP256K1_N
        if s == 0:
            continue
        recovery_id = (2 if point_r[0] >= SECP256K1_N else 0) | (point_r[1] & 1)
        if s > SECP256K1_N // 2:
            s = SECP256K1_N - s
            recovery_id ^= 1
        return r, s, recovery_id


def _recover_public_point(digest: bytes, signature_hex: str) -> tuple[int, int] | None:
    signature = signature_hex[2:] if signature_hex.startswith("0x") else signature_hex
    signature_bytes = bytes.fromhex(signature)
    if len(signature_bytes) != 65:
        raise ValueError("Expected a 65-byte hex Ethereum signature.")

    r = int.from_bytes(signature_bytes[:32], "big")
    s = int.from_bytes(signature_bytes[32:64], "big")
    v = signature_bytes[64]
    if not 1 <= r < SECP256K1_N or not 1 <= s < SECP256K1_N:
        raise ValueError("Signature scalars are out of range.")

    if v in (27, 28):
        recovery_id = v - 27
    elif v in (0, 1, 2, 3):
        recovery_id = v
    elif v >= 35:
        recovery_id = (v - 35) % 2
    else:
        raise ValueError("Unsupported recovery id.")

    x_value = r + (recovery_id // 2) * SECP256K1_N
    if x_value >= SECP256K1_P:
        raise ValueError("Recovered x-coordinate is outside the curve field.")

    point_r = _lift_x(x_value, recovery_id % 2)
    if _point_mul(SECP256K1_N, point_r) is not None:
        raise ValueError("Recovered point is not on the secp256k1 subgroup.")

    digest_int = int.from_bytes(digest, "big") % SECP256K1_N
    r_inverse = _inverse_mod(r, SECP256K1_N)
    public_point = _point_add(
        _point_mul((s * r_inverse) % SECP256K1_N, point_r),
        _point_mul((-digest_int * r_inverse) % SECP256K1_N, _GENERATOR),
    )
    if public_point is None or not _verify_digest(public_point, digest, r, s):
        raise ValueError("Recovered public key does not verify the signature.")
    return public_point


def _verify_digest(public_point: tuple[int, int], digest: bytes, r: int, s: int) -> bool:
    if not 1 <= r < SECP256K1_N or not 1 <= s < SECP256K1_N:
        return False
    digest_int = int.from_bytes(digest, "big") % SECP256K1_N
    s_inverse = _inverse_mod(s, SECP256K1_N)
    u1 = (digest_int * s_inverse) % SECP256K1_N
    u2 = (r * s_inverse) % SECP256K1_N
    point = _point_add(_point_mul(u1, _GENERATOR), _point_mul(u2, public_point))
    return point is not None and point[0] % SECP256K1_N == r
