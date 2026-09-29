"""Verify Supabase Auth access tokens against this project's public JWKS."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientConnectionError, PyJWKClientError

from app.api.errors import AppError
from app.core.config import Settings

bearer = HTTPBearer(auto_error=False)
ALLOWED_ALGORITHMS = frozenset({"RS256", "ES256", "EdDSA"})


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID


class SupabaseJWTVerifier:
    def __init__(self, settings: Settings, jwks_client: PyJWKClient | None = None) -> None:
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is required for JWT verification")
        self.issuer = f"{settings.supabase_url}/auth/v1"
        self.audience = settings.supabase_jwt_audience
        self.jwks_client = jwks_client or PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            lifespan=settings.jwks_cache_seconds,
            timeout=5,
        )

    def verify(self, token: str) -> CurrentUser:
        if len(token) > 8192:
            raise AppError("invalid_token", "Invalid access token", 401)
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALLOWED_ALGORITHMS or not header.get("kid"):
                raise AppError("invalid_token", "Invalid access token", 401)
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[header["alg"]],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
                leeway=30,
            )
            user_id = UUID(str(claims["sub"]))
            if user_id.int == 0 or claims.get("is_anonymous") is True:
                raise ValueError("Anonymous or nil user")
            return CurrentUser(id=user_id)
        except PyJWKClientConnectionError as exc:
            raise AppError("auth_unavailable", "Authentication keys are unavailable", 503) from exc
        except (InvalidTokenError, PyJWKClientError, ValueError, KeyError, TypeError) as exc:
            raise AppError("invalid_token", "Invalid access token", 401) from exc


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AppError("authentication_required", "Bearer access token required", 401)
    verifier: SupabaseJWTVerifier | None = getattr(request.app.state, "jwt_verifier", None)
    if verifier is None:
        raise AppError("auth_not_configured", "Authentication is not configured", 503)
    return verifier.verify(credentials.credentials)
