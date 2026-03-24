from shipyard.session.manager import SessionManager
from shipyard.config import ShipyardConfig


class RecoveryInfo:
    """Info about an interrupted session."""
    def __init__(self, session_id: str, last_instruction: str, events_after: int):
        self.session_id = session_id
        self.last_instruction = last_instruction
        self.events_after = events_after  # events logged after last instruction


def check_interrupted_sessions(config: ShipyardConfig) -> list[RecoveryInfo]:
    """
    Scan sessions directory for interrupted sessions.

    An interrupted session has an instruction event without a
    matching task_complete event after it.

    Returns list of RecoveryInfo for each interrupted session.
    """
    sm = SessionManager(config)
    interrupted = []

    for session_info in sm.list_sessions():
        if session_info["status"] == "interrupted":
            events = sm.get_session_events(session_info["session_id"])
            # Find the last instruction
            last_instruction = ""
            last_instruction_idx = 0
            for i, e in enumerate(events):
                if e.type == "instruction":
                    last_instruction = e.content
                    last_instruction_idx = i

            events_after = len(events) - last_instruction_idx - 1
            interrupted.append(RecoveryInfo(
                session_id=session_info["session_id"],
                last_instruction=last_instruction,
                events_after=events_after,
            ))

    return interrupted
