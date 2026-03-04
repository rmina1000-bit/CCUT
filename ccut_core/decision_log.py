import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from types import MappingProxyType
from event_registry import validate_event
from hash_util import compute_event_hash
from engine_meta import EngineMeta
from persistence import LogPersistence
from verify import verify_log
from cut_projection import Projection

class DecisionLog:
    def __init__(self, storage_path="storage/engine.log"):
        self._events = []
        self._seq = 0
        self._protected = False
        self._write_enabled = True
        self._protect_reason = None
        self._meta = EngineMeta()
        self._persistence = LogPersistence(storage_path)
        self._snapshot_path = "storage/engine.snapshot"
        self._snapshot_hash_path = "storage/engine.snapshot.hash"
        self._snapshot_threshold = 100
        self._projection = Projection()

        try:
            from observability.timeline import record_start
            record_start("REPLAY")
        except Exception:
            pass

        snapshot = None
        try:
            snapshot = self._load_snapshot()
        except Exception as e:
            self._protected = True
            self._write_enabled = False
            self._protect_reason = str(e)

        if snapshot and not self._protected:
            self._events = [
                MappingProxyType({
                    "seq": e["seq"],
                    "type": e["type"],
                    "payload": MappingProxyType(e["payload"]),
                    "prev_hash": e["prev_hash"],
                    "hash": e["hash"]
                })
                for e in snapshot["events"]
            ]
            self._seq = snapshot["last_seq"]
            self._projection.rebuild(self._events)
            self._write_recovery_report()
            try:
                from projection.projection_store import rebuild_projection
                rebuild_projection()
            except Exception:
                pass
            try:
                from observability.event_trace import log_event
                from observability.timeline import record_end
                from observability.snapshot import record_snapshot
                from observability.trace_buffer import flush_all
                log_event("REPLAY_COMPLETE", engine_seq=self._seq)
                record_end("REPLAY")
                record_snapshot(decision_count=len(self._events), engine_status="STABLE")
                flush_all()
            except Exception:
                pass

        elif not self._protected:
            loaded = self._persistence.load_events()

            if loaded:
                converted = []
                for raw in loaded:
                    event = MappingProxyType({
                        "seq": raw["seq"],
                        "type": raw["type"],
                        "payload": MappingProxyType(raw["payload"]),
                        "prev_hash": raw["prev_hash"],
                        "hash": raw["hash"]
                    })
                    converted.append(event)

                try:
                    verify_log(converted)
                    self._events = converted
                    self._seq = self._events[-1]["seq"]
                    self._projection.rebuild(self._events)
                    try:
                        from projection.projection_store import rebuild_projection
                        rebuild_projection()
                    except Exception:
                        pass
                    try:
                        from observability.event_trace import log_event
                        from observability.timeline import record_end
                        from observability.snapshot import record_snapshot
                        from observability.trace_buffer import flush_all
                        log_event("REPLAY_COMPLETE", engine_seq=self._seq)
                        record_end("REPLAY")
                        record_snapshot(decision_count=len(self._events), engine_status="STABLE")
                        flush_all()
                    except Exception:
                        pass
                except Exception as e:
                    self._protected = True
                    self._write_enabled = False
                    self._protect_reason = str(e)
                    self._events = []
                    self._seq = -1

                self._write_recovery_report()

            else:
                self._initialize_genesis()

        else:
            self._write_recovery_report()

    def _initialize_genesis(self):
        genesis_payload = self._meta.to_dict()
        genesis_hash = compute_event_hash(
            0,
            "GENESIS",
            genesis_payload,
            "NONE"
        )

        genesis_event_dict = {
            "seq": 0,
            "type": "GENESIS",
            "payload": genesis_payload,
            "prev_hash": "NONE",
            "hash": genesis_hash
        }

        self._persistence.append_event(genesis_event_dict)

        self._events.append(MappingProxyType({
            "seq": 0,
            "type": "GENESIS",
            "payload": MappingProxyType(genesis_payload),
            "prev_hash": "NONE",
            "hash": genesis_hash
        }))
        self._seq = 0

    def append(self, event_type: str, payload: dict):
        if self._protected or not self._write_enabled:
            raise RuntimeError("Engine in protected mode")

        validate_event(event_type, payload)

        next_seq = self._seq + 1
        prev_hash = self._events[-1]["hash"]
        frozen_payload = MappingProxyType(copy.deepcopy(payload))

        event_hash = compute_event_hash(
            next_seq,
            event_type,
            dict(frozen_payload),
            prev_hash
        )

        event = MappingProxyType({
            "seq": next_seq,
            "type": event_type,
            "payload": frozen_payload,
            "prev_hash": prev_hash,
            "hash": event_hash
        })

        self._persistence.append_event({
            "seq": next_seq,
            "type": event_type,
            "payload": dict(frozen_payload),
            "prev_hash": prev_hash,
            "hash": event_hash
        })

        self._events.append(event)
        self._seq = next_seq
        self._projection.apply(event)

        if len(self._events) >= self._snapshot_threshold:
            self._write_snapshot()

        try:
            from projection.projection_store import apply_event_to_projection
            apply_event_to_projection(event)
        except Exception:
            pass

        try:
            from observability.event_trace import log_event
            log_event("DECISION_APPEND", engine_seq=next_seq)
        except Exception:
            pass

    def get_next_seq(self):
        return self._seq + 1

    def get_event_count(self):
        return len(self._events)

    def get_events(self):
        return list(self._events)

    def _write_snapshot(self):
        data = {
            "last_seq": self._seq,
            "events": [
                {
                    "seq": e["seq"],
                    "type": e["type"],
                    "payload": dict(e["payload"]),
                    "prev_hash": e["prev_hash"],
                    "hash": e["hash"]
                }
                for e in self._events
            ]
        }

        serialized = json.dumps(data, separators=(",", ":"))
        snapshot_hash = hashlib.sha256(serialized.encode()).hexdigest()

        with open(self._snapshot_path, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())

        with open(self._snapshot_hash_path, "w", encoding="utf-8") as f:
            f.write(snapshot_hash)
            f.flush()
            os.fsync(f.fileno())

    def _load_snapshot(self):
        if not os.path.exists(self._snapshot_path):
            return None

        with open(self._snapshot_path, "r", encoding="utf-8") as f:
            content = f.read()

        with open(self._snapshot_hash_path, "r", encoding="utf-8") as f:
            expected_hash = f.read().strip()

        actual_hash = hashlib.sha256(content.encode()).hexdigest()

        if actual_hash != expected_hash:
            raise RuntimeError("Snapshot hash mismatch")

        return json.loads(content)

    def _write_recovery_report(self):
        report = {
            "event_count": len(self._events),
            "last_seq": self._seq,
            "protected": self._protected,
            "protect_reason": self._protect_reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with open("storage/recovery_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, separators=(",", ":"))

    def get_cut(self, cut_id):
        return self._projection.get_cut(cut_id)

    def get_all_cuts(self):
        return self._projection.get_all()

    def get_projection_version(self):
        return self._projection.version()

    def get_engine_status(self):
        return {
            "protected": self._protected,
            "write_enabled": self._write_enabled,
            "event_count": len(self._events),
            "last_seq": self._seq,
            "protect_reason": self._protect_reason
        }


def read_all_events(storage_path="storage/engine.log"):
    persistence = LogPersistence(storage_path)
    raw = persistence.load_events()
    return [
        MappingProxyType({
            "seq": e["seq"],
            "type": e["type"],
            "payload": MappingProxyType(e["payload"]),
            "prev_hash": e["prev_hash"],
            "hash": e["hash"]
        })
        for e in raw
    ]
