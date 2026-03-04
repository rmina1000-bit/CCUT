from types import MappingProxyType

class Projection:

    def __init__(self):
        self._cuts = {}
        self._version = -1

    def reset(self):
        self._cuts = {}
        self._version = -1

    def apply(self, event):
        etype = event["type"]
        payload = event["payload"]

        if etype == "CREATE_CUT":
            self._cuts[payload["id"]] = {
                "start": payload["start"],
                "end": payload["end"]
            }

        elif etype == "REMOVE_CUT":
            self._cuts.pop(payload["id"], None)

        self._version = event["seq"]

    def rebuild(self, events):
        self.reset()
        for e in events:
            self.apply(e)

    def get_cut(self, cut_id):
        return self._cuts.get(cut_id)

    def get_all(self):
        return MappingProxyType(self._cuts)

    def version(self):
        return self._version
