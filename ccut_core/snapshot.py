import copy

class Snapshot:
    def __init__(self, cuts: dict):
        self._cuts = copy.deepcopy(cuts)

    def get_state(self):
        return copy.deepcopy(self._cuts)
