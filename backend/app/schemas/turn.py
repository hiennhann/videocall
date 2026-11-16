from pydantic import BaseModel


class TurnCredentials(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None
    ttl: int = 0
