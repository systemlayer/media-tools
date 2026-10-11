#!/bin/env python

import torch
from spandrel import ImageModelDescriptor, ModelLoader, ModelDescriptor  # type: ignore
from PIL import Image, ImageFile
from torchvision import transforms  # type: ignore
from typing import Union
import sys
from pathlib import Path
import argparse


# Load an image model and prepare it for GPU inference.
def initialize_model(model_file: Path) -> ModelDescriptor:
  model = ModelLoader().load_from_file(str(model_file))
  assert isinstance(model, ImageModelDescriptor)
  # Send it to the GPU and put it in inference mode.
  model.cuda().eval()
  return model


def run_model(model: ModelDescriptor, image: torch.Tensor) -> torch.Tensor:
  with torch.no_grad():
    tensor = model(image)  # type: ignore
    assert isinstance(tensor, torch.Tensor)
    return tensor


# Receives a PIL image, runs the model against it, and converts the result back to a PIL image.
# The "upscale" name in the function is by convention only, the image processing is defined by the
# model i.e., it could change colors or fix artifacts and preserve the image size.
def upscale_image(
    image: Union[Image.Image, ImageFile.ImageFile],
    model: ModelDescriptor, passes: int
) -> Image.Image:
  # Define transformation pipeline to convert the PIL image to a torch.Tensor.
  transform = transforms.Compose([
      transforms.ToTensor(),  # Converts the image to a torch.Tensor
      # transforms.Normalize((0.5,), (0.5,)) # Common for 8-bit RGB images
  ])
  transform_tensor: torch.Tensor = transform(image)  # type: ignore
  # Move to GPU (with ".cuda()").
  image_tensor = transform_tensor.unsqueeze(0).cuda()
  for _ in range(passes):
    image_tensor = run_model(model, image_tensor)
  # Convert the processed tensor back to a PIL image, "squeeze(0)" will remove
  # the batch dimension (i.e., undo the previous "unsqueeze(0)").
  image_tensor = image_tensor.squeeze(0).cpu()
  # Denormalize the image if necessary (reverses "transforms.Normalize").
  # image_tensor = image_tensor * 0.5 + 0.5
  upscaled_image = transforms.ToPILImage()(image_tensor)  # type: ignore
  assert isinstance(upscaled_image, Image.Image)
  return upscaled_image


# Process an image, optionally forcing RGB for models that require three channels, and save it.
def process_image(
    input_file: Path,
    output_dir: Path,
    model: ModelDescriptor,
    passes: int,
    force_rgb: bool,
    compression: int
) -> None:
  # Sometimes images can contain alpha channels (RGBA) but some models only work with RGB, thus an
  # error like "Given groups=1, weight of size [...], expected input[...] to have 3 channels, but
  # got 4 channels instead". Use the force_rgb argument to avoid these errors.
  # Can also happen with frames taken from 10-bit videos.
  with Image.open(input_file) as image:
    if force_rgb:
      image = image.convert("RGB")
    upscaled_image = upscale_image(image, model, passes)
  output_file = output_dir / input_file.name
  # Keeping the input filename lets Pillow pick the output format from its extension.
  # compress_level only applies to PNGs; it's fine for other formats to ignore it.
  upscaled_image.save(output_file, compress_level=compression)


# Parse the input, output, model, RGB, and PNG compression options.
def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser()
  parser.add_argument("-i", "--input", type=Path, required=True,
                      help="Path for the input directory")
  parser.add_argument("-o", "--output", type=Path, required=True,
                      help="Path for the output directory")
  parser.add_argument("-m", "--model", type=str, required=True, help="Path for the .pth model file")
  parser.add_argument("--rgb", action="store_true", default=False, help="Force convert to RGB")
  parser.add_argument("-c", "--compression", type=int, choices=range(10), default=1,
                      help="PNG compression level from 0 to 9 (default: 1)")
  return parser.parse_args()


# Look for bundled models in this directory beside the script.
MODELS_DIR = Path("models")


# Resolve a model path and its optional colon-separated pass count.
def locate_model(model_file_with_passes: str) -> tuple[Path, int]:
  parts = model_file_with_passes.rsplit(":", 1)
  model_path = Path(parts[0])
  pass_count = "1" if len(parts) == 1 else (parts[1] or "1")
  try:
    passes = int(pass_count)
  except ValueError as error:
    raise argparse.ArgumentTypeError("Pass count must be a positive integer") from error
  if passes < 1:
    raise argparse.ArgumentTypeError("Pass count must be a positive integer")
  if model_path.is_file():
    return model_path, passes
  script_dir = Path(__file__).resolve().parent
  return script_dir / MODELS_DIR / model_path, passes


# Validate paths and process input files sequentially with one loaded model.
def main() -> int:
  args = parse_args()
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
  model_file, passes = locate_model(args.model)
  print(
      f"Input    : {input_dir_real}\nOutput   : {output_dir_real}\nModel    : {model_file}:{passes}\nForce RGB: {args.rgb}")
  if input_dir_real == output_dir_real:
    print("ERROR: input directory must not be the same as the output directory")
    return 1
  output_dir_real.mkdir(parents=True, exist_ok=True)
  model = initialize_model(model_file)
  files: list[Path] = []
  for entry in input_dir_real.iterdir():
    if entry.is_file():
      files.append(entry)
  # Using multiprocessing.Pool would not work because may variables need to be
  # shared, it's especially annoying because of the PyTorch stuff, so just do
  # it sequentially. Use an external program to distribute the tasks if needed.
  for image_file in files:
    process_image(image_file, output_dir_real, model, passes, args.rgb, args.compression)
  return 0


if __name__ == "__main__":
  sys.exit(main())
