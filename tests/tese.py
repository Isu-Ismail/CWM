from datetime import datetime,timezone

def _now_iso():
    return datetime.now(timezone.utc).isoformat()
