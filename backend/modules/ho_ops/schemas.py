"""Request bodies for HO self-update orchestration."""
from typing import List, Optional

from pydantic import BaseModel, Field


class NodeTarget(BaseModel):
    url: Optional[str] = Field(None, description="peer HO base URL; null for this node")
    is_self: bool = Field(False, description="true to update the node serving this request")


class SelfUpdateRequest(BaseModel):
    # For exe nodes: where to pull the published bundle from (the build node).
    source_url: Optional[str] = Field(None, description="base URL of the node that holds the release")


class UpdateNodesRequest(BaseModel):
    targets: List[NodeTarget] = Field(default_factory=list)
    source_url: Optional[str] = Field(None, description="build node base URL exe peers pull from")
