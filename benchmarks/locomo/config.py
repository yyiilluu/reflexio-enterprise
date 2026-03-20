"""Constants and configuration for the LoCoMo benchmark."""

# QA category mapping (from LoCoMo paper)
CATEGORY_MAP: dict[int, str] = {
    1: "multi-hop",
    2: "single-hop",
    3: "temporal",
    4: "open-domain",
    5: "adversarial",
}

CATEGORY_IDS: dict[str, int] = {v: k for k, v in CATEGORY_MAP.items()}

# Strategies
STRATEGIES = ["no_context", "reflexio"]
NON_REFLEXIO_STRATEGIES = ["no_context"]
REFLEXIO_STRATEGIES = ["reflexio"]

# Defaults
DEFAULT_MODEL = "minimax/MiniMax-M2.5"
DEFAULT_REFLEXIO_URL = "http://localhost:8081"
DEFAULT_TOP_K = 20
DEFAULT_SEARCH_THRESHOLD = 0.1

# Adversarial negative phrases (prediction should contain one of these)
ADVERSARIAL_NEGATIVE_PHRASES = [
    "no information",
    "not available",
    "don't have enough information",
    "do not have enough information",
    "cannot determine",
    "not mentioned",
    "no evidence",
    "not enough context",
    "unknown",
    "i'm not sure",
    "i am not sure",
    "not clear",
    "no data",
    "insufficient",
]
