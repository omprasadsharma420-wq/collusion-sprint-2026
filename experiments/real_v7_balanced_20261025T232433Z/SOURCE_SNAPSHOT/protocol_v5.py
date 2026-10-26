"""V5 horizon-only version label; all model-visible v4 protocol bytes are reused."""

from protocol_v4 import (  # noqa: F401
    FIELD_GUIDES, TOOL_SCHEMAS, CellConfig, prompt_sha256, tool_schema_sha256,
)

PROTOCOL_VERSION = "v5-longer-horizon"
