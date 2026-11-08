#!/bin/env python

from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
import sys
from pathlib import Path
import argparse

if TYPE_CHECKING:
  import torch
  from spandrel import ImageModelDescriptor  # type: ignore
  from PIL import Image


# Look for bundled models in this directory beside the script.
MODELS_DIR = Path(__file__).resolve().parent / "models"


# Keep a loaded model together with its source and repetition count.
@dataclass(frozen=True)
class ModelStage:
  path: Path
  model: ImageModelDescriptor
  passes: int


# Load an image model and prepare it for GPU inference.
def initialize_model(model_file: Path) -> ImageModelDescriptor:
  from spandrel import ImageModelDescriptor, ModelLoader  # type: ignore
  model = ModelLoader().load_from_file(str(model_file))
  assert isinstance(model, ImageModelDescriptor)
  # Send it to the GPU and put it in inference mode.
  model.cuda().eval()
  return model


# Run the GPU model with PyTorch gradient tracking disabled.
def run_model(model: ImageModelDescriptor, image: torch.Tensor) -> torch.Tensor:
  import torch
  with torch.no_grad():
    tensor = model(image)  # type: ignore
    assert isinstance(tensor, torch.Tensor)
    return tensor


# Apply loaded models on the GPU, converting between PIL and tensors only at the boundaries.
def apply_models(
    image: Image.Image,
    stages: list[ModelStage]
) -> Image.Image:
  from PIL import Image
  from torchvision import transforms  # type: ignore
  # Define transformation pipeline to convert the PIL image to a torch.Tensor.
  transform = transforms.Compose([
      transforms.ToTensor(),  # Converts the image to a torch.Tensor
      # transforms.Normalize((0.5,), (0.5,)) # Common for 8-bit RGB images
  ])
  transform_tensor: torch.Tensor = transform(image)  # type: ignore
  # Move to GPU (with ".cuda()").
  image_tensor = transform_tensor.unsqueeze(0).cuda()
  for stage_number, stage in enumerate(stages, start=1):
    for pass_number in range(1, stage.passes + 1):
      try:
        image_tensor = run_model(stage.model, image_tensor)
      except Exception as error:
        raise RuntimeError(
            f"model stage {stage_number}/{len(stages)} ({stage.path}), "
            f"pass {pass_number}/{stage.passes} failed"
        ) from error
  # Convert the processed tensor back to a PIL image, "squeeze(0)" will remove
  # the batch dimension (i.e., undo the previous "unsqueeze(0)").
  image_tensor = image_tensor.squeeze(0).cpu()
  # Denormalize the image if necessary (reverses "transforms.Normalize").
  # image_tensor = image_tensor * 0.5 + 0.5
  processed_image = transforms.ToPILImage()(image_tensor)  # type: ignore
  assert isinstance(processed_image, Image.Image)
  return processed_image


# Process an image, optionally forcing RGB for models that require three channels, and save it.
def process_image(
    input_file: Path,
    output_dir: Path,
    stages: list[ModelStage],
    force_rgb: bool,
    compression: int
) -> None:
  from PIL import Image
  # Sometimes images can contain alpha channels (RGBA) but some models only work with RGB, thus an
  # error like "Given groups=1, weight of size [...], expected input[...] to have 3 channels, but
  # got 4 channels instead". Use the force_rgb argument to avoid these errors.
  # Can also happen with frames taken from 10-bit videos.
  with Image.open(input_file) as image:
    if force_rgb:
      image = image.convert("RGB")
    processed_image = apply_models(image, stages)
  output_file = output_dir / input_file.name
  # Keeping the input filename lets Pillow pick the output format from its extension.
  # compress_level only applies to PNGs; it's fine for other formats to ignore it.
  processed_image.save(output_file, compress_level=compression)


# Read bundled model filenames, print them, and exit through argparse.
class ListModelsAction(argparse.Action):
  # List models from disk on standard output and exit before processing images.
  def __call__(
      self, parser: argparse.ArgumentParser, namespace: argparse.Namespace,
      values: object, option_string: str | None = None
  ) -> None:
    list_models(MODELS_DIR)
    parser.exit()


