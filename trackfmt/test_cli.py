import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, call, patch
import cli


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

  @patch("cli.FLACAnalyzer")
  def test_analyzer_uses_default_sample_duration(self, mock_analyzer: MagicMock) -> None:
    cli._analyze_flac(Path("track.flac"), None)
    mock_analyzer.assert_called_once_with()
    mock_analyzer.return_value.analyze_file.assert_called_once_with(Path("track.flac"))

  @patch("cli.FLACAnalyzer")
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
      suspicious_future.result.return_value = {"verdict": "SUSPICIOUS", "score": 75}
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
    self.assertIn(
        f"{suspicious}\n{{'verdict': 'SUSPICIOUS',\n 'score': 75}}\n\n",
        rendered,
    )


if __name__ == "__main__":
  unittest.main()
