"""Check hyperlink consistency across an Obsidian-style vault.

Uses :mod:`obsidiantools` to parse the vault and surface:

* Unresolved wiki-link targets (``[[Foo_Bar_42]]`` with no matching note).
* Unresolved relative Markdown links (``[text](path.md)`` whose target is
  missing on disk).
* Person-shaped links whose resolved target lives outside ``persons/``.

Broken wiki-links are split into two buckets:

* **Unresearched persons** — targets shaped like a person-note slug
  (``Firstname_Lastname`` or ``Firstname_Lastname_ID``). Expected when a
  referenced person has not been researched yet.
* **Broken** — every other unresolved link. Real errors.

Exit code is ``0`` when nothing is broken (unresearched persons are
informational), ``1`` when at least one real broken link or misplaced
person link is found.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path

import obsidiantools.api as otools

PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_EXCLUDES = ("*template*",)
PERSONS_DIR = "persons"


def looks_like_person_slug(target: str) -> bool:
    # Either Firstname_Lastname_ID (researched) or Firstname_Lastname (yet to
    # be researched). Both are permissible person references.
    name = Path(target).name
    if DATE_RE.match(name):
        return False
    return "_" in name


def is_date_link(target: str) -> bool:
    return bool(DATE_RE.match(Path(target).name))


def is_template_placeholder(target: str) -> bool:
    # Targets like ``{{Father_Slug}}`` in the template file aren't real links.
    return bool(PLACEHOLDER_RE.search(target))


def is_excluded(note_path: Path, patterns: tuple[str, ...]) -> bool:
    parts = note_path.as_posix()
    name = note_path.name
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(parts, p) for p in patterns)


def _under_persons(rel_path: Path) -> bool:
    return rel_path.as_posix().startswith(PERSONS_DIR + "/")


def find_broken_md_links(
    vault: otools.Vault,
    vault_root: Path,
    exclude: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Return ``(source_note, target_path)`` pairs for missing relative links."""
    broken: list[tuple[str, str]] = []
    for note, targets in vault.md_links_index.items():
        note_path = vault.md_file_index.get(note)
        if note_path is None:
            continue
        if is_excluded(Path(note_path), exclude):
            continue
        note_dir = (vault_root / note_path).parent
        for target in targets:
            if "://" in target or target.startswith(("#", "mailto:", "/")):
                continue
            clean = target.split("#", 1)[0].split("?", 1)[0]
            if not clean:
                continue
            candidate = (note_dir / clean).resolve()
            if candidate.exists():
                continue
            if not candidate.suffix and candidate.with_suffix(".md").exists():
                continue
            broken.append((note, target))
    return broken


