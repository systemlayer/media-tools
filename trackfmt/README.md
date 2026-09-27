# trackfmt

`trackfmt` is a small command-line tool for organizing an audio library. It can
set MP3/FLAC grouping tags, add ReplayGain metadata, find duplicate tracks, and
detect FLAC files transcoded from lossy sources.

## Required tools

The following external CLI tools must be available on `PATH` for the commands
that use them:

- `metaflac`: Reads and updates grouping tags in FLAC files for `grouping`.
- `eyeD3`: Reads and updates grouping tags in MP3 files for `grouping`.
- `rsgain`: Calculates and writes ReplayGain metadata for `gain`.
- `audiomatch`: Compares audio files to find duplicates for `dedup`.

## Development

All required external CLI tools except `audiomatch` can be installed through
the `apt` or `apk` package manager, depending on your Linux distribution.

Install the Python dependencies with `pip`.

```sh
python3 -m pip install --only-binary=:all: audiomatch==0.1.8 flac-detective==1.18.0
python3 -m pip install termcolor==3.3.0
```

Run all automatic tests from the repository root:

```sh
python3 -m unittest discover -v
```

Run an individual test module:

```sh
python3 -m unittest -v test_cli
python3 -m unittest -v test_media
```

## Usage

```sh
python3 cli.py [--non-interactive] {grouping,gain,dedup,flac} DIRECTORY
```

Run `python3 cli.py COMMAND --help` for command-specific options.

### FLAC verdicts

The `flac` command reports non-authentic results using the first character of
the verdict:

- `W` (`WARNING`): The result is uncertain; check the file manually.
- `S` (`SUSPICIOUS`): The evidence is stronger than a warning, but is not conclusive.
- `F` (`FAKE_CERTAIN`): The file is definitively a fake FLAC sourced from lossy audio.
