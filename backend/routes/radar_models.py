from pydantic import BaseModel, ConfigDict


class OfficialOpportunity(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    source: dict
    date_auth: str
    is_demo: bool
    promoteur: dict | None = None


class OfficialOpportunityList(BaseModel):
    model_config = ConfigDict(extra="allow")
    data_mode: str
    count: int
    page: int
    page_size: int
    opportunities: list[OfficialOpportunity]
    sync: dict
    stats: dict