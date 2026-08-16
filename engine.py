# Deterministic state machine + conflict resolution

class Engine:
    def __init__(self):
        self.state = {}

    def apply(self, event: dict) -> dict:
        """Apply an event to the current state deterministically."""
        raise NotImplementedError

    def resolve_conflict(self, a: dict, b: dict) -> dict:
        """Resolve conflicting events, returning the winning event."""
        raise NotImplementedError
