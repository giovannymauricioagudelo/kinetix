"""Cifrado de las credenciales de Synapse con Fernet (AES-128-CBC + HMAC-SHA256), con rotación de llaves."""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional, Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from src.agents.common import dumps
from src.agents.security_agent.models import ConflictError

logger = logging.getLogger(__name__)

KEY_VARIABLE = "SYNAPSE_ENCRYPTION_KEY"


class CredentialCipher:
    """La primera llave cifra; todas descifran (SYNAPSE_ENCRYPTION_KEY=nueva,anterior para rotar)."""

    def __init__(self, keys: Sequence[str]) -> None:
        fernets = []
        for key in keys:
            try:
                fernets.append(Fernet(key.encode("ascii")))
            except (ValueError, TypeError, UnicodeEncodeError):
                raise ValueError(f"{KEY_VARIABLE} inválida: genera una con cryptography.fernet.Fernet.generate_key()") from None
        self._cipher: Optional[MultiFernet] = MultiFernet(fernets) if fernets else None

    @property
    def configured(self) -> bool:
        return self._cipher is not None

    def _require(self) -> MultiFernet:
        if self._cipher is None:
            raise ConflictError(f"Synapse no puede manejar credenciales: define {KEY_VARIABLE}")
        return self._cipher

    def encrypt(self, secret: Dict[str, str]) -> str:
        return self._require().encrypt(dumps(secret).encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> Dict[str, str]:
        try:
            return json.loads(self._require().decrypt(token.encode("ascii")))
        except (InvalidToken, ValueError):
            raise ConflictError(f"No se pudo descifrar la credencial: {KEY_VARIABLE} cambió sin conservar la llave anterior") from None

    def rotate(self, token: str) -> str:
        try:
            return self._require().rotate(token.encode("ascii")).decode("ascii")
        except InvalidToken:
            raise ConflictError("No se pudo rotar la credencial con las llaves configuradas") from None


def cipher_from_env(ephemeral_ok: bool = False) -> CredentialCipher:
    keys = [k.strip() for k in os.getenv(KEY_VARIABLE, "").split(",") if k.strip()]
    if not keys and ephemeral_ok:
        logger.warning("Synapse usa una llave de cifrado temporal: las credenciales no sobrevivirán un reinicio.")
        keys = [Fernet.generate_key().decode("ascii")]
    return CredentialCipher(keys)
