from cut import Cut
from snapshot import Snapshot
from verify import verify_log, VerificationError


class ReplayIntegrityError(Exception):
    pass


def replay(events):
    try:
        verify_log(events)
    except VerificationError as e:
        raise ReplayIntegrityError(str(e)) from e

    cuts = {}

    for event in events:

        etype = event["type"]
        payload = event["payload"]

        if etype == "CREATE_CUT":
            cut = Cut(
                id=payload["id"],
                start=payload["start"],
                end=payload["end"]
            )
            cuts[cut.id] = cut

        elif etype == "REMOVE_CUT":
            cut_id = payload["id"]
            if cut_id in cuts:
                del cuts[cut_id]

    return Snapshot(cuts)
