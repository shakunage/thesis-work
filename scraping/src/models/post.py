from datetime import datetime
from pydantic import BaseModel, HttpUrl

class Post(BaseModel):
    id: str
    author_id: str
    message: str
    date_time: datetime
    engagement: str = "N/A"
    forum: str
    url: HttpUrl
    company_name: str
    ticker: str
