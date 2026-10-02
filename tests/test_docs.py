"""Public documentation must work in a clean checkout and remain English."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
INDEXES = {ROOT / path for path in ("README.md", "paper/README.md", "runs/README.md")}
HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]")
FENCES = re.compile(r"^(`{3,}|~{3,}).*?^\1\s*$", re.MULTILINE | re.DOTALL)
LINKS = re.compile(r"\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def public_files() -> set[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True,
    )
    return {ROOT / name.decode() for name in result.stdout.split(b"\0")
            if name and (ROOT / name.decode()).is_file()}


def prose(text: str) -> str:
    return re.sub(r"`[^`\n]*`", "", FENCES.sub("", text))


def heading_anchors(text: str) -> set[str]:
    counts: Counter[str] = Counter()
    anchors = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", FENCES.sub("", text), re.MULTILINE):
        heading = re.sub(r"\[([^]]*)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        anchors.add(slug + (f"-{counts[slug]}" if counts[slug] else ""))
        counts[slug] += 1
    return anchors


def documentation(files: set[Path]) -> list[Path]:
    return sorted(path for path in files if path.suffix == ".md"
                  and (path.is_relative_to(ROOT / "docs") or path in INDEXES))


def test_public_docs_are_english_and_exclude_local_archives():
    files = public_files()
    docs = documentation(files)
    assert docs
    archives = [str(path.relative_to(ROOT)) for path in docs
                if path.name.endswith((".zh-tw.md", ".shadow.md"))]
    non_english = [str(path.relative_to(ROOT)) for path in docs if HAN.search(path.read_text())]
    assert not archives, f"Local archives entered public documentation: {archives}"
    assert not non_english, f"Translate public documentation into English: {non_english}"


def test_public_documentation_links_resolve_to_checkout_files():
    files = public_files()
    failures = []
    for doc in documentation(files):
        for link in LINKS.findall(prose(doc.read_text())):
            parsed = urlsplit(link.strip("<>"))
            if parsed.scheme or parsed.netloc:
                continue
            target = (doc.parent / unquote(parsed.path)).resolve() if parsed.path else doc
            available = target in files or (target.is_dir() and any(path.is_relative_to(target) for path in files))
            if not available:
                failures.append(f"{doc.relative_to(ROOT)}: {link} is not public")
            elif parsed.fragment and target.suffix == ".md":
                if unquote(parsed.fragment) not in heading_anchors(target.read_text()):
                    failures.append(f"{doc.relative_to(ROOT)}: {link} has no matching heading")
    assert not failures, "\n".join(failures)
