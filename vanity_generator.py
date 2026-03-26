#!/usr/bin/env python3
"""
PyBitcoinVanity - Advanced Bitcoin Vanity Address Generator
===========================================================

Fast, multithreaded Bitcoin vanity address generator that supports:
- Legacy addresses (starts with 1Veronica)
- Bech32 addresses (starts with bc1qveronice)

Author: Grok for you
Version: 1.0.0
License: MIT
"""

import argparse
import hashlib
import os
import time
import json
import logging
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional, List, Dict
from datetime import datetime
from tqdm import tqdm
from ecdsa import SigningKey, SECP256k1

# ====================== LOGGING SETUP ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PyBitcoinVanity")

# ====================== CONSTANTS ======================
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'

# Global stop flag for graceful shutdown
stop_event = threading.Event()

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info("\n🛑 Shutdown signal received. Stopping all threads...")
    stop_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ====================== CRYPTOGRAPHIC HELPERS ======================
def double_sha256(data: bytes) -> bytes:
    """Bitcoin uses double SHA256."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def base58_encode(payload: bytes) -> str:
    """Convert bytes to Base58 string (Bitcoin compatible)."""
    # Count leading zeros
    leading_zeros = len(payload) - len(payload.lstrip(b'\0'))
    
    # Convert to big integer
    num = int.from_bytes(payload, 'big')
    result = []
    
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(BASE58_ALPHABET[rem])
    
    # Add '1' for each leading zero
    return '1' * leading_zeros + ''.join(reversed(result))

def get_compressed_public_key(sk: SigningKey) -> bytes:
    """Return compressed public key (33 bytes)."""
    vk = sk.verifying_key
    x = vk.pubkey.point.x().to_bytes(32, 'big')
    y_parity = b'\x02' if vk.pubkey.point.y() % 2 == 0 else b'\x03'
    return y_parity + x

def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data))"""
    sha256 = hashlib.sha256(data).digest()
    ripemd160 = hashlib.new('ripemd160', sha256).digest()
    return ripemd160

# ====================== BECH32 (SegWit) IMPLEMENTATION ======================
def bech32_polymod(values: list) -> int:
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk

def bech32_hrp_expand(hrp: str) -> list:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def bech32_create_checksum(hrp: str, data: list) -> list:
    values = bech32_hrp_expand(hrp) + data
    mod = bech32_polymod(values + [0] * 6) ^ 1
    return [(mod >> (5 * (5 - i))) & 31 for i in range(6)]

