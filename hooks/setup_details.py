import os
import hashlib
from cryptography.fernet import Fernet
import base64

DEFAULT_KEY = b"1toMVVmg7zuX8p74L7rlvljHw-dsLAdD0KvzlmxjZSs="
ENCRYPTED_SONAR = b"gAAAAABoyk25aRwPrw0MVSlI8A44vX8DvcZwyCifINkhQuT5zZN0dN-ZdCzXRP7P7yAyvlroqfz87RBVLxq-B2vrysUfvMYgR0MpHKk8hrLMfdJPURk_j1cbk38TKc-RFpIsbYpzOcqO"

def _generate_key() -> bytes:
    """Generate consistent Fernet key from machine-specific data."""
    seed = f"{os.getenv('COMPUTERNAME', 'default')}bcbsa_sonar_key"
    key_material = hashlib.sha256(seed.encode()).digest()
    return base64.urlsafe_b64encode(key_material)

def get_decrypted_tokens():
    # Use default key for existing encrypted token
    f = Fernet(DEFAULT_KEY)
    sonar_token = f.decrypt(ENCRYPTED_SONAR).decode()
    return {"SONAR_TOKEN": sonar_token}

def encrypt_token(token: str) -> str:
    """Encrypt a token for secure storage, return as string for JSON compatibility."""
    f = Fernet(_generate_key())
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a token for use."""
    f = Fernet(_generate_key())
    return f.decrypt(encrypted_token.encode()).decode()
