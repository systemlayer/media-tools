import subprocess
import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, call, patch
import cli


class MainTests(unittest.TestCase):
  @patch("cli._run_command_line", side_effect=KeyboardInterrupt)
  def test_keyboard_interrupt_exits_with_status_130(
      self,
      _mock_run_command_line: MagicMock,
  ) -> None:
    error = StringIO()
    with self.assertRaises(SystemExit) as raised, redirect_stderr(error):
      cli.main()
    self.assertEqual(raised.exception.code, 130)
    self.assertEqual(error.getvalue(), "\nInterrupted.\n")


class GainTests(unittest.TestCase):
  def test_force_defaults_to_false(self) -> None:
    args = cli.build_parser().parse_args(["gain", "/music"])

    self.assertFalse(args.force)

  def test_parser_accepts_force(self) -> None:
    args = cli.build_parser().parse_args(["gain", "--force", "/music"])

    self.assertTrue(args.force)

  @patch("cli.subprocess.run")
  def test_gain_skips_existing_tags_by_default(self, mock_run) -> None:
    cli.handle_gain(Namespace(directory=Path("/music"), force=False))

    mock_run.assert_called_once_with(
        [
            "rsgain",
            "easy",
            "-p",
            "no_album",
            "-m",
            "MAX",
            "--skip-existing",
            "/music",
        ],
        check=True,
    )

  @patch("cli.subprocess.run")
  def test_force_processes_files_with_existing_tags(self, mock_run) -> None:
    cli.handle_gain(Namespace(directory=Path("/music"), force=True))

    mock_run.assert_called_once_with(
        [
            "rsgain",
            "easy",
            "-p",
            "no_album",
            "-m",
            "MAX",
            "/music",
        ],
        check=True,
    )


class FlacTests(unittest.TestCase):
  def test_importing_cli_does_not_load_flac_detective(self) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import cli; raise SystemExit('flac_detective' in sys.modules)",
        ],
        cwd=Path(__file__).parent,
        check=False,
    )
    self.assertEqual(result.returncode, 0)

  def test_flac_options_have_expected_defaults(self) -> None:
    args = cli.build_parser().parse_args(["flac", "/music"])
    self.assertEqual(args.jobs, cli.os.cpu_count() or 1)
    self.assertIsNone(args.sample_duration)

  def test_parser_accepts_flac_options(self) -> None:
    args = cli.build_parser().parse_args([
        "flac",
        "--jobs",
        "3",
        "--sample-duration",
        "15.5",
        "/music",
    ])
    self.assertEqual(args.jobs, 3)
    self.assertEqual(args.sample_duration, 15.5)

  def test_parser_rejects_non_positive_jobs(self) -> None:
    with self.assertRaises(SystemExit):
      cli.build_parser().parse_args(["flac", "--jobs", "0", "/music"])

  @patch("flac_detective.FLACAnalyzer")
  def test_analyzer_uses_default_sample_duration(self, mock_analyzer: MagicMock) -> None:
    cli._analyze_flac(Path("track.flac"), None)
    mock_analyzer.assert_called_once_with()
    mock_analyzer.return_value.analyze_file.assert_called_once_with(Path("track.flac"))

  @patch("flac_detective.FLACAnalyzer")
  def test_analyzer_accepts_sample_duration(self, mock_analyzer: MagicMock) -> None:
    cli._analyze_flac(Path("track.flac"), 20.0)
    mock_analyzer.assert_called_once_with(sample_duration=20.0)

  @patch("cli.as_completed", side_effect=lambda futures: futures)
  @patch("cli.ProcessPoolExecutor")
  def test_flac_prints_only_non_authentic_results(
      self,
      mock_executor: MagicMock,
      _mock_as_completed: MagicMock,
  ) -> None:
    with TemporaryDirectory() as temp_dir:
      directory = Path(temp_dir)
      authentic = directory / "authentic.flac"
      suspicious = directory / "suspicious.FLAC"
      ignored = directory / "track.mp3"
      authentic.touch()
      suspicious.touch()
      ignored.touch()
      authentic_future = MagicMock()
      authentic_future.result.return_value = {"verdict": "AUTHENTIC", "score": 0}
      suspicious_future = MagicMock()
      suspicious_future.result.return_value = {
          "verdict": "SUSPICIOUS",
          "score": 75,
          "confidence": "Anomalies detected may be legitimate",
          "reason": "Constant MP3 bitrate detected",
          "score_breakdown": {
              "rule_1": 50,
              "rule_2": 0,
              "rule_3": -5,
          },
          "verbose_detail": "must not be rendered",
      }
      executor = mock_executor.return_value.__enter__.return_value
      executor.submit.side_effect = [authentic_future, suspicious_future]
      output = StringIO()
      with redirect_stdout(output):
        cli.handle_flac(Namespace(
            directory=directory,
            jobs=2,
            sample_duration=None,
        ))
    mock_executor.assert_called_once_with(max_workers=2)
    self.assertEqual(
        executor.submit.call_args_list,
        [
            call(cli._analyze_flac, authentic, None),
            call(cli._analyze_flac, suspicious, None),
        ],
    )
    rendered = output.getvalue()
    self.assertNotIn(str(authentic), rendered)
    self.assertNotIn(str(ignored), rendered)
    self.assertEqual(
        rendered,
        f"Scanning directory: {directory}\n"
        f"{suspicious}\n"
        "Anomalies detected may be legitimate\n"
        "Score=75 Verdict=SUSPICIOUS\n"
        "Score breakdown: rule_1=50, rule_3=-5\n"
        "Reason: Constant MP3 bitrate detected\n"
        "\n",
    )

  def test_flac_score_breakdown_formats_missing_or_zero_rules(self) -> None:
    self.assertEqual(cli._format_score_breakdown({}), "(none)")
    self.assertEqual(
        cli._format_score_breakdown({"score_breakdown": {"rule_1": 0}}),
        "(none)",
    )

  @patch("cli.as_completed", side_effect=KeyboardInterrupt)
  @patch("cli.ProcessPoolExecutor")
  def test_flac_terminates_workers_when_interrupted(
      self,
      mock_executor: MagicMock,
      _mock_as_completed: MagicMock,
  ) -> None:
    with TemporaryDirectory() as temp_dir:
      directory = Path(temp_dir)
      (directory / "track.flac").touch()
      executor = mock_executor.return_value.__enter__.return_value
      with self.assertRaises(KeyboardInterrupt), redirect_stdout(StringIO()):
        cli.handle_flac(Namespace(
            directory=directory,
            jobs=1,
            sample_duration=None,
        ))
    executor.terminate_workers.assert_called_once_with()


if __name__ == "__main__":
  unittest.main()
