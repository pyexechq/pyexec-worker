"""
secret_decryptor.py — Decrypt secret envelopes received from the server.

Each envelope is:
  {
    "alg": "RSA-OAEP-AES-256-GCM",
    "enc_key":    "<base64>",   # AES key encrypted with this agent's RSA public key
    "nonce":      "<base64>",
    "tag":        "<base64>",
    "ciphertext": "<base64>"
  }

The agent uses its RSA private key to decrypt the AES key, then AES-GCM to
recover the plaintext secret value.
"""

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def _load_private_key(private_key_path: str):
    from cryptography.hazmat.primitives import serialization
    pem = Path(private_key_path).read_bytes()
    return serialization.load_pem_private_key(pem, password=None)


def decrypt_envelope(envelope: dict, private_key_path: str) -> str:
    """
    Decrypt a single secret envelope.  Returns plaintext string.
    Raises ValueError on failure.
    """
    if envelope.get('alg') != 'RSA-OAEP-AES-256-GCM':
        raise ValueError(f'Unsupported algorithm: {envelope.get("alg")}')

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    private_key = _load_private_key(private_key_path)

    # Decrypt AES key with RSA private key.
    aes_key = private_key.decrypt(
        _b64d(envelope['enc_key']),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    # AES-GCM decrypt (ciphertext || tag).
    nonce = _b64d(envelope['nonce'])
    tag = _b64d(envelope['tag'])
    ciphertext = _b64d(envelope['ciphertext'])
    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    return plaintext.decode()


def decrypt_env_bundle(bundle: dict, private_key_path: str) -> dict:
    """
    Given {name: envelope_dict} return {name: plaintext}.
    Secrets that fail to decrypt are excluded and a warning is logged.
    """
    result = {}
    for name, envelope in bundle.items():
        try:
            result[name] = decrypt_envelope(envelope, private_key_path)
        except Exception as exc:
            logger.warning('Could not decrypt secret "%s": %s', name, exc)
    return result