def convert_bits(data: bytes, from_bits: int, to_bits: int, pad: bool = True) -> list:
    """General power-of-2 bit conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << to_bits) - 1
    max_acc = (1 << (from_bits + to_bits - 1)) - 1

    for value in data:
        if value < 0 or (value >> from_bits):
            raise ValueError("Invalid value")
        acc = ((acc << from_bits) | value) & max_acc
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            ret.append((acc >> bits) & maxv)

    if pad and bits:
        ret.append((acc << (to_bits - bits)) & maxv)
    elif bits >= from_bits or ((acc << (to_bits - bits)) & maxv):
        raise ValueError("Invalid padding")

    return ret

def encode_bech32_address(hash160_bytes: bytes) -> str:
    """Create bc1q... Bech32 address."""
    hrp = "bc"
    version = 0
    data = [version] + convert_bits(hash160_bytes, 8, 5, pad=True)
    checksum = bech32_create_checksum(hrp, data)
    combined = data + checksum
    return hrp + "1" + "".join(BECH32_CHARSET[d] for d in combined)

# ====================== ADDRESS CONVERSION ======================
def private_key_to_wif(private_key: bytes) -> str:
    """Convert 32-byte private key to Wallet Import Format (WIF)."""
    extended = b'\x80' + private_key
    checksum = double_sha256(extended)[:4]
    return base58_encode(extended + checksum)

def generate_legacy_address(private_key: bytes) -> Tuple[str, str]:
    """Generate Legacy (P2PKH) address starting with 1."""
    sk = SigningKey.from_string(private_key, curve=SECP256k1)
    pubkey = get_compressed_public_key(sk)
    h160 = hash160(pubkey)
    
    payload = b'\x00' + h160
    checksum = double_sha256(payload)[:4]
    address = base58_encode(payload + checksum)
    wif = private_key_to_wif(private_key)
    return address, wif

def generate_bech32_address(private_key: bytes) -> Tuple[str, str]:
    """Generate Bech32 (SegWit P2WPKH) address starting with bc1q."""
    sk = SigningKey.from_string(private_key, curve=SECP256k1)
    pubkey = get_compressed_public_key(sk)
    h160 = hash160(pubkey)
    address = encode_bech32_address(h160)
    wif = private_key_to_wif(private_key)
    return address, wif

# ====================== VANITY GENERATION CORE ======================
def generate_single_key(prefix: str, addr_type: str) -> Optional[Dict]:
    """Generate one random key and check if it matches the prefix."""
    if stop_event.is_set():
        return None

    try:
        private_key = os.urandom(32)

        if addr_type == "legacy":
            address, wif = generate_legacy_address(private_key)
        else:
            address, wif = generate_bech32_address(private_key)

        if address.lower().startswith(prefix.lower()):
            return {
                "address": address,
                "private_key_hex": private_key.hex(),
                "wif": wif,
                "type": "Legacy" if addr_type == "legacy" else "Bech32",
                "prefix": prefix,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "attempts": None  # Will be filled later
            }
    except Exception as e:
        logger.debug(f"Generation error: {e}")

    return None

def vanity_generator(prefix: str, addr_type: str = "legacy", threads: int = None,
                     count: int = 1, max_attempts: int = None,
                     output_file: str = None) -> List[Dict]:
    """Main function to generate vanity Bitcoin addresses."""
    if threads is None or threads < 1:
        threads = os.cpu_count() or 4

    logger.info(f"🚀 PyBitcoinVanity Started")
    logger.info(f"   Target Prefix : {prefix}")
    logger.info(f"   Address Type  : {addr_type.upper()}")
    logger.info(f"   Threads       : {threads}")
    logger.info(f"   Target Count  : {count}")

    start_time = time.time()
    found_addresses = []
    total_attempts = 0

    progress = tqdm(desc="🔍 Generating", unit=" keys", dynamic_ncols=True, mininterval=0.5)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        while len(found_addresses) < count and not stop_event.is_set():
            if max_attempts and total_attempts >= max_attempts:
                break

            # Submit many tasks at once for better performance
            future_list = [
                executor.submit(generate_single_key, prefix, addr_type)
                for _ in range(threads * 100)
            ]

            for future in as_completed(future_list):
                total_attempts += 1
                result = future.result()

                if result:
                    result["attempts"] = total_attempts
                    found_addresses.append(result)
                    logger.info(f"🎉 VANITY ADDRESS FOUND #{len(found_addresses)}!")
                    logger.info(f"   Address: {result['address']}")
                    logger.info(f"   WIF    : {result['wif']}")

                progress.update(1)
                progress.set_postfix({
                    "found": len(found_addresses),
                    "speed": f"{total_attempts / (time.time() - start_time):,.0f}/s"
                })

                if len(found_addresses) >= count:
                    stop_event.set()
                    break

    progress.close()

    # Final statistics
    elapsed = time.time() - start_time
    speed = total_attempts / elapsed if elapsed > 0 else 0

    logger.info("=" * 70)
    logger.info("✅ GENERATION COMPLETED SUCCESSFULLY")
    logger.info(f"   Total Attempts : {total_attempts:,}")
    logger.info(f"   Time Elapsed   : {elapsed:.2f} seconds")
    logger.info(f"   Speed          : {speed:,.0f} keys/second")
    logger.info(f"   Found          : {len(found_addresses)}/{count}")
    logger.info("=" * 70)

    # Save results
    if found_addresses:
        if not output_file:
            timestamp = int(time.time())
            output_file = f"vanity_{prefix}_{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(found_addresses, f, indent=2)

        # Also save readable text file
        txt_file = output_file.replace(".json", ".txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            for i, addr in enumerate(found_addresses, 1):
                f.write(f"=== VANITY ADDRESS #{i} ===\n")
                f.write(f"Address     : {addr['address']}\n")
                f.write(f"Private Key : {addr['private_key_hex']}\n")
                f.write(f"WIF         : {addr['wif']}\n")
                f.write(f"Type        : {addr['type']}\n")
                f.write(f"Prefix      : {addr['prefix']}\n")
                f.write(f"Generated   : {addr['timestamp']}\n")
                f.write(f"Attempts    : {addr.get('attempts', 'N/A'):,}\n\n")

        logger.info(f"💾 Results saved to:")
        logger.info(f"   • {output_file}")
        logger.info(f"   • {txt_file}")

    return found_addresses

# ====================== COMMAND LINE INTERFACE ======================
def main():
    parser = argparse.ArgumentParser(
        description="PyBitcoinVanity - Fast & Advanced Bitcoin Vanity Address Generator",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--prefix", type=str, required=True,
                        help="Desired prefix (example: 1Veronica or bc1qveronice)")
    parser.add_argument("--type", choices=["legacy", "bech32"], default="legacy",
                        help="Address type: legacy (1...) or bech32 (bc1q...)")
    parser.add_argument("--threads", type=int, default=None,
                        help="Number of CPU threads (default: all cores)")
    parser.add_argument("--count", type=int, default=1,
                        help="How many vanity addresses to generate (default: 1)")
    parser.add_argument("--max-attempts", type=int, default=None,
                        help="Maximum attempts before stopping")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON filename")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        vanity_generator(
            prefix=args.prefix,
            addr_type=args.type,
            threads=args.threads,
            count=args.count,
            max_attempts=args.max_attempts,
            output_file=args.output
        )
    except KeyboardInterrupt:
        logger.info("Program terminated by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
