import hashlib
import json


def compute_event_hash(seq, event_type, payload, prev_hash):
    data = {
        "seq": seq,
        "type": event_type,
        "payload": payload,
        "prev_hash": prev_hash
    }

    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()
