"""Helpers shared by the static scanners: line-numbered matching and redacted evidence."""

import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.secret_redactor import redact

SNIPPET_LENGTH = 80
MAX_EVIDENCE = 5
SQL_EXTENSIONS = (".sql", ".pks", ".pkb", ".pls", ".plb", ".prc", ".fnc", ".trg")
CODE_EXTENSIONS = (".py", ".java", ".kt", ".scala", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".cs", ".rb", ".php")
SQL_KEYWORDS = re.compile(r"(?i)\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|MERGE\s+INTO|CREATE\s+(OR\s+REPLACE\s+)?\w+)\b")


def evidence(path: str, line_number: int, line: str) -> str:
    """'path:line snippet' with secrets masked."""
    snippet = redact(line.strip())[:SNIPPET_LENGTH]
    return f"{path}:{line_number} {snippet}"


def is_sql_file(source: SourceFile) -> bool:
    return source.path.lower().endswith(SQL_EXTENSIONS)


def is_code_file(source: SourceFile) -> bool:
    return source.path.lower().endswith(CODE_EXTENSIONS)


def base_name(source: SourceFile) -> str:
    return PurePosixPath(source.path).name


def matching_lines(source: SourceFile, pattern: re.Pattern[str]) -> Iterator[tuple[int, str, re.Match[str]]]:
    """(1-based line number, line, match) for every line that matches."""
    for number, line in enumerate(source.lines, start=1):
        found = pattern.search(line)
        if found:
            yield number, line, found


def sql_lines(source: SourceFile) -> Iterator[tuple[int, str]]:
    """Lines that carry SQL: every line of a SQL file, SQL-keyword lines in code files."""
    if is_sql_file(source):
        yield from enumerate(source.lines, start=1)
    elif is_code_file(source):
        for number, line in enumerate(source.lines, start=1):
            if SQL_KEYWORDS.search(line):
                yield number, line


def add_evidence(collected: list[str], item: str) -> None:
    """Keep at most MAX_EVIDENCE distinct items."""
    if item not in collected and len(collected) < MAX_EVIDENCE:
        collected.append(item)
