# feeder_logger.py
import os
import csv
from datetime import datetime
import asyncio
import logging

LOG = logging.getLogger("feeder_logger")
LOG_DIR = "/home/sqna/cave/logs"

os.makedirs(LOG_DIR, exist_ok=True)


class FeederLogger:
    """
    Maintains a CSV with rows: hour_iso, seconds_on
    On each add(seconds) it updates the current hour row (appends if missing).
    Thread-safe via asyncio.Lock (used from asyncio tasks).
    """
    def __init__(self, filename="feeder_log.csv"):
        self.path = os.path.join(LOG_DIR, filename)
        self._lock = asyncio.Lock()
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["hour", "seconds_on"])

    async def add_seconds(self, seconds: int):
        hour_key = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat()
        async with self._lock:
            # read existing
            rows = []
            try:
                with open(self.path, newline="") as f:
                    reader = list(csv.reader(f))
                    if not reader:
                        rows = [["hour", "seconds_on"]]
                    else:
                        rows = reader
            except FileNotFoundError:
                rows = [["hour", "seconds_on"]]

            header = rows[0] if rows else ["hour", "seconds_on"]
            body = rows[1:] if len(rows) > 1 else []

            updated = False
            for r in body:
                if r[0] == hour_key:
                    r[1] = str(int(r[1]) + int(seconds))
                    updated = True
                    break
            if not updated:
                body.append([hour_key, str(int(seconds))])

            # write back (header + body)
            with open(self.path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(body)
            LOG.debug("Feeder log updated: %s += %s", hour_key, seconds)


class CsvLogger:
    """
    Maintains a CSV with rows: hour_iso, seconds_on
    On each add(seconds) it updates the current hour row (appends if missing).
    Thread-safe via asyncio.Lock (used from asyncio tasks).
    """
    def __init__(self, filename, head):  # head = ["hour", "seconds_on"]
        self.path = os.path.join(LOG_DIR, filename)
        self.head = head

        self._lock = asyncio.Lock()
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(head)

    async def update(self, hour_key, *args: float):
        async with self._lock:
            # read existing
            rows = []
            try:
                with open(self.path, newline="") as f:
                    reader = list(csv.reader(f))
                    if not reader:
                        rows = [self.head]
                    else:
                        rows = reader
            except FileNotFoundError:
                rows = [self.head]

            header = rows[0] if rows else self.head
            body = rows[1:] if len(rows) > 1 else []

            body.append([hour_key] + [str(a) for a in args])

            # write back (header + body)
            with open(self.path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(body)
            LOG.debug("Feeder log updated: %s += %s", hour_key, args)
