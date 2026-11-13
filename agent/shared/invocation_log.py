"""Labels each Claude call with its conversation, for Bedrock's invocation log"""

from shared.log_utils import StructuredLogger

LONGEST_LABEL = 256


def _plain(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char in "-_")


# Bedrock refuses a call whose label has other characters.
def _fits(session_id: str) -> bool:
    if not session_id or len(session_id) > LONGEST_LABEL:
        return False

    return all(_plain(char) for char in session_id)


def session_label(logger: StructuredLogger | None) -> dict:
    session_id = logger.session_id if logger else ""

    if not _fits(session_id):
        return {}

    return {"requestMetadata": {"session_id": session_id}}
