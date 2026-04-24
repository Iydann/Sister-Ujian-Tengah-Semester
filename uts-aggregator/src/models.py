from pydantic import BaseModel
from typing import Dict
from datetime import datetime

class Event(BaseModel):
    topic: str
    event_id: str
    timestamp: datetime
    source: str
    payload: Dict