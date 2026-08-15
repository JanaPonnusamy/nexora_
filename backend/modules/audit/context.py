from __future__ import annotations

"""Request context extraction and client parsing for audit logging."""

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Optional
from fastapi import Request

from .models import ActorRole


def parse_device_info(user_agent: Optional[str]) -> Optional[str]:
    """Parse raw user-agent string into a clean 'Browser (OS)' format."""
    if not user_agent:
        return None

    ua = user_agent.strip()
    if not ua:
        return None

    # Detect OS (order matters: iPhone/iPad contains 'like Mac OS X')
    os_name = "Unknown OS"
    if "iPhone" in ua or "iPad" in ua or "iPod" in ua:
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        os_name = "macOS"
    elif "Windows NT 10.0" in ua or "Windows NT 11.0" in ua:
        os_name = "Windows"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Linux" in ua:
        os_name = "Linux"

    # Detect Browser / Client
    browser_name = "Unknown Client"
    if "Edg/" in ua or "Edge/" in ua:
        browser_name = "Edge"
    elif "Chrome/" in ua and "Chromium/" not in ua and "Edg/" not in ua:
        browser_name = "Chrome"
    elif "Firefox/" in ua:
        browser_name = "Firefox"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser_name = "Safari"
    elif "Electron/" in ua:
        browser_name = "Electron"
    elif "PostmanRuntime" in ua:
        browser_name = "Postman"
    elif "python-requests" in ua or "python-httpx" in ua or "aiohttp" in ua or "python" in ua.lower():
        browser_name = "Python Client"
    elif "curl" in ua.lower():
        browser_name = "cURL"

    return f"{browser_name} ({os_name})"


def resolve_local_country(ip_str: Optional[str]) -> Optional[str]:
    """Classify client IP locally. Returns None for private/local/unmappable addresses.
    
    IMPORTANT: This never makes third-party HTTP geolocation calls.
    Third-party network dependencies in audit log writes are strictly prohibited.
    """
    if not ip_str:
        return None

    try:
        ip_obj = ipaddress.ip_address(ip_str.strip())
        # Return None for private, loopback, link-local, reserved addresses
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
            return None
        # In an offline environment without an embedded MMDB binary, public IPs return None
        # rather than guessing or asserting a false geolocation.
        return None
    except ValueError:
        return None


@dataclass
class AuditContext:
    """Narrow contextual wrapper read by the audit writer."""
    actor_id: Optional[str] = None
    actor_role: ActorRole = ActorRole.SYSTEM
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    device: Optional[str] = None
    country: Optional[str] = None

    @classmethod
    def from_request(
        cls,
        request: Optional[Request],
        user: Optional[dict[str, Any]] = None,
        actor_override: Optional[dict[str, Any]] = None,
    ) -> "AuditContext":
        """Build an AuditContext from an active Request and optional user claims."""
        ip = None
        user_agent = None
        device = None
        country = None

        if request is not None:
            # Client IP
            if request.client:
                ip = request.client.host
            # User agent
            raw_ua = request.headers.get("user-agent", "")
            if raw_ua:
                user_agent = raw_ua[:512]
                device = parse_device_info(user_agent)
            country = resolve_local_country(ip)

        # Actor resolution
        actor_id = None
        actor_role = ActorRole.SYSTEM
        actor_email = None
        actor_name = None

        if user:
            actor_id = user.get("sub") or user.get("user_id")
            # Map role
            if user.get("is_platform_user") or any(
                r in {"SUPER_ADMIN", "PLATFORM_OWNER", "ADMIN"} for r in user.get("role_names", [])
            ):
                actor_role = ActorRole.ADMIN
            elif user.get("role_names"):
                actor_role = ActorRole.ADMIN  # Enterprise staff
            else:
                actor_role = ActorRole.CUSTOMER

            actor_email = user.get("email") or user.get("username")
            actor_name = user.get("full_name") or user.get("first_name") or user.get("username")

        # Explicit overrides (e.g. pre-auth actions or loaded user profile snapshot)
        if actor_override:
            if "actor_id" in actor_override:
                actor_id = actor_override["actor_id"]
            if "actor_role" in actor_override:
                role_val = actor_override["actor_role"]
                actor_role = role_val if isinstance(role_val, ActorRole) else ActorRole(role_val)
            if "actor_email" in actor_override:
                actor_email = actor_override["actor_email"]
            if "actor_name" in actor_override:
                actor_name = actor_override["actor_name"]

        return cls(
            actor_id=actor_id,
            actor_role=actor_role,
            actor_email=actor_email,
            actor_name=actor_name,
            ip=ip,
            user_agent=user_agent,
            device=device,
            country=country,
        )


def extract_request_context(request: Request) -> dict[str, Any]:
    """Helper to extract IP, user agent, device, and country from FastAPI request."""
    ip = request.client.host if request.client else None
    raw_ua = request.headers.get("user-agent", "")
    user_agent = raw_ua[:512] if raw_ua else None
    device = parse_device_info(user_agent)
    country = resolve_local_country(ip)
    return {
        "ip": ip,
        "user_agent": user_agent,
        "device": device,
        "country": country,
    }
