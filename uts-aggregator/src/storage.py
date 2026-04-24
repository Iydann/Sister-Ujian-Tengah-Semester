from collections import defaultdict

class EventStorage:
    def __init__(self):
        self.events = defaultdict(list)

    def add(self, event):
        self.events[event.topic].append(event)

    def get_by_topic(self, topic):
        return self.events.get(topic, [])