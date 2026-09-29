"""JWT checks use generated keys and fabricated identities only."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from app.api.errors import AppError
from app.core.auth import SupabaseJWTVerifier
from app.core.config import Settings
from cryptography.hazmat.primitives.asymmetric import rsa

SUBJECT = UUID("00000000-0000-4000-8000-000000000001")


class FakeJwksClient:
    def __init__(self, public_key: rsa.RSAPublicKey) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self.public_key)


@pytest.fixture
def jwt_parts() -> tuple[SupabaseJWTVerifier, rsa.RSAPrivateKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(_env_file=None, supabase_url="https://demo.supabase.co")
    verifier = SupabaseJWTVerifier(settings, jwks_client=FakeJwksClient(private_key.public_key()))  # type: ignore[arg-type]
    return verifier, private_key


def _token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    claims = {
        "sub": str(SUBJECT),
        "iss": "https://demo.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "synthetic-key"})


def test_valid_and_invalid_jwts(jwt_parts: tuple[SupabaseJWTVerifier, rsa.RSAPrivateKey]) -> None:
    verifier, private_key = jwt_parts
    assert verifier.verify(_token(private_key)).id == SUBJECT
    invalid = (
        _token(private_key, exp=datetime.now(UTC) - timedelta(minutes=5)),
        _token(private_key, aud="wrong"),
        _token(private_key, iss="https://wrong.example/auth/v1"),
        _token(private_key, sub="not-a-uuid"),
        _token(private_key, is_anonymous=True),
        _token(private_key, sub=str(UUID(int=0))),
        _token(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        jwt.encode(
            {"sub": str(SUBJECT)},
            "synthetic-test-secret-with-32-characters",
            algorithm="HS256",
            headers={"kid": "x"},
        ),
    )
    for token in invalid:
        with pytest.raises(AppError) as failure:
            verifier.verify(token)
        assert failure.value.status_code == 401
