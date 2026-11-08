# pthexec

Process a directory of images with one or more Spandrel-supported `.pth` image models, such as upscaling or restoration models. Requires a CUDA-capable GPU and a CUDA-enabled PyTorch installation. All models are loaded once and kept on the GPU.

Install dependencies and run from this directory:

```sh
python3 -m pip install -r requirements.txt
python3 pthexec.py --list
python3 pthexec.py -i ./input -o ./output --models ./models/model.pth
python3 pthexec.py -i ./input -o ./output --models restore.pth:2 upscale.pth --rgb -c 6
```

- `-l, --list`: list sorted `.pth` filenames directly inside `models/` beside the script and exit.
- `-i, --input`: existing directory containing images.
- `-o, --output`: output directory, created if needed; must differ from the input directory.
- `-m, --models`: one or more model paths, each optionally followed by `:N` for a positive pass count (default: `1`). Paths are checked as supplied, then under `models/` beside the script; files must exist.
- `--rgb`: convert inputs to RGB for models requiring three channels; removes alpha.
- `-c, --compression`: PNG compression level from `0` to `9` (default: `1`).

For each image, models run left to right, completing each model's passes before the next model receives its output. The example runs **restore → restore → upscale → save**, saving only the final result.

Every file directly inside the input directory is processed sequentially; subdirectories are skipped. Keep only supported images there. Outputs retain their filenames and formats, and existing files with matching names are overwritten. Processing stops on the first failure; model errors identify the stage and, during inference, the pass.
