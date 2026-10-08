"""Typed errors for the NMV integration boundary.

Each carries an HTTP status so the router can map it to a clean JSON response
without leaking internals. None of these ever carry a token/secret in their
message.
"""
from __future__ import annotations


class NmvIntegrationError(Exception):
    """Base. status_code maps to the HTTP response the router returns."""

    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class StoreNotConfigured(NmvIntegrationError):
    """The requested store_code is not a provisioned platform store."""

    status_code = 404


class StoreAccessDenied(NmvIntegrationError):
    """The calling device is not authorized for this store_code."""

    status_code = 403


class UnknownEntity(NmvIntegrationError):
    """A downlink entity / uplink table name that this boundary does not serve."""

    status_code = 400


class MalformedPayload(NmvIntegrationError):
    """The request body failed validation beyond what pydantic can express."""

    status_code = 422
