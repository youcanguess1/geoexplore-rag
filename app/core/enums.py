"""Shared state and compatibility enums.

The active geological graph uses ``RetrievalStrategy`` and ``QueryComplexity``.
Legacy category and tool enums remain only for inactive research utilities and
serialized compatibility; they are not part of the formal BM25 query path.
"""

from enum import Enum


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class IntentLabel(str, Enum):
    GREETING = "greeting"
    CHITCHAT = "chitchat"
    FAQ_POLICY = "faq_policy"
    OUT_OF_SCOPE = "out_of_scope"


class RetrievalStrategy(str, Enum):
    """Execution states retained for API response compatibility."""

    DIRECT = "direct"
    SINGLE = "single"
    MULTI = "multi"
    AGENT = "agent"
    REFUSE = "refuse"


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    SINGLE_HOP = "single_hop"
    MULTI_HOP = "multi_hop"
    TOOL_REQUIRED = "tool_required"
    OUT_OF_SCOPE = "out_of_scope"


class ToolRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"


class CompressionLevel(str, Enum):
    NONE = "none"
    SOFT_TRUNCATE = "soft_truncate"
    HARD_COMPRESS = "hard_compress"
    AUTO_COMPACT = "auto_compact"


class DocumentCategory(str, Enum):
    """Neutral classification retained for generic chunk compatibility."""

    GENERAL = "general"
