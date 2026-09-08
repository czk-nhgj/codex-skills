#!/usr/bin/env python3
"""Decrypt config.json.enc into config.json for the feishu-api skill.

Usage:
    python unlock.py
    python unlock.py -p <password>
    FEISHU_CONFIG_PASSWORD=<password> python unlock.py

Writes config.json next to this script. The password is NOT stored in this
repository; get it from the team admin and keep it private.
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SKILL_DIR = Path(__file__).resolve().parent
ENC_FILE = SKILL_DIR / "config.json.enc"
OUT_FILE = SKILL_DIR / "config.json"
KDF_PARAMS = {"n": 2**15, "r": 8, "p": 1}


def decrypt(password, payload):
    if payload.get("kdf") != "scrypt":
        raise ValueError("unsupported kdf: %s" % payload.get("kdf"))
    params = dict(KDF_PARAMS)
    params.update(payload.get("kdf_params") or {})
    salt = base64.b64decode(payload["salt"])
    nonce = base64.b64decode(payload["nonce"])
    ct = base64.b64decode(payload["ciphertext"])
    key = Scrypt(salt=salt, length=32, n=params["n"], r=params["r"], p=params["p"]).derive(
        password.encode("utf-8")
    )
    return AESGCM(key).decrypt(nonce, ct, None)


def main():
    if not ENC_FILE.exists():
        print("missing %s" % ENC_FILE, file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Unlock feishu-api config")
    parser.add_argument("-p", "--password", help="team password (omit to be prompted)")
    args = parser.parse_args()

    password = args.password or os.environ.get("FEISHU_CONFIG_PASSWORD")
    if not password:
        try:
            import getpass
            password = getpass.getpass("feishu-api team password: ")
        except Exception:
            password = input("feishu-api team password: ")
    if not password:
        print("no password provided", file=sys.stderr)
        return 1

    payload = json.loads(ENC_FILE.read_text(encoding="utf-8"))
    try:
        plain = decrypt(password, payload)
    except Exception as exc:
        print("decryption failed (wrong password?): %s" % exc, file=sys.stderr)
        return 1
    json.loads(plain.decode("utf-8"))  # validate JSON before writing
    OUT_FILE.write_bytes(plain)
    print("ok: wrote %s" % OUT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
