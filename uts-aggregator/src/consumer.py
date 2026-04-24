class Consumer:
    def __init__(self, queue, dedup_store, stats, logger):
        self.queue = queue
        self.dedup = dedup_store
        self.stats = stats
        self.logger = logger

    async def run(self):
        while True:
            event = await self.queue.get()
            try:
                if hasattr(event, "model_dump"):
                    event_dict = event.model_dump()
                elif hasattr(event, "dict"):
                    event_dict = event.dict()
                else:
                    event_dict = event

                ok = self.dedup.insert_event(event_dict)

                if ok:
                    self.stats["unique_processed"] += 1
                    self.logger.info("[PROCESSED] topic=%s event_id=%s", event_dict["topic"], event_dict["event_id"])
                else:
                    self.stats["duplicate_dropped"] += 1
                    self.logger.info("[DUPLICATE] topic=%s event_id=%s", event_dict["topic"], event_dict["event_id"])
            finally:
                self.queue.task_done()