"""Mask secrets in repo text before it is logged, stored as evidence or sent to the LLM (CLAUDE.md rule 7).

Known token formats and credential assignments are replaced with <REDACTED>; long random-looking
strings in assignments are caught by a Shannon-entropy check.
"""

import math
import re

REDACTED = "<REDACTED>"
ENTROPY_THRESHOLD = 4.0
MIN_ENTROPY_LENGTH = 20

PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),  # Google API key
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),  # Slack
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),  # OpenAI-style keys
    re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{20,}"),  # Azure storage connection strings
    re.compile(r"(?i)SharedAccessSignature=[^;\s\"']+"),
]
# user:password@host in URLs / connection strings: keep the user and host, mask the password.
URL_PASSWORD = re.compile(r"(?P<prefix>[a-z][a-z0-9+.-]*://[^:/\s\"'@]+:)(?P<secret>[^@\s\"'/]+)(?P<suffix>@)", re.IGNORECASE)
# Oracle "user/password@" forms: jdbc:oracle:thin:user/password@..., sqlplus / CONNECT user/password@db.
ORACLE_PASSWORD = re.compile(
    r"(?P<prefix>(?i:jdbc:oracle:[a-z]+:[^/\s@\"']+/|\b(?:sqlplus|connect)\s+[\w$#]+/))(?P<secret>[^@\s\"']+)(?P<suffix>@)"
)
# key = value / key: value for credential-like names.
ASSIGNMENT = re.compile(
    r"(?P<prefix>(?i:\b[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential)[\w.-]*)\s*[:=]\s*[\"']?)"
    r"(?P<secret>[^\s\"',;]+)"
)
# Any long quoted / assigned token (checked by entropy).
LONG_VALUE = re.compile(r"(?P<prefix>[:=]\s*[\"']?)(?P<secret>[A-Za-z0-9+/_=-]{%d,})" % MIN_ENTROPY_LENGTH)
PLACEHOLDER = re.compile(r"(?i)^(\$\{.*\}|<.*>|changeme|change-me.*|example|xxx+|\*+|null|none|true|false|your[_-].*)$")


def shannon_entropy(text: str) -> float:
    """Bits per character."""
    if not text:
        return 0.0
    entropy = 0.0
    for character in set(text):
        probability = text.count(character) / len(text)
        entropy -= probability * math.log2(probability)
    return entropy


def mask_assignment(match: re.Match[str]) -> str:
    """Mask an assigned credential unless it is clearly a placeholder or a reference."""
    secret = match["secret"]
    if PLACEHOLDER.match(secret) or secret.startswith(("$", "{", "os.environ", "process.env")):
        return match.group(0)
    return match["prefix"] + REDACTED


def mask_high_entropy(match: re.Match[str]) -> str:
    """Mask long random-looking values."""
    if shannon_entropy(match["secret"]) >= ENTROPY_THRESHOLD:
        return match["prefix"] + REDACTED
    return match.group(0)


def redact(text: str) -> str:
    """Return text with secrets replaced by <REDACTED>."""
    for pattern in PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = URL_PASSWORD.sub(lambda match: match["prefix"] + REDACTED + match["suffix"], text)
    text = ORACLE_PASSWORD.sub(lambda match: match["prefix"] + REDACTED + match["suffix"], text)
    text = ASSIGNMENT.sub(mask_assignment, text)
    text = LONG_VALUE.sub(mask_high_entropy, text)
    return text
