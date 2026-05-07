"""
Column-level encryption types for SQLAlchemy to protect PII data at rest.

Uses Fernet symmetric encryption from the cryptography library.
"""

from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import TypeDecorator, Text

from app.core.config import get_settings


class EncryptedString(TypeDecorator[str]):
    """
    SQLAlchemy column type that automatically encrypts/decrypts string values.
    
    Stores encrypted data as base64-encoded strings in a TEXT column.
    Uses Fernet symmetric encryption from cryptography library.
    
    Example:
        email: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    """

    impl = Text
    cache_ok = True

    def _get_fernet(self) -> Fernet | None:
        """Get or create Fernet cipher from settings."""
        settings = get_settings()
        key = getattr(settings, "PII_ENCRYPTION_KEY", None) or getattr(settings, "GITHUB_TOKEN_ENCRYPTION_KEY", None)
        if not key:
            return None
        try:
            # Ensure key is properly formatted for Fernet (32-byte base64-encoded)
            return Fernet(key.encode("utf-8"))
        except Exception:
            return None

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        """
        Encrypt value before saving to database.
        Called automatically by SQLAlchemy when binding parameters.
        """
        if value is None:
            return None
        
        if not isinstance(value, str):
            value = str(value)
        
        fernet = self._get_fernet()
        if fernet is None:
            # Fallback: store plaintext with marker if no encryption key configured
            # This allows development without encryption key but logs warning
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "PII_ENCRYPTION_KEY not configured. Storing PII field unencrypted. "
                "Configure PII_ENCRYPTION_KEY for production use."
            )
            return f"__UNENCRYPTED__:{value}"
        
        encrypted = fernet.encrypt(value.encode("utf-8"))
        return encrypted.decode("utf-8")

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        """
        Decrypt value when loading from database.
        Called automatically by SQLAlchemy when fetching results.
        """
        if value is None:
            return None
        
        if not isinstance(value, str):
            value = str(value)
        
        # Check for unencrypted marker (migration/compatibility)
        if value.startswith("__UNENCRYPTED__:"):
            return value[len("__UNENCRYPTED__:"):]
        
        fernet = self._get_fernet()
        if fernet is None:
            # No encryption key - can't decrypt
            # Return as-is if it doesn't look like encrypted data
            try:
                # Try to detect if this is encrypted data (Fernet uses base64)
                import base64
                base64.b64decode(value)
                # If it decodes as base64 but we can't decrypt, log error
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    "PII_ENCRYPTION_KEY not configured but encrypted data found in database. "
                    "Cannot decrypt PII field."
                )
                return None
            except Exception:
                # Not base64, probably plaintext
                return value
        
        try:
            decrypted = fernet.decrypt(value.encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                "Failed to decrypt PII field. Encryption key may have changed."
            )
            return None
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error decrypting PII field: {exc}")
            return None

    def compare_values(self, x: str | None, y: str | None) -> bool:
        """
        Compare two values for equality.
        Used by SQLAlchemy for change detection.
        """
        if x is None and y is None:
            return True
        if x is None or y is None:
            return False
        return x == y


class EncryptedSearchableString(TypeDecorator[str]):
    """
    Encrypted string that maintains a hash for searchable operations.
    
    Stores both encrypted value and deterministic hash (HMAC) to allow 
    searching by exact match while keeping data encrypted.
    
    Format: <hash>:<encrypted_data>
    
    WARNING: The hash reveals when two values are identical. Use only when
    exact-match search is required (e.g., email lookup during login).
    """

    impl = Text
    cache_ok = True

    def _get_fernet(self) -> Fernet | None:
        """Get or create Fernet cipher from settings."""
        settings = get_settings()
        key = getattr(settings, "PII_ENCRYPTION_KEY", None) or getattr(settings, "GITHUB_TOKEN_ENCRYPTION_KEY", None)
        if not key:
            return None
        try:
            return Fernet(key.encode("utf-8"))
        except Exception:
            return None

    def _compute_hash(self, value: str) -> str:
        """Compute deterministic hash for searchable value."""
        import hashlib
        import hmac
        
        settings = get_settings()
        key = getattr(settings, "PII_HMAC_KEY", None) or getattr(settings, "PII_ENCRYPTION_KEY", None) or getattr(settings, "GITHUB_TOKEN_ENCRYPTION_KEY", None) or ""
        
        # Use HMAC-SHA256 for deterministic hash
        h = hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)
        return h.hexdigest()

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        """Encrypt and hash value before saving."""
        if value is None:
            return None
        
        if not isinstance(value, str):
            value = str(value)
        
        # Normalize for consistent hashing (emails should be lowercase)
        value = value.lower().strip()
        
        fernet = self._get_fernet()
        if fernet is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "PII_ENCRYPTION_KEY not configured. Storing PII field unencrypted."
            )
            return f"__UNENCRYPTED__:{self._compute_hash(value)}:{value}"
        
        value_hash = self._compute_hash(value)
        encrypted = fernet.encrypt(value.encode("utf-8"))
        return f"{value_hash}:{encrypted.decode('utf-8')}"

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        """Decrypt value when loading from database."""
        if value is None:
            return None
        
        if not isinstance(value, str):
            value = str(value)
        
        # Handle unencrypted legacy data
        if value.startswith("__UNENCRYPTED__:"):
            parts = value.split(":", 2)
            if len(parts) >= 3:
                return parts[2]
            return None
        
        # Split hash and encrypted data
        if ":" not in value:
            # Plain text or corrupted
            return value
        
        _, encrypted = value.split(":", 1)
        
        fernet = self._get_fernet()
        if fernet is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("PII_ENCRYPTION_KEY not configured. Cannot decrypt.")
            return None
        
        try:
            decrypted = fernet.decrypt(encrypted.encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Failed to decrypt PII field. Key may have changed.")
            return None
        except Exception as exc:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error decrypting PII field: {exc}")
            return None

    def compute_search_hash(self, value: str) -> str:
        """
        Compute the search hash for a given value.
        Use this when querying by exact match.
        
        Example:
            email_hash = EncryptedSearchableString().compute_search_hash("user@example.com")
            query = select(User).where(User.email_hash == email_hash)
        """
        return self._compute_hash(value.lower().strip())
