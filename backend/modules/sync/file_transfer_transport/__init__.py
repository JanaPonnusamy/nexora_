"""HO-side (receiver) transport adapters for FILE_TRANSFER sync mode.

Mirrors store_agent/file_transfer/*_transport.py's layout/protocol on each
physical channel, implemented independently here because backend/ and
store_agent/ are separate deployables that never share a Python runtime in
production. See base.py for the interface both sides agree on.
"""
