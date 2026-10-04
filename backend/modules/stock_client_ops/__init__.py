"""Stock Client fleet management: releases, authorized per-store rollouts,
installation registry + rich heartbeat, and secure (sha256 + Ed25519) package
download for the on-store watchdog.

This is the richer sibling of ``modules.agent_ops`` (which fleet-manages the
store SYNC agent). Here the managed thing is the Electron Stock Client, which
needs a release-vs-rollout split, an explicit authorization gate and per-store
rollout status - things agent_ops' single ``is_current`` flag can't express.
The on-store watchdog executable that consumes these endpoints is a separate
(Milestone 2) deliverable; this module defines the full state model + contract.
"""
