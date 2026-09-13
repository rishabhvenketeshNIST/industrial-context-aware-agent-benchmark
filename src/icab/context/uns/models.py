from pydantic import BaseModel, ConfigDict, Field


class UNSNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    canonical_id: str | None = None
