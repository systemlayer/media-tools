# trackfmt

`trackfmt` is a small command-line tool for organizing an audio library. It can
set MP3/FLAC grouping tags, add ReplayGain metadata, find duplicate tracks, and
detect FLAC files transcoded from lossy sources.

## Required tools

The tools needed for the commands you use must be available on `PATH`:

- `metaflac`: Reads and updates grouping tags in FLAC files for `grouping`.
- `eyeD3`: Reads and updates grouping tags in MP3 files for `grouping`.
- `rsgain`: Calculates and writes ReplayGain metadata for `gain`.
- `audiomatch`: Compares audio files to find duplicates for `dedup`.
- `flac-detective`: Detects FLAC files transcoded from lossy sources for `flac`.

## Development

All required tools except `audiomatch` can be installed through the `apt` or
`apk` package manager, depending on your Linux distribution.

Install the Python dependencies with `pip`. Version 0.1.8 of `audiomatch` is the
latest release as of July 2026:

```sh
python3 -m pip install -r requirements.txt
python3 -m pip install --only-binary=:all: audiomatch==0.1.8
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
