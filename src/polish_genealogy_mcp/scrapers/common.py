"""Shared utilities for the CSV scrapers in this directory.

The catalogue scrapers each target a different upstream but produce the
same flavour of output: a "Miejscowość, Parafia, Rodzaj Księgi, Rok od,
Rok do" CSV that acts as a grep/fzf-friendly index of which parishes
cover which years.

Conventions enforced here:

  * ``-o/--output`` is the single sink switch. Omit it to write to
    stdout; pass a path to write to a file. Errors and progress chatter
    always go to stderr.
  * ``--user-agent`` (or ``PG_SCRAPER_UA``) lets the operator override
    the UA without touching the script. Some upstreams (Geneteka in
    particular) reject bot-looking UAs.
  * ``--timeout`` / ``--delay`` / ``-v/--verbose`` mean the same thing
    everywhere.
  * Resumable scrapers track per-unit progress in a sidecar
    ``<output>.progress`` file. Resume requires ``-o`` (stdout can't
    resume); ``--restart`` discards prior progress.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import IO, Iterable

import requests

BASE_FIELDS: list[str] = [
    "Miejscowość",
    "Parafia",
    "Rodzaj Księgi",
    "Rok od",
    "Rok do",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)

_YEAR_RANGE_OR_BARE_RE = re.compile(r"(\d{4})(?:\s*[-–—]\s*(\d{4}))?")


def eprint(*args: object, **kwargs: object) -> None:
    """`print(..., file=sys.stderr)` with the same signature."""
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)  # type: ignore[arg-type]


def parse_year_ranges(text: str | None) -> list[tuple[int, int]]:
    """Extract every ``(start, end)`` year span from ``text``, in document order.

    Spans without an explicit end (e.g. ``"1812"``) are emitted as
    ``(year, year)``. Ranges may use ASCII hyphen or en/em dash.
    """
    if not text:
        return []
    spans: list[tuple[int, int]] = []
    for m in _YEAR_RANGE_OR_BARE_RE.finditer(text):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        spans.append((start, end))
    return spans


def resolve_user_agent(cli_value: str | None) -> str:
    """Pick the UA: CLI flag → ``PG_SCRAPER_UA`` env → default."""
    if cli_value:
        return cli_value
    env = os.environ.get("PG_SCRAPER_UA")
    if env:
        return env
    return DEFAULT_USER_AGENT


def make_session(user_agent: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": resolve_user_agent(user_agent)})
    return session


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    default_delay: float | None = None,
    default_timeout: float = 30.0,
    supports_resume: bool = False,
) -> None:
    """Wire the standard flags onto ``parser``.

    Use ``default_delay`` for scripts that paginate / loop over many
    upstream requests (set to e.g. 5 to match the project-wide
    GENETEKA_MIN_INTERVAL). Omit for one-shot scrapers.
    """
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="CSV output path. Omit to write to stdout.",
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        help=(
            "Override the HTTP User-Agent header. Falls back to "
            "$PG_SCRAPER_UA, then a desktop-Safari default."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=default_timeout,
        help=f"HTTP timeout in seconds (default: {default_timeout}).",
    )
    if default_delay is not None:
        parser.add_argument(
            "--delay",
            type=float,
            default=default_delay,
            help=f"Seconds to sleep between requests (default: {default_delay}).",
        )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each fetched URL to stderr.",
    )
    parser.add_argument(
        "--input-html",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Parse a captured HTML fixture instead of fetching. Useful "
            "for offline testing. Multi-stage scrapers (e.g. lubgens) "
            "treat FILE as the page their primary parser consumes."
        ),
    )
    if supports_resume:
        parser.add_argument(
            "--restart",
            action="store_true",
            help=(
                "Discard any existing .progress sidecar and rebuild from " "scratch. Requires -o."
            ),
        )


def fetch_text(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    verbose: bool = False,
    params: dict[str, str] | None = None,
) -> str:
    """GET ``url``, raise on HTTP error, return decoded body.

    With ``verbose=True`` the resolved URL is logged to stderr before
    the request goes out.
    """
    if verbose:
        eprint(f"Fetching {url}" + (f" params={params}" if params else ""))
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    return response.text


class CsvSink:
    """Write rows to either a file path or stdout.

    Used as a context manager::

        with CsvSink(args.output, fieldnames=...) as sink:
            sink.write_row({...})
            sink.write_row({...})
        eprint(f"Wrote {sink.row_count} rows")

    When ``output`` is ``None`` rows go to stdout. Otherwise the parent
    directory is created, the file is opened for writing (truncating
    any prior content), and the header is emitted up front.
    """

    def __init__(
        self,
        output: Path | None,
        fieldnames: Iterable[str],
        *,
        mode: str = "w",
        write_header: bool = True,
    ) -> None:
        self.output = output
        self.fieldnames = list(fieldnames)
        self.row_count = 0
        self._owns_handle = output is not None
        self._handle: IO[str]
        if output is None:
            self._handle = sys.stdout
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            self._handle = output.open(mode, encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._handle, fieldnames=self.fieldnames)
        if write_header:
            self._writer.writeheader()
            self._handle.flush()

    def write_row(self, row: dict[str, object]) -> None:
        self._writer.writerow(row)
        self.row_count += 1

    def write_rows(self, rows: Iterable[dict[str, object]]) -> None:
        for row in rows:
            self.write_row(row)

    def flush(self) -> None:
        self._handle.flush()

    def close(self) -> None:
        # Flush in both cases so a stderr-bound "wrote N rows" message
        # printed after `with`-block exit doesn't interleave with stdout.
        self._handle.flush()
        if self._owns_handle:
            self._handle.close()

    def __enter__(self) -> "CsvSink":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _progress_path_for(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".progress")


def _load_completed(progress_path: Path) -> set[str]:
    if not progress_path.exists():
        return set()
    return {
        line.strip()
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


class ResumableCsvSink:
    """Per-unit appendable CSV with a ``<output>.progress`` sidecar.

    Wraps :class:`CsvSink` for the typical scraper loop:

      1. Iterate over units (regions, parishes, ...).
      2. For each unit, call :meth:`already_done` and skip if true.
      3. Otherwise fetch + parse rows, then :meth:`write_unit` which
         flushes the rows and records the unit key.

    Behaviour:

      * If ``output`` is ``None`` we fall back to plain stdout writing
        with no progress tracking (resume is meaningless without a
        durable file). :meth:`already_done` always returns ``False``.
      * If ``restart`` is set, both the CSV and sidecar are removed
        before opening fresh.
      * If a sidecar exists alongside a CSV, the CSV is opened in
        append mode and the header is *not* re-emitted.
    """

    def __init__(
        self,
        output: Path | None,
        fieldnames: Iterable[str],
        *,
        restart: bool = False,
    ) -> None:
        self.output = output
        self.fieldnames = list(fieldnames)
        self.completed: set[str] = set()
        self.progress: Path | None = None

        if output is None:
            if restart:
                eprint("warning: --restart has no effect without -o; ignoring")
            self._sink = CsvSink(None, self.fieldnames)
            return

        self.progress = _progress_path_for(output)
        if restart:
            if self.progress.exists():
                self.progress.unlink()
            if output.exists():
                output.unlink()

        self.completed = _load_completed(self.progress)
        resuming = bool(self.completed) and output.exists()
        if resuming:
            self._sink = CsvSink(output, self.fieldnames, mode="a", write_header=False)
        else:
            self._sink = CsvSink(output, self.fieldnames, mode="w", write_header=True)
            if self.progress.exists():
                self.progress.unlink()
            self.completed = set()

    @property
    def row_count(self) -> int:
        return self._sink.row_count

    def already_done(self, unit_key: str) -> bool:
        return unit_key in self.completed

    def write_unit(self, unit_key: str, rows: Iterable[dict[str, object]]) -> int:
        n = 0
        for row in rows:
            self._sink.write_row(row)
            n += 1
        self._sink.flush()
        if self.progress is not None:
            with self.progress.open("a", encoding="utf-8") as f:
                f.write(unit_key + "\n")
        self.completed.add(unit_key)
        return n

    def close(self) -> None:
        self._sink.close()

    def __enter__(self) -> "ResumableCsvSink":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
