
from pydantic import BaseModel

class UserRequest(BaseModel):
    username: str
    full_name: str
    password: str | None = None

class UserStatusRequest(BaseModel):
    is_active: bool
