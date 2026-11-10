"""
Principal propagation for SAP Datasphere (SAML bearer assertion via BTP).

Implements the flow from "MCP server for SAP Datasphere: access data as the
logged-in user with principal propagation" (SAP Community, ba-p/14515568):

  1. The MCP client logs the user in at XSUAA and sends the access token as
     ``Authorization: Bearer`` to this server (see PrincipalPropagationMiddleware).
  2. XsuaaTokenValidator verifies signature, issuer, audience, expiry, the user
     identifier claim and the required IAS group (default ``sac``).
  3. DestinationTokenProvider calls the BTP Destination service with its own
     service token plus the user's token (``X-user-token``). The destination
     (type OAuth2SAMLBearerAssertion) builds the signed SAML assertion and
     returns a Datasphere token that carries *that user's* permissions.

This server holds no signing key and does no SAML itself.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import quote

import aiohttp

from auth.user_context import UserContext, current_user

logger = logging.getLogger(__name__)

_EXPIRY_MARGIN = 60  # seconds: refresh a token shortly before it expires


class PrincipalPropagationError(Exception):
    """Base class for principal propagation failures."""


class TokenValidationError(PrincipalPropagationError):
    """The caller's XSUAA token is missing, invalid or not authorized (HTTP 401)."""


class MissingGroupError(TokenValidationError):
    """Token is valid but lacks the required group (HTTP 403)."""


class UserContextMissingError(PrincipalPropagationError):
    """A Datasphere call was attempted without an authenticated user."""


class DestinationError(PrincipalPropagationError):
    """The Destination service did not return a usable Datasphere token."""


@dataclass(frozen=True)
class PrincipalPropagationConfig:
    xsuaa_url: str                # XSUAA service key "url"
    xsuaa_client_id: str          # XSUAA service key "clientid" (expected audience)
    destination_url: str          # Destination service key "url" (token endpoint host)
    destination_uri: str          # Destination service key "uri" (configuration API)
    destination_client_id: str
    destination_client_secret: str = ""
    destination_name: str = "Datasphere_Token_Exchange_MCP"
    required_group: str = "sac"   # "" disables the group check
    user_claim: str = "user_name"  # must match the destination's userIdSource

    @classmethod
    def from_env(cls) -> "PrincipalPropagationConfig":
        """Build the config from environment variables.

        On Cloud Foundry the XSUAA and Destination credentials come from the
        bound service instances (VCAP_SERVICES), so no secret has to be set
        by hand. Explicit environment variables always take precedence.
        """
        vcap = _credentials_from_vcap()
        required = {
            "XSUAA_URL": ("xsuaa_url", vcap.get("xsuaa", {}).get("url")),
            "XSUAA_CLIENT_ID": ("xsuaa_client_id", vcap.get("xsuaa", {}).get("clientid")),
            "DESTINATION_SERVICE_URL": ("destination_url", vcap.get("destination", {}).get("url")),
            "DESTINATION_SERVICE_URI": ("destination_uri", vcap.get("destination", {}).get("uri")),
            "DESTINATION_CLIENT_ID": ("destination_client_id", vcap.get("destination", {}).get("clientid")),
            "DESTINATION_CLIENT_SECRET": ("destination_client_secret", vcap.get("destination", {}).get("clientsecret")),
        }
        values = {attr: (os.getenv(env) or fallback or "").strip()
                  for env, (attr, fallback) in required.items()}
        missing = [env for env, (attr, _) in required.items() if not values[attr]]
        if missing:
            raise ValueError(
                "Principal propagation is enabled but these variables are not set: "
                + ", ".join(missing)
                + ". Bind an xsuaa and a destination service instance (Cloud Foundry) or set them "
                "explicitly. See docs/OAUTH_SETUP.md (Part 2)."
            )
        return cls(
            **{k: v.rstrip("/") if k.endswith(("_url", "_uri")) else v for k, v in values.items()},
            destination_name=os.getenv("DESTINATION_NAME", cls.destination_name),
            required_group=os.getenv("PP_REQUIRED_GROUP", cls.required_group).strip(),
            user_claim=os.getenv("PP_USER_CLAIM", cls.user_claim).strip(),
        )


def _credentials_from_vcap() -> Dict[str, Dict[str, str]]:
    """Credentials of the bound ``xsuaa`` and ``destination`` instances, if any.

    Takes the first binding of each service label. Returns {} outside Cloud Foundry.
    """
    raw = os.getenv("VCAP_SERVICES")
    if not raw:
        return {}
    try:
        services = json.loads(raw)
    except ValueError:
        logger.warning("VCAP_SERVICES is not valid JSON; ignoring it")
        return {}
    found: Dict[str, Dict[str, str]] = {}
    for label in ("xsuaa", "destination"):
        instances = services.get(label) or []
        if instances:
            found[label] = instances[0].get("credentials") or {}
    return found


