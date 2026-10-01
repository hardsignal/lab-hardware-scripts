"""Flush each timestamped event; callers own the stream lifetime."""
from datetime import datetime, timezone
import json


class JsonlLogger:
    def __init__(self, stream):
        self.stream = stream

    def record(self, event, **fields):
        self.stream.write(json.dumps({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': event, **fields}, allow_nan=False) + '\n')
        self.stream.flush()
