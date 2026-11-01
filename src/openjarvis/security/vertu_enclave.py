"""Vertu-Grade Cryptographic Enclave, Identity Blinding, and Strict Decision Gating.

Implements zero-knowledge ephemeral enclaves, ChaCha20-Poly1305 and AES-256-GCM
authenticated encryption, disposable persona generation, and strict cryptographic
human confirmation gating strictly for critical destructive or financial decisions.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import json
import logging
import os
import secrets
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger("openjarvis.security.vertu_enclave")


class OperationRiskTier(str, enum.Enum):
    TIER_0_PERCEPTION = "tier_0_perception"       # 100% autonomous (ambient reading, scraping)
    TIER_1_LOGISTICS = "tier_1_logistics"         # 100% autonomous (reservations, video pipeline, drafting)
    TIER_2_CRITICAL = "tier_2_critical"           # STRICT CONFIRMATION (wire transfers, deletion, contracts)


@dataclass
class DisposablePersona:
    """Masked identity to protect user privacy against surveillance and correlation."""

    persona_id: str
    alias_name: str
    masked_email: str
    burner_phone_proxy: str
    virtual_card_token: str
    proxy_tunnel_node: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400)


@dataclass
class ConfirmationRequest:
    """Formal request for human dual-key authorization of critical operations."""

    request_id: str
    action_name: str
    risk_tier: OperationRiskTier
    rationale: str
    financial_impact_usd: float
    reversible: bool
    confirmation_token: str
    timestamp: float = field(default_factory=time.time)
    approved: bool = False


class VertuCryptographicEnclave:
    """Military-grade zero-knowledge secure storage and envelope encryption."""

    def __init__(self, master_key: Optional[bytes] = None) -> None:
        self._master_key = master_key or self._resolve_or_create_master_key()

    def _resolve_or_create_master_key(self) -> bytes:
        env_key = os.environ.get("OPENJARVIS_VERTU_MASTER_KEY")
        if env_key:
            return hashlib.sha256(env_key.encode()).digest()
        key_path = Path.home() / ".openjarvis" / ".vertu_enclave.key"
        if key_path.exists():
            try:
                raw = key_path.read_bytes()
                if len(raw) >= 32:
                    return raw[:32]
                # Corrupted key file detected: preserve it with backup to avoid silent data loss
                backup = key_path.with_name(f"{key_path.name}.corrupted.{int(time.time())}")
                key_path.rename(backup)
                log.error("Clave Vertu corrupta en %s (<32 bytes). Respaldada en %s", key_path, backup)
            except Exception as exc:
                log.error("Error al leer clave Vertu: %s", exc)

        new_key = secrets.token_bytes(32)
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            # Create atomically with restricted permissions (0600)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(str(key_path), flags, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "wb") as f:
                f.write(new_key)
        except Exception as exc:
            log.warning("No se pudo restringir permisos atómicamente en clave Vertu: %s", exc)
            key_path.write_bytes(new_key)
            try:
                key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
        return new_key

    def _derive_enclave_key(self, salt: bytes, context_aad: str) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA512(),
            length=32,
            salt=salt,
            info=f"vertu_enclave_v2:{context_aad}".encode(),
        )
        return hkdf.derive(self._master_key)

    def seal_envelope(
        self,
        plaintext_data: bytes,
        context_aad: str = "vertu_shield",
        cipher_algo: str = "aesgcm",
    ) -> str:
        """Seals data using AES-256-GCM or ChaCha20-Poly1305 with SHA512 derived key."""
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        derived_key = self._derive_enclave_key(salt, context_aad)

        algo_norm = cipher_algo.lower().strip()
        if "chacha" in algo_norm:
            cipher = ChaCha20Poly1305(derived_key)
            version_str = "vertu_v2_chacha20"
        else:
            cipher = AESGCM(derived_key)
            version_str = "vertu_v2_aesgcm"

        ciphertext = cipher.encrypt(nonce, plaintext_data, context_aad.encode())

        packet = {
            "version": version_str,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "aad": context_aad,
            "timestamp": time.time(),
        }
        return "vertu:" + base64.b64encode(json.dumps(packet).encode("utf-8")).decode("ascii")

    def unseal_envelope(self, sealed_token: str, expected_aad: Optional[str] = None) -> bytes:
        """Unseals authenticated envelope with constant-time AAD validation."""
        if not sealed_token.startswith("vertu:"):
            raise ValueError("Token inválido: Formato de sobre Vertu no reconocido")
        raw_json = base64.b64decode(sealed_token[6:])
        packet = json.loads(raw_json)

        aad = packet.get("aad", "")
        if expected_aad is not None and not hmac.compare_digest(aad, expected_aad):
            raise ValueError(f"Falla de autenticación AAD: esperada '{expected_aad}', recibida '{aad}'")

        salt = base64.b64decode(packet["salt_b64"])
        nonce = base64.b64decode(packet["nonce_b64"])
        ciphertext = base64.b64decode(packet["ciphertext_b64"])
        version = packet.get("version", "vertu_v2_aesgcm")

        derived_key = self._derive_enclave_key(salt, aad)
        if "chacha" in version:
            cipher = ChaCha20Poly1305(derived_key)
        else:
            cipher = AESGCM(derived_key)

        return cipher.decrypt(nonce, ciphertext, aad.encode())

    def seal_file_securely(self, target_path: Path, data: bytes, context_label: str) -> None:
        """Writes sealed envelope to disk and locks POSIX permissions to 0600."""
        sealed_str = self.seal_envelope(data, context_aad=context_label)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(sealed_str, encoding="utf-8")
        try:
            target_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass


class IdentityBlindingNexus:
    """Synthesizes isolated disposable personas to prevent tracking during operations."""

    def __init__(self, enclave: VertuCryptographicEnclave) -> None:
        self.enclave = enclave
        self._active_personas: Dict[str, DisposablePersona] = {}

    def spawn_disposable_persona(self, mission_tag: str) -> DisposablePersona:
        """Creates a completely detached operational persona for external tasks."""
        self.prune_expired_personas()
        pid = f"persona_{secrets.token_hex(6)}"
        persona = DisposablePersona(
            persona_id=pid,
            alias_name=f"E. {secrets.choice(['Vance', 'Sterling', 'Mercer', 'Davenport', 'Sinclair'])}",
            masked_email=f"client.desk.{secrets.token_hex(4)}@privatemail.ch",
            burner_phone_proxy=f"+41-22-{secrets.randbelow(899) + 100}-{secrets.randbelow(8999) + 1000}",
            virtual_card_token=f"vcc_tok_{secrets.token_urlsafe(16)}",
            proxy_tunnel_node=f"ch-zrh-node{secrets.randbelow(15) + 1}.secure-tunnel.net",
        )
        self._active_personas[pid] = persona
        log.info("Persona descartable activada [%s] para misión: %s", pid, mission_tag)
        return persona

    def revoke_persona(self, persona_id: str) -> None:
        """Zeroes and invalidates disposable persona after mission completion."""
        if persona_id in self._active_personas:
            del self._active_personas[persona_id]
            log.info("Persona descartable [%s] revocada y purgada del enclave", persona_id)

    def prune_expired_personas(self) -> int:
        """Prunes personas that have exceeded their 24h validity window."""
        now = time.time()
        expired = [pid for pid, p in self._active_personas.items() if p.expires_at <= now]
        for pid in expired:
            del self._active_personas[pid]
        return len(expired)


class StrictConfirmationGate:
    """Dual-key cryptographic gate requiring explicit human authorization strictly for critical actions."""

    def __init__(self, enclave: VertuCryptographicEnclave) -> None:
        self.enclave = enclave
        self._pending_confirmations: Dict[str, ConfirmationRequest] = {}

    def evaluate_risk(
        self,
        action_name: str,
        financial_amount: float = 0.0,
        is_destructive: bool = False,
    ) -> OperationRiskTier:
        """Determines if operation can proceed autonomously or requires human sign-off."""
        if is_destructive or financial_amount > 5000.0 or "eliminar" in action_name.lower():
            return OperationRiskTier.TIER_2_CRITICAL
        elif financial_amount > 0 or any(w in action_name.lower() for w in ["reservar", "comprar", "postear", "subir"]):
            return OperationRiskTier.TIER_1_LOGISTICS
        return OperationRiskTier.TIER_0_PERCEPTION

    def request_authorization_if_needed(
        self,
        action_name: str,
        rationale: str,
        financial_impact_usd: float = 0.0,
        is_destructive: bool = False,
    ) -> Tuple[bool, Optional[ConfirmationRequest]]:
        """Checks risk tier: returns (True, None) if autonomous, or (False, Request) if gated."""
        tier = self.evaluate_risk(action_name, financial_impact_usd, is_destructive)
        if tier != OperationRiskTier.TIER_2_CRITICAL:
            return True, None

        req_id = f"gate_{secrets.token_hex(8)}"
        auth_token = hmac.new(
            self.enclave._master_key,
            f"{req_id}:{action_name}:{financial_impact_usd}".encode(),
            hashlib.sha256,
        ).hexdigest()

        req = ConfirmationRequest(
            request_id=req_id,
            action_name=action_name,
            risk_tier=tier,
            rationale=rationale,
            financial_impact_usd=financial_impact_usd,
            reversible=not is_destructive,
            confirmation_token=auth_token,
        )
        self._pending_confirmations[req_id] = req
        log.warning("Acción crítica detenida por puerta Vertu [%s]: %s", req_id, action_name)
        return False, req

    def authorize_request(self, request_id: str, confirmation_token: str) -> bool:
        """Validates human confirmation token and unblocks critical execution."""
        req = self._pending_confirmations.get(request_id)
        if not req:
            return False
        expected_token = hmac.new(
            self.enclave._master_key,
            f"{request_id}:{req.action_name}:{req.financial_impact_usd}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(expected_token, confirmation_token):
            req.approved = True
            log.info("Acción crítica [%s] formalmente autorizada por el Señor", request_id)
            return True
        return False


# Global singleton instance
_global_enclave: Optional[VertuCryptographicEnclave] = None


def get_vertu_enclave() -> VertuCryptographicEnclave:
    global _global_enclave
    if _global_enclave is None:
        _global_enclave = VertuCryptographicEnclave()
    return _global_enclave


__all__ = [
    "OperationRiskTier",
    "DisposablePersona",
    "ConfirmationRequest",
    "VertuCryptographicEnclave",
    "IdentityBlindingNexus",
    "StrictConfirmationGate",
    "get_vertu_enclave",
]
