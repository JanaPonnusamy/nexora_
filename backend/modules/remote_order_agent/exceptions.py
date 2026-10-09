"""Typed errors for the Remote Order Agent contract. The router turns these into
the agent's error envelope + HTTP status (docs/02 status-code table)."""
from __future__ import annotations


class AgentContractError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
