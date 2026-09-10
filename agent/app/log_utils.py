"""Structured JSON logger for Bedrock agents with session context."""

import json
import logging
from datetime import UTC, datetime
from typing import Any


class StructuredLogger:
    """Structured JSON logger for Bedrock agents with session context."""

    def __init__(self, session_id: str, user_id: str, agent_name: str = "govuk-companion-agent"):
        self.logger = logging.getLogger(agent_name)
        self.session_id = session_id
        self.user_id = user_id
        self.agent_name = agent_name

        # Configure to output JSON to stdout
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)

    def log(self, level: str, message: str, **extra_fields: Any):
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "level": level,
            "message": message,
            **extra_fields,
        }
        log_fn = getattr(self.logger, level.lower(), self.logger.info)
        log_fn(json.dumps(log_entry))
