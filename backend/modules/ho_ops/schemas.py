"""Request bodies for HO self-update orchestration."""
from typing import List, Optional

from pydantic import BaseModel, Field


class NodeTarget(BaseModel):
    url: Optional[str] = Field(None, description="peer HO base URL; null for this node")
    is_self: bool = Field(False, description="true to update the node serving this request")


class UpdateNodesRequest(BaseModel):
    targets: List[NodeTarget] = Field(default_factory=list)