def find_misplaced_person_links(
    vault: otools.Vault,
    vault_root: Path,
    exclude: tuple[str, ...],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Return person-shaped links whose resolved target sits outside ``persons/``.

    Two lists: wiki-link misplacements and markdown-link misplacements. Each
    item is ``(source_note, link_text, resolved_relative_path)``.
    """
    wiki: list[tuple[str, str, str]] = []
    for source, targets in vault.wikilinks_index.items():
        source_path = vault.md_file_index.get(source)
        if source_path is None or is_excluded(Path(source_path), exclude):
            continue
        for target in targets:
            if not looks_like_person_slug(target) or is_template_placeholder(target):
                continue
            target_path = vault.md_file_index.get(target)
            if target_path is None:
                continue  # unresolved — handled by the unresearched bucket
            if not _under_persons(Path(target_path)):
                wiki.append((source, target, Path(target_path).as_posix()))

    md: list[tuple[str, str, str]] = []
    for note, targets in vault.md_links_index.items():
        note_path = vault.md_file_index.get(note)
        if note_path is None or is_excluded(Path(note_path), exclude):
            continue
        note_dir = (vault_root / note_path).parent
        for target in targets:
            if "://" in target or target.startswith(("#", "mailto:", "/")):
                continue
            clean = target.split("#", 1)[0].split("?", 1)[0]
            if not clean:
                continue
            stem = Path(clean).stem
            if not looks_like_person_slug(stem):
                continue
            candidate = (note_dir / clean).resolve()
            if not candidate.exists():
                if candidate.suffix:
                    continue
                candidate = candidate.with_suffix(".md")
                if not candidate.exists():
                    continue
            try:
                rel = candidate.relative_to(vault_root)
            except ValueError:
                continue
            if not _under_persons(rel):
                md.append((note, target, rel.as_posix()))
    return wiki, md


def referrers_for(
    vault: otools.Vault,
    target: str,
    exclude: tuple[str, ...],
) -> list[str]:
    out = []
    for note in vault.get_backlinks(target):
        note_path = vault.md_file_index.get(note)
        if note_path is None or is_excluded(Path(note_path), exclude):
            continue
        out.append(note)
    return out


def render(
    vault: otools.Vault,
    nonexistent: list[str],
    broken_md: list[tuple[str, str]],
    misplaced_wiki: list[tuple[str, str, str]],
    misplaced_md: list[tuple[str, str, str]],
    exclude: tuple[str, ...],
) -> tuple[str, int]:
    unresearched: list[tuple[str, list[str]]] = []
    broken_wiki: list[tuple[str, list[str]]] = []
    for target in nonexistent:
        if is_template_placeholder(target) or is_date_link(target):
            continue
        referrers = referrers_for(vault, target, exclude)
        if not referrers:
            continue
        bucket = unresearched if looks_like_person_slug(target) else broken_wiki
        bucket.append((target, referrers))

    lines: list[str] = []
    error_count = len(broken_wiki) + len(broken_md) + len(misplaced_wiki) + len(misplaced_md)

    if broken_wiki:
        lines.append(f"Broken wiki-links ({len(broken_wiki)}):")
        for target, referrers in sorted(broken_wiki):
            lines.append(f"  [[{target}]]  referenced in: {', '.join(referrers)}")
    if broken_md:
        if lines:
            lines.append("")
        lines.append(f"Broken markdown links ({len(broken_md)}):")
        for note, target in sorted(broken_md):
            lines.append(f"  {note}  →  {target}")
    if misplaced_wiki or misplaced_md:
        if lines:
            lines.append("")
        total = len(misplaced_wiki) + len(misplaced_md)
        lines.append(
            f"Misplaced person links ({total}) — person notes must live " f"under {PERSONS_DIR}/:"
        )
        for source, target, path in sorted(misplaced_wiki):
            lines.append(f"  [[{target}]] in {source}  →  {path}")
        for source, target, path in sorted(misplaced_md):
            lines.append(f"  {source}  →  {target}  (resolves to {path})")
    if unresearched:
        if lines:
            lines.append("")
        lines.append(
            f"Unresearched persons ({len(unresearched)}) — person notes " f"that don't exist yet:"
        )
        for target, referrers in sorted(unresearched):
            lines.append(f"  [[{target}]]  referenced in: {', '.join(referrers)}")
    if not lines:
        lines.append("All links resolve.")
    return "\n".join(lines), error_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "vault",
        nargs="?",
        default=".",
        help="Vault root directory (default: current working directory).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "Skip files matching this glob (matched against basename and "
            "POSIX-style relative path). Repeatable. Defaults: " + ", ".join(DEFAULT_EXCLUDES)
        ),
    )
    args = parser.parse_args(argv)

    vault_root = Path(args.vault).resolve()
    if not vault_root.is_dir():
        print(f"error: {vault_root} is not a directory", file=sys.stderr)
        return 2

    exclude = tuple(args.exclude) or DEFAULT_EXCLUDES
    vault = otools.Vault(vault_root).connect()
    broken_md = find_broken_md_links(vault, vault_root, exclude)
    misplaced_wiki, misplaced_md = find_misplaced_person_links(vault, vault_root, exclude)
    report, error_count = render(
        vault,
        vault.nonexistent_notes,
        broken_md,
        misplaced_wiki,
        misplaced_md,
        exclude,
    )
    print(report)
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
