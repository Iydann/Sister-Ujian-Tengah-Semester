import asyncio
import logging
from datetime import datetime
from typing import List, Union

from fastapi import FastAPI

from src.consumer import Consumer
from src.dedup import DedupStore
from src.models import Event

logger = logging.getLogger("aggregator")
logging.basicConfig(level=logging.INFO)

def create_app() -> FastAPI:
    app = FastAPI()

    stats = {
        "received": 0,
        "unique_processed": 0,
        "duplicate_dropped": 0,
        "start_time": datetime.utcnow().isoformat()
    }

    @app.on_event("startup")
    async def startup_event():
        app.state.dedup = DedupStore()
        app.state.queue = asyncio.Queue()
        app.state.stats = stats
        app.state.consumer = Consumer(
            queue=app.state.queue,
            dedup_store=app.state.dedup,
            stats=app.state.stats,
            logger=logger,
        )
        app.state.consumer_task = asyncio.create_task(app.state.consumer.run())

    @app.on_event("shutdown")
    async def shutdown_event():
        app.state.consumer_task.cancel()
        try:
            await app.state.consumer_task
        except asyncio.CancelledError:
            pass
        app.state.dedup.close()

    @app.post("/publish")
    async def publish(events: Union[Event, List[Event]]):
        batch = events if isinstance(events, list) else [events]
        app.state.stats["received"] += len(batch)

        for event in batch:
            await app.state.queue.put(event)

        await app.state.queue.join()

        return {"status": "accepted", "count": len(batch)}

    @app.get("/events")
    def get_events(topic: str):
        return app.state.dedup.get_events(topic)

    @app.get("/stats")
    def get_stats():
        uptime = (datetime.utcnow() - datetime.fromisoformat(app.state.stats["start_time"])).total_seconds()

        return {
            **app.state.stats,
            "topics": app.state.dedup.get_topics(),
            "uptime": uptime
        }

    return app

app = create_app()