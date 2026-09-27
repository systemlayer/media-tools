#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from enum import StrEnum
from pathlib import Path, PosixPath
from media import read_flac_tags, read_mp3_grouping
from termcolor import colored

# FLAC Detective verdicts: https://guillain-rdcde.github.io/FLAC_Detective/api-reference.html
class FlacVerdict(StrEnum):
  AUTHENTIC = "AUTHENTIC"
  WARNING = "WARNING"
  SUSPICIOUS = "SUSPICIOUS"
  FAKE_CERTAIN = "FAKE_CERTAIN"


# Seconds between FLAC analysis progress updates.
_FLAC_PROGRESS_INTERVAL_SECONDS: int = 30

# Colors used for FLAC analysis verdict headings.
_FLAC_VERDICT_COLORS: dict[str, str] = {
    FlacVerdict.WARNING: "yellow",
    FlacVerdict.SUSPICIOUS: "red",
    FlacVerdict.FAKE_CERTAIN: "red",
}

# Unicode ranges used for emoji characters and their sequence markers.
_EMOJI_PATTERN = re.compile(
    "[\u200d\u20e3\u2600-\u27bf\u2b00-\u2bff\ufe0e\ufe0f"
    "\U0001f1e6-\U0001f1ff\U0001f300-\U0001faff]"
)


def existing_dir(path_str: str) -> Path:
  path = Path(path_str)
  if not path.is_dir():
    raise argparse.ArgumentTypeError(f"not a directory: {path}")
  return path


def _parse_positive_int(value: str) -> int:
  parsed = int(value)
  if parsed < 1:
    raise argparse.ArgumentTypeError("must be 1 or more")
  return parsed


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="trackfmt")
  parser.add_argument(
      "--non-interactive",
      action="store_true",
      help="Run without waiting for confirmation.",
  )
  subparsers = parser.add_subparsers(dest="command", required=True)

  commands = {
      "grouping": "Set the grouping tag on audio files.",
      "gain": "Add ReplayGain metadata to audio files.",
      "dedup": "Scan for duplicate audio files.",
      "flac": "Detect FLAC files transcoded from lossy sources.",
  }

  for name, help_text in commands.items():
    subparser = subparsers.add_parser(
        name, help=help_text, description=help_text)
    subparser.add_argument(
        "directory",
        nargs="?",
        help="Path to a directory containing audio files. Optional when MEDIA_PATH is set.",
    )
    if name == "grouping":
      subparser.add_argument(
          "--dry-run",
          action="store_true",
          help="Show what would be done without making changes.",
      )
    if name == "gain":
      subparser.add_argument(
          "--force",
          action="store_true",
          help="Recalculate ReplayGain metadata even when tags already exist.",
      )
    if name == "dedup":
      subparser.add_argument(
          "--length",
          type=int,
          default=120,
          help="Number of seconds to analyze (default: 120).",
      )
    if name == "flac":
      subparser.add_argument(
          "--jobs",
          type=_parse_positive_int,
          default=os.cpu_count() or 1,
          help="Number of concurrent analysis jobs (default: number of CPUs).",
      )
      subparser.add_argument(
          "--sample-duration",
          type=float,
          default=None,
          help="Seconds of audio to sample per window (default: analyzer default).",
      )

  return parser


def resolve_directory(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace
) -> Path:
  media_path = os.environ.get("MEDIA_PATH")
  if media_path:
    return existing_dir(media_path)
  if args.directory is None:
    parser.error("the following arguments are required: directory")
  return existing_dir(args.directory)


def _press_return_to_continue() -> None:
  if not sys.stdin.isatty():
    sys.exit("ERROR: Interactive confirmation requires a TTY.")
  input("Press Return to continue...")


