import time
from typing import Optional

import httpx
from jose import jwt
from jose.exceptions import JWTError

from Backend.config.env_loader import get_env_var

UMS_URL = get_env_var("UMS_URL").rstrip("/")
OPENID_CONFIG_URL = f"{UMS_URL}/.well-known/openid-configuration"
JWKS_CACHE_TTL_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 5.0

_cache = {"openid_config": None, "jwks": None, "jwks_fetched_at": 0.0}


async def _get_openid_config() -> dict:
    if _cache["openid_config"] is None:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(OPENID_CONFIG_URL)
            response.raise_for_status()
            _cache["openid_config"] = response.json()
    return _cache["openid_config"]


async def _get_jwks(force_refresh: bool = False) -> dict:
    is_stale = time.time() - _cache["jwks_fetched_at"] > JWKS_CACHE_TTL_SECONDS
    if _cache["jwks"] is None or force_refresh or is_stale:
        config = await _get_openid_config()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(config["jwks_uri"])
            response.raise_for_status()
            _cache["jwks"] = response.json()
            _cache["jwks_fetched_at"] = time.time()
    return _cache["jwks"]


async def _get_signing_key(kid: str) -> Optional[dict]:
    jwks = await _get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    # kid not found: JWKS may have rotated, refresh once and retry.
    jwks = await _get_jwks(force_refresh=True)
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def decode_access_token(token: str) -> Optional[dict]:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        return None

    kid = unverified_header.get("kid")
    if not kid:
        return None

    signing_key = await _get_signing_key(kid)
    if signing_key is None:
        return None

    config = await _get_openid_config()
    algorithms = config.get("id_token_signing_alg_values_supported", ["RS256"])

    try:
        return jwt.decode(
            token,
            signing_key,
            algorithms=algorithms,
            issuer=config["issuer"],
            options={"verify_aud": False},
        )
    except JWTError:
        return None
