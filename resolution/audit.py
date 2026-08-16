# Audit trail manager
from datetime import datetime
from typing import List


class AuditTrail:
    def __init__(self):
        self._log: List[dict] = []

    def record(self, action: str, data: dict):
        self._log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "data": data,
        })

    def get_log(self) -> List[dict]:
        return list(self._log)
