# pthexec

Process a directory of images with a Spandrel-supported `.pth` image model, such as an upscaling or restoration model. Requires a CUDA-capable GPU and a CUDA-enabled PyTorch installation.

Install dependencies and run from this directory:

```sh
python3 -m pip install -r requirements.txt
python3 pthexec.py -i ./input -o ./output -m ./models/model.pth
python3 pthexec.py -i ./input -o ./output -m model.pth:2 --rgb -c 6
```

- `-i, --input`: existing directory containing images.
- `-o, --output`: output directory, created if needed; must differ from the input directory.
- `-m, --model`: model path, optionally followed by `:N` to apply it `N` times (default: `1`). If the path is not an existing file, it is resolved under `models/` beside the script.
- `--rgb`: convert inputs to RGB for models requiring three channels; removes alpha.
- `-c, --compression`: PNG compression level from `0` to `9` (default: `1`).

Every file directly inside the input directory is processed sequentially; subdirectories are skipped. Keep only supported images there. Outputs retain their filenames and formats, and existing files with matching names are overwritten.