def handle_grouping(args: argparse.Namespace) -> None:
  base_dir: PosixPath = args.directory.resolve()
  skipped_names = {"cover.jpg", "cover.png", ".ndignore"}

  print(f"Scanning directory: {args.directory}")
  entries: list[Path] = sorted(args.directory.rglob("*"))

  for file_path in entries:
    if not file_path.is_file():
      continue

    if file_path.name in skipped_names:
      continue

    file_abs = file_path.resolve()
    try:
      relative = file_abs.relative_to(base_dir).as_posix()
    except ValueError:
      sys.exit(f"ERROR: File not under BASE_DIR (unexpected): {file_path}")

    # Parse expected 4 components.
    # e.g., "game/Super Tux Kart/SuperTux SOUNDTRACK/track1.mp3".
    parts = relative.split("/", 3)
    if len(parts) < 4:
      sys.exit(f"ERROR: Unexpected directory structure: {file_path}")

    # Grouping can be the complete relative path, or could be stylized.
    # Using the relative path is longer and difficult to read
    # e.g., "category/collection/album".
    _category, collection, _album, audio_file = parts
    grouping = collection
    extension = Path(audio_file).suffix.lower()

    if extension == ".flac":
      current = read_flac_tags(str(file_path)).get("GROUPING")
      if current == grouping:
        if args.dry_run:
          print(f"Skipping (already tagged): {file_path}")
        continue

      print(f"Tagging FLAC: {file_path} (Grouping={grouping})")
      if not args.dry_run:
        subprocess.run(
            [
                "metaflac",
                "--remove-tag=GROUPING",
                f"--set-tag=GROUPING={grouping}",
                str(file_path),
            ],
            check=True,
        )
      continue

    if extension == ".mp3":
      current = read_mp3_grouping(str(file_path))
      if current == grouping:
        if args.dry_run:
          print(f"Skipping (already tagged): {file_path}")
        continue

      print(f"Tagging MP3: {file_path} (Grouping={grouping})")
      if not args.dry_run:
        subprocess.run(
            [
                "eyeD3",
                "--user-text-frame",
                f"GRP1:{grouping}",
                str(file_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
      continue

    print(f"WARNING: Non-audio file found: {file_path}")


def handle_gain(args: argparse.Namespace) -> None:
  skip_existing = [] if args.force else ["--skip-existing"]
  subprocess.run(
      [
          "rsgain",
          "easy",
          "-p",
          "no_album",
          "-m",
          "MAX",
          *skip_existing,
          str(args.directory),
      ],
      check=True,
  )


def handle_dedup(args: argparse.Namespace) -> None:
  print(f"Scanning directory: {args.directory}")
  audio_files = sorted(
      file_path.relative_to(args.directory).as_posix()
      for file_path in args.directory.rglob("*")
      if file_path.is_file() and file_path.suffix.lower() in {".mp3", ".flac"}
  )
  subprocess.run(
      [
          "audiomatch",
          "--length",
          str(args.length),
          *audio_files,
      ],
      check=True,
      cwd=args.directory,
  )


def _analyze_flac(file_path: Path, sample_duration: float | None) -> dict[str, object]:
  """Analyze one FLAC file without overriding the analyzer's default duration."""
  # Import this dependency only for FLAC analysis to reduce the attack surface in case
  # of a supply-chain attack: unrelated commands avoid its import-time code. This does
  # not protect against install-time behavior, compromised transitive dependencies, or
  # execution when FLAC analysis itself is invoked.
  from flac_detective import FLACAnalyzer
  # FLACAnalyzer's automatic repair fallback cannot be disabled through its public API.
  # Wrapping it with another temporary copy would be inefficient because the analyzer
  # already copies each file. Mount the media directory read-only to prevent repairs.
  if sample_duration is None:
    analyzer = FLACAnalyzer()
  else:
    analyzer = FLACAnalyzer(sample_duration=sample_duration)
  return analyzer.analyze_file(file_path)


def _format_score_breakdown(result: dict[str, object]) -> str:
  """Format the non-zero score contributions from an analysis result."""
  breakdown = result.get("score_breakdown")
  if not isinstance(breakdown, dict):
    return "(none)"
  entries = []
  for rule, value in breakdown.items():
    if value != 0:
      entries.append(f"{rule}={value}")
  return ", ".join(entries) or "(none)"


# Format the result heading with the color assigned to its verdict.
def _format_flac_heading(verdict: object, file_path: Path) -> str:
  heading = f"[{verdict}] {file_path}"
  color = _FLAC_VERDICT_COLORS.get(str(verdict))
  return colored(heading, color) if color is not None else heading


# Remove emoji characters and surrounding whitespace from display text.
def _remove_emojis(value: object) -> str:
  return _EMOJI_PATTERN.sub("", str(value)).strip()


def handle_flac(args: argparse.Namespace) -> None:
  # Discover the complete workload before analysis so progress has a stable total.
  print(f"Scanning directory: {args.directory}")
  flac_files = sorted(
      file_path
      for file_path in args.directory.rglob("*")
      if file_path.is_file() and file_path.suffix.lower() == ".flac"
  )
  # Use a monotonic clock so system clock changes do not affect progress timing.
  started_at = time.monotonic()
  next_progress_at = started_at + _FLAC_PROGRESS_INTERVAL_SECONDS
  completed_count = 0
  with ProcessPoolExecutor(max_workers=args.jobs) as executor:
    try:
      # Submit every file once and retain its path for rendering suspicious results.
      futures = {
          executor.submit(_analyze_flac, file_path, args.sample_duration): file_path
          for file_path in flac_files
      }
      pending = set(futures)
      while pending:
        # Wake for either the next completed analysis or the next progress update.
        timeout = max(0.0, next_progress_at - time.monotonic())
        done, pending = wait(pending, timeout=timeout, return_when=FIRST_COMPLETED)
        # Count all completed analyses, but print details only for suspicious files.
        for future in done:
          file_path = futures[future]
          result = future.result()
          completed_count += 1
          if result.get("verdict") == FlacVerdict.AUTHENTIC:
            continue
          print(_format_flac_heading(result["verdict"], file_path))
          print(_remove_emojis(result["confidence"]))
          print(
              f"Score: {result['score']} "
              f"Breakdown: {_format_score_breakdown(result)}"
          )
          print(f"Reason: {result['reason']}")
        # Report progress at most once per interval while work remains.
        now = time.monotonic()
        if pending and now >= next_progress_at:
          elapsed_seconds = int(now - started_at)
          progress = f"File {completed_count}/{len(flac_files)}. Elapsed time {elapsed_seconds}s"
          print(colored(progress, "dark_grey"), file=sys.stderr)
          next_progress_at = now + _FLAC_PROGRESS_INTERVAL_SECONDS
    except KeyboardInterrupt:
      executor.terminate_workers()
      raise


def _run_command_line() -> None:
  parser = build_parser()
  args = parser.parse_args()
  args.directory = resolve_directory(parser, args)
  handlers = {
      "grouping": handle_grouping,
      "gain": handle_gain,
      "dedup": handle_dedup,
      "flac": handle_flac,
  }
  if not args.non_interactive:
    _press_return_to_continue()
  handlers[args.command](args)


def main() -> None:
  try:
    _run_command_line()
  except KeyboardInterrupt:
    print("\nInterrupted.", file=sys.stderr)
    raise SystemExit(130)


if __name__ == "__main__":
  main()