class XsuaaTokenValidator:
    """Verifies XSUAA access tokens against the subaccount's published keys."""

    def __init__(self, config: PrincipalPropagationConfig, jwks_client=None):
        self.config = config
        if jwks_client is None:
            import jwt  # PyJWT

            jwks_client = jwt.PyJWKClient(f"{config.xsuaa_url}/token_keys", cache_keys=True)
        self._jwks = jwks_client

    async def validate(self, token: str) -> UserContext:
        import jwt

        try:
            # PyJWKClient does blocking HTTP on a cache miss.
            key = await asyncio.to_thread(self._jwks.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                options={"verify_aud": False, "require": ["exp", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenValidationError(f"invalid token: {exc}") from exc
        except Exception as exc:  # JWKS fetch failure etc.: fail closed
            raise TokenValidationError(f"token could not be verified: {exc}") from exc

        issuer = str(claims.get("iss", ""))
        if not issuer.startswith(self.config.xsuaa_url):
            raise TokenValidationError("token was not issued by the configured XSUAA")

        audience = claims.get("aud") or []
        if isinstance(audience, str):
            audience = [audience]
        if self.config.xsuaa_client_id not in audience and claims.get("cid") != self.config.xsuaa_client_id:
            raise TokenValidationError("token is not intended for this application")

        user_id = claims.get(self.config.user_claim)
        if not user_id or not isinstance(user_id, str):
            raise TokenValidationError(f"token has no '{self.config.user_claim}' claim")

        groups = tuple(
            (claims.get("xs.system.attributes") or {}).get("xs.saml.groups") or ()
        )
        if self.config.required_group and self.config.required_group not in groups:
            # Datasphere would reject the assertion anyway (401); fail early and clearly.
            raise MissingGroupError(
                f"user lacks required group '{self.config.required_group}' (see IAS attribute Groups)"
            )

        return UserContext(
            user_id=user_id,
            user_token=token,
            groups=groups,
            expires_at=float(claims["exp"]),
        )


class DestinationTokenProvider:
    """Exchanges a user's XSUAA token for a Datasphere token via the Destination service."""

    def __init__(self, config: PrincipalPropagationConfig,
                 session: Optional[aiohttp.ClientSession] = None):
        self.config = config
        self._session = session
        self._service_token: Optional[Tuple[str, float]] = None
        self._service_lock = asyncio.Lock()
        self._user_tokens: Dict[str, Tuple[str, float]] = {}
        self._user_locks: Dict[str, asyncio.Lock] = {}

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_service_token(self) -> str:
        async with self._service_lock:
            if self._service_token and self._service_token[1] > time.time() + _EXPIRY_MARGIN:
                return self._service_token[0]
            # client_secret_post: BTP client IDs contain '!' and '|', which break
            # when URL-encoded for HTTP Basic auth (see blog, step 13).
            async with self._http().post(
                f"{self.config.destination_url}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.destination_client_id,
                    "client_secret": self.config.destination_client_secret,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    raise DestinationError(f"Destination service token request failed (HTTP {resp.status})")
                body = await resp.json()
            token = body["access_token"]
            self._service_token = (token, time.time() + int(body.get("expires_in", 300)))
            return token

    def invalidate(self, user: UserContext):
        self._user_tokens.pop(user.user_id.lower(), None)

    async def get_datasphere_token(self, user: Optional[UserContext] = None) -> str:
        """Return an ``Authorization`` header value ("Bearer <token>") for this user."""
        user = user or current_user.get()
        if user is None:
            raise UserContextMissingError(
                "No authenticated user for this request. In principal-propagation mode every "
                "call must carry the user's XSUAA token; the technical-user fallback is disabled."
            )
        key = user.user_id.lower()
        lock = self._user_locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._user_tokens.get(key)
            if cached and cached[1] > time.time() + _EXPIRY_MARGIN:
                return cached[0]
            header, ttl = await self._fetch(user)
            # Never cache beyond the lifetime of the user's own login.
            expires = min(time.time() + ttl, user.expires_at) if user.expires_at else time.time() + ttl
            self._user_tokens[key] = (header, expires)
            return header

    async def _fetch(self, user: UserContext) -> Tuple[str, int]:
        service_token = await self._get_service_token()
        url = (f"{self.config.destination_uri}/destination-configuration/v1/destinations/"
               f"{quote(self.config.destination_name, safe='')}")
        async with self._http().get(
            url,
            headers={"Authorization": f"Bearer {service_token}", "X-user-token": user.user_token},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                # Body may name the failure (e.g. "Cannot determine user to propagate");
                # it never contains the user's token.
                detail = (await resp.text())[:300]
                raise DestinationError(f"Destination lookup failed (HTTP {resp.status}): {detail}")
            body = await resp.json()

        tokens = body.get("authTokens") or []
        if not tokens:
            raise DestinationError("Destination returned no authTokens (check destination type OAuth2SAMLBearerAssertion)")
        auth = tokens[0]
        if auth.get("error"):
            raise DestinationError(f"Token exchange at Datasphere failed: {auth['error']}")
        value = auth.get("value")
        if not value:
            raise DestinationError("Destination returned an empty token")
        try:
            ttl = int(auth.get("expires_in") or 300)
        except (TypeError, ValueError):
            ttl = 300
        return f"{auth.get('type') or 'Bearer'} {value}", ttl


_WELL_KNOWN = "/.well-known/oauth-protected-resource"


def resolve_public_base_url(headers: Dict[str, str], scheme: str = "http") -> str:
    """The externally visible base URL of this server (no trailing slash).

    Order: MCP_PUBLIC_URL, then the first route of this Cloud Foundry app
    (VCAP_APPLICATION), then the request's own Host / X-Forwarded-Proto. The
    explicit settings come first because the Host header is client-controlled.
    """
    explicit = (os.getenv("MCP_PUBLIC_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    try:
        uris = json.loads(os.getenv("VCAP_APPLICATION") or "{}").get("application_uris") or []
    except ValueError:
        uris = []
    if uris:
        return f"https://{uris[0]}"
    proto = (headers.get("x-forwarded-proto") or scheme).split(",")[0].strip()
    return f"{proto}://{headers.get('host', 'localhost')}"


class PrincipalPropagationMiddleware:
    """ASGI middleware: authenticate the caller and bind the user to the request.

    Also serves OAuth Protected Resource Metadata (RFC 9728), which is how MCP
    clients discover which authorization server (XSUAA) to log in at. Unauthenticated
    responses point to it via ``WWW-Authenticate: ... resource_metadata="..."``.
    """

    def __init__(self, app, validator: XsuaaTokenValidator, exempt_prefixes=("/health",),
                 mcp_path: str = "/mcp", authorization_server: Optional[str] = None):
        self.app = app
        self.validator = validator
        self.exempt = tuple(exempt_prefixes)
        self.mcp_path = "/" + mcp_path.strip("/")
        self.authorization_server = (
            authorization_server or os.getenv("MCP_AUTHORIZATION_SERVER") or validator.config.xsuaa_url
        ).rstrip("/")

    def _metadata_paths(self):
        # RFC 9728 inserts the well-known segment before the resource path.
        return {_WELL_KNOWN, f"{_WELL_KNOWN}{self.mcp_path}"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        base = resolve_public_base_url(headers, scope.get("scheme", "http"))

        if scope["path"] in self._metadata_paths():
            return await self._metadata(scope, send, base)
        if scope["path"].startswith(self.exempt):
            return await self.app(scope, receive, send)

        auth = headers.get("authorization", "")
        if not auth.lower().startswith("bearer ") or not auth[7:].strip():
            return await self._reject(send, 401, "missing bearer token", base)
        try:
            user = await self.validator.validate(auth[7:].strip())
        except MissingGroupError as exc:
            return await self._reject(send, 403, str(exc), base, error="insufficient_scope")
        except TokenValidationError as exc:
            logger.warning("Rejected request: %s", exc)
            return await self._reject(send, 401, "invalid token", base, error="invalid_token")

        reset = current_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user.reset(reset)

    async def _metadata(self, scope, send, base: str):
        if scope["method"] not in ("GET", "HEAD"):
            return await self._respond(send, 405, {"error": "method not allowed"},
                                       [(b"allow", b"GET, HEAD")])
        body = {
            "resource": f"{base}{self.mcp_path}",
            "authorization_servers": [self.authorization_server],
            "bearer_methods_supported": ["header"],
            "resource_name": "SAP Datasphere MCP server",
        }
        await self._respond(send, 200, body, [(b"cache-control", b"public, max-age=300")],
                            head=scope["method"] == "HEAD")

    async def _reject(self, send, status: int, message: str, base: str, error: Optional[str] = None):
        challenge = 'Bearer realm="sap-datasphere-mcp"'
        if error:
            challenge += f', error="{error}"'
        challenge += f', resource_metadata="{base}{_WELL_KNOWN}{self.mcp_path}"'
        await self._respond(send, status, {"error": message},
                            [(b"www-authenticate", challenge.encode("latin-1"))])

    @staticmethod
    async def _respond(send, status: int, payload, extra_headers=(), head: bool = False):
        body = json.dumps(payload).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            *extra_headers,
        ]})
        await send({"type": "http.response.body", "body": b"" if head else body})
