import uuid

from pydantic import BaseModel


class UpdateVersionStatusCommand(BaseModel):
    version_id: uuid.UUID
    expected_version: int
    new_status: str
