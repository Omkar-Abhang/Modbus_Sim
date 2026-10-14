"""JSON file persistence for templates and devices (data/templates.json, data/devices.json)."""
import json
import os
import threading
import time

from loguru import logger

from src.config import DATA_DIR


class JsonStore:
    """List of dict items with integer ids, kept in memory and saved atomically on every change."""

    def __init__(self, filename):
        self.path = os.path.join(DATA_DIR, filename)
        self.lock = threading.RLock()
        self.items = {}
        self.next_id = 1
        self._load()

    def _load(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
            self.items = {int(i["id"]): i for i in data.get("items", [])}
            self.next_id = max([data.get("next_id", 1)] + [i + 1 for i in self.items])
        except Exception as e:
            # keep a copy of the broken file instead of overwriting it
            backup = f"{self.path}.broken-{int(time.time())}"
            os.replace(self.path, backup)
            logger.error(f"Could not read {self.path} ({e}); moved to {backup}")

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"next_id": self.next_id, "items": list(self.items.values())}, f, indent=1)
        os.replace(tmp, self.path)

    def all(self):
        with self.lock:
            return list(self.items.values())

    def get(self, item_id):
        with self.lock:
            return self.items.get(int(item_id))

    def add(self, item):
        with self.lock:
            item = dict(item, id=self.next_id)
            self.items[item["id"]] = item
            self.next_id += 1
            self._save()
            return item

    def put(self, item_id, item):
        with self.lock:
            item = dict(item, id=int(item_id))
            self.items[item["id"]] = item
            self._save()
            return item

    def delete(self, item_id):
        with self.lock:
            item = self.items.pop(int(item_id), None)
            if item is not None:
                self._save()
            return item


templates = JsonStore("templates.json")
devices = JsonStore("devices.json")
