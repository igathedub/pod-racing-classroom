"""Pure, fail-closed selection of the bot observation wire format."""
import os


def configured_input_protocol(value: str | None = None) -> str:
    """Use the operator environment only when no explicit protocol is supplied."""
    if value is None:
        value = os.environ.get("POD_INPUT_PROTOCOL", "legacy")
    if not isinstance(value, str) or value not in ("legacy", "checkpoint-only"):
        raise ValueError("POD_INPUT_PROTOCOL must be 'legacy' or 'checkpoint-only'")
    return value