# Parse CLI options and validate model files on disk; listing exits before validation.
def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(allow_abbrev=False)
  parser.add_argument("-l", "--list", action=ListModelsAction, nargs=0,
                      help="List available .pth models")
  parser.add_argument("-i", "--input", type=Path, required=True,
                      help="Path for the input directory")
  parser.add_argument("-o", "--output", type=Path, required=True,
                      help="Path for the output directory")
  parser.add_argument("-m", "--models", nargs="+", required=True, metavar="MODEL",
                      help="Ordered .pth model paths, each optionally followed by :N passes")
  parser.add_argument("--rgb", action="store_true", default=False, help="Force convert to RGB")
  parser.add_argument("-c", "--compression", type=int, choices=range(10), default=1,
                      help="PNG compression level from 0 to 9 (default: 1)")
  args = parser.parse_args()
  stages: list[tuple[Path, int]] = []
  for specification in args.models:
    try:
      model_path, passes = parse_model_spec(specification)
      stages.append((resolve_model_path(model_path), passes))
    except argparse.ArgumentTypeError as error:
      parser.error(f"{specification!r}: {error}")
  args.models = stages
  return args


# Read the models directory and print sorted .pth filenames to standard output.
def list_models(models_dir: Path) -> None:
  try:
    entries = sorted(models_dir.iterdir())
  except FileNotFoundError:
    return
  for entry in entries:
    if entry.suffix == ".pth" and entry.is_file():
      print(entry.name)


# Parse a model path and its optional positive pass count without accessing disk.
def parse_model_spec(specification: str) -> tuple[Path, int]:
  parts = specification.rsplit(":", 1)
  if not parts[0]:
    raise argparse.ArgumentTypeError("model path must not be empty")
  pass_count = "1" if len(parts) == 1 else parts[1]
  try:
    passes = int(pass_count)
  except ValueError as error:
    raise argparse.ArgumentTypeError("pass count must be a positive integer") from error
  if passes < 1:
    raise argparse.ArgumentTypeError("pass count must be a positive integer")
  return Path(parts[0]), passes


# Find an existing model file on disk, preferring the supplied path to bundled models.
def resolve_model_path(model_path: Path) -> Path:
  if model_path.is_file():
    return model_path.resolve()
  bundled_path = MODELS_DIR / model_path
  if bundled_path.is_file():
    return bundled_path.resolve()
  raise argparse.ArgumentTypeError(f"model file does not exist: {model_path}")


# Validate directories, load models onto the GPU, and read and save images sequentially.
def main() -> int:
  args = parse_args()
  import torch
  if not torch.cuda.is_available():
    print("CUDA is not available", file=sys.stderr)
    return 1
  input_dir_real: Path = args.input.resolve()
  output_dir_real: Path = args.output.resolve()
  if not input_dir_real.is_dir():
    print("ERROR: input must be an existing directory", file=sys.stderr)
    return 1
  if output_dir_real.exists() and not output_dir_real.is_dir():
    print("ERROR: output must be a directory", file=sys.stderr)
    return 1
  print(
      f"Input    : {input_dir_real}\nOutput   : {output_dir_real}\nForce RGB: {args.rgb}")
  print("Models:")
  for stage_number, (model_file, passes) in enumerate(args.models, start=1):
    print(f"  {stage_number}. {model_file} (passes: {passes})")
  if input_dir_real == output_dir_real:
    print("ERROR: input directory must not be the same as the output directory")
    return 1
  stages: list[ModelStage] = []
  for stage_number, (model_file, passes) in enumerate(args.models, start=1):
    try:
      model = initialize_model(model_file)
    except Exception as error:
      raise RuntimeError(
          f"loading model stage {stage_number}/{len(args.models)} ({model_file}) failed"
      ) from error
    stages.append(ModelStage(path=model_file, model=model, passes=passes))
  output_dir_real.mkdir(parents=True, exist_ok=True)
  files: list[Path] = []
  for entry in input_dir_real.iterdir():
    if entry.is_file():
      files.append(entry)
  # Using multiprocessing.Pool would not work because may variables need to be
  # shared, it's especially annoying because of the PyTorch stuff, so just do
  # it sequentially. Use an external program to distribute the tasks if needed.
  for image_file in files:
    process_image(image_file, output_dir_real, stages, args.rgb, args.compression)
  return 0


if __name__ == "__main__":
  sys.exit(main())
