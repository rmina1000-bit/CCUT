import os
import json


class LogPersistence:

    def __init__(self, path):
        self._log_path = path
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def append_event(self, event_dict):
        line = json.dumps(event_dict, sort_keys=True, separators=(",", ":"))

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def load_events(self):
        if not os.path.exists(self._log_path):
            return []

        valid_lines = []
        last_valid_pos = 0

        with open(self._log_path, "r+", encoding="utf-8") as f:
            while True:
                pos = f.tell()
                line = f.readline()

                if not line:
                    break

                stripped = line.strip()
                if not stripped:
                    continue

                try:
                    event = json.loads(stripped)
                    valid_lines.append(event)
                    last_valid_pos = f.tell()
                except Exception:
                    break

            f.seek(last_valid_pos)
            f.truncate()

        return valid_lines
