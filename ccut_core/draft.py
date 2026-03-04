from replay import replay, ReplayIntegrityError
from snapshot import Snapshot
from event_registry import validate_event
from types import MappingProxyType
import copy


class Draft:
    def __init__(self, decision_log):
        self._decision_log = decision_log
        self._pending = []

    def stage(self, event_type: str, payload: dict):
        validate_event(event_type, payload)

        seq = self._decision_log.get_next_seq() + len(self._pending)

        frozen_payload = MappingProxyType(copy.deepcopy(payload))

        event = MappingProxyType({
            "seq": seq,
            "type": event_type,
            "payload": frozen_payload
        })

        self._pending.append(event)

    def commit(self):
        if not self._pending:
            return

        initial_count = self._decision_log.get_event_count()

        try:
            for event in self._pending:
                self._decision_log.append(
                    event["type"],
                    dict(event["payload"])
                )

        except Exception as e:
            current_count = self._decision_log.get_event_count()
            rollback_count = current_count - initial_count

            if rollback_count > 0:
                self._decision_log._events = \
                    self._decision_log._events[:initial_count]
                self._decision_log._seq = initial_count

            raise e

        final_count = self._decision_log.get_event_count()

        if final_count != initial_count + len(self._pending):
            raise RuntimeError("Commit integrity mismatch")

        self._pending = []

    def clear_pending(self):
        self._pending = []

    def get_current_snapshot(self):
        base_snapshot = replay(self._decision_log.get_events())
        base_state = base_snapshot.get_state()

        expected_seq = self._decision_log.get_next_seq()

        for event in self._pending:

            if event["seq"] != expected_seq:
                raise ReplayIntegrityError("Pending seq mismatch")

            expected_seq += 1

            etype = event["type"]
            payload = event["payload"]

            if etype == "CREATE_CUT":
                from cut import Cut
                cut = Cut(
                    id=payload["id"],
                    start=payload["start"],
                    end=payload["end"]
                )
                base_state[cut.id] = cut

            elif etype == "REMOVE_CUT":
                cut_id = payload["id"]
                if cut_id in base_state:
                    del base_state[cut_id]

        return Snapshot(base_state)
