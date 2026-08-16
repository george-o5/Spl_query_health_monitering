# Replay logic (clean isolated engine)
from engine import Engine


def replay(events: list) -> dict:
    """Replay a list of events through a clean engine instance."""
    engine = Engine()
    for event in events:
        engine.apply(event)
    return engine.state
