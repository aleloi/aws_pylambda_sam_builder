#!/usr/bin/env python3
# AI-generated with minor edits https://chatgpt.com/share/67d17aa2-6560-8001-829d-8b7973b918a9
"""
Core implementation of aws_pylambda_sam_builder

Usage:
    python -m aws_pylambda_sam_builder --aws-runtime py311 --aws-architecture x86_64 --source path/to/project --destination $ARTIFACTS_DIR

Design:
  * Reads each non-empty, non-comment line from requirements.txt in the source project.
  * For each requirement, it computes a hash based on the requirement string plus the architecture values.
  * It looks for a corresponding folder in the global cache (~/.cache/aws_pylambda_sam_builder).
  * If missing, it downloads the wheel with pip download (using --only-binary=:all:, --platform, --abi, --implementation, and --python-version) into the cache folder.
  * The wheel is then unpacked (using the "unzip" command) into an "unpacked_wheel" subdirectory and metadata is stored.
  * Finally, it symlinks the contents of each unpacked wheel, and the project files (except requirements.txt), into the destination AWS build directory.
  
Logging:
  * Uses logging.info/debug/error to indicate progress or errors.
  
Note: The code crashes on errors (other than "no package found" from pip download, which logs and exits with status 1).
Note: While we do support ';'-style comments, line continuation format is not supported. This example, in the format generated 
by poetry, is NOT OKAY:

  structlog==1.2.3 ; hash=0xdeadbeef \
     hash=0xcafebabe \
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys

from typing import NamedTuple

__all__ = ["main"]

# Bundle together the build configuration arguments into a NamedTuple.
class BuildConfig(NamedTuple):
    platform: list[str]
    abi: str
    implementation: str
    python_version: str
    source: str
    destination: str

def setup_logger():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)

def compute_hash(requirement: str, config: BuildConfig) -> str:
    """
    Compute a SHA256 hash based on the requirement and architecture fields.
    """
    key = f"{requirement.strip()}|{'.'.join(config.platform)}|{config.abi}|{config.implementation}|{config.python_version}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def process_requirement(requirement: str, config: BuildConfig, cache_dir: str, logger: logging.Logger) -> str:
    """
    Process a single requirement:
      * Compute its hash.
      * If not cached, download the wheel via pip and unpack it using unzip.
      * Save metadata to the cache.
    
    Returns the cache folder path for this requirement.
    """
    req_hash = compute_hash(requirement, config)
    hash_dir = os.path.join(cache_dir, req_hash)
    metadata_dir = os.path.join(hash_dir, "metadata")
    unpacked_dir = os.path.join(hash_dir, "unpacked_wheel")

    if os.path.exists(hash_dir):
        logger.info("Using cached wheel for requirement: %s", requirement.strip())
        return hash_dir

    logger.info("Caching wheel for requirement: %s", requirement.strip())
    os.makedirs(metadata_dir, exist_ok=True)
    os.makedirs(unpacked_dir, exist_ok=True)

    # Build the pip download command.
    # Note: if --platform is a comma-separated list, pass as-is.
    platform_args = []
    for platform in config.platform:
        platform_args.append("--platform")
        platform_args.append(platform)
    cmd = [
        "pip", "download",
        "--only-binary=:all:",
        *platform_args,
        "--abi", config.abi,
        "--implementation", config.implementation,
        "--python-version", config.python_version,
        requirement.strip(),
        "--no-deps",
        "-d", hash_dir,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.error("pip download failed for requirement %s", requirement.strip(), exc_info=e)
        sys.exit(1)

    # Look for the downloaded wheel file.
    wheel_files = [f for f in os.listdir(hash_dir) if f.endswith(".whl")]
    if not wheel_files:
        logger.error("No wheel file found for requirement %s", requirement.strip())
        sys.exit(1)
    (wheel_file,) = wheel_files
    wheel_file = os.path.join(hash_dir, wheel_file)
    logger.info("Unpacking wheel: %s", wheel_file)
    subprocess.run(["unzip", "-o", wheel_file, "-d", unpacked_dir],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Save metadata: include the original requirement and architecture fields.
    metadata = {
        "requirement": requirement.strip(),
        "platform": config.platform,
        "abi": config.abi,
        "implementation": config.implementation,
        "python_version": config.python_version,
        "wheel_file": wheel_file
    }
    metadata_file = os.path.join(metadata_dir, "metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f)
    logger.info("Cached wheel for %s at %s", requirement.strip(), hash_dir)

    return hash_dir

def symlink_directory_contents(src_dir: str, dest_dir: str, logger: logging.Logger) -> None:
    """
    Create symlinks in the destination directory for every file/directory in src_dir.
    """
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        src_item = os.path.join(src_dir, item)
        dest_item = os.path.join(dest_dir, item)
        if os.path.lexists(dest_item):
            os.remove(dest_item)
        try:
            os.symlink(src_item, dest_item)
            logger.debug("Symlinked %s -> %s", src_item, dest_item)
        except Exception as e:
            logger.error("Failed to symlink %s to %s", src_item, dest_item, exc_info=e)
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="AWS PyLambda SAM Builder")
    parser.add_argument("--aws-runtime", required=True, choices=["py310", "py311", "py312"], 
                        help="Target AWS Lambda Python runtime (py310, py311, py312)")
    parser.add_argument("--aws-architecture", required=True, choices=["x86_64", "arm64"],
                        help="Target AWS Lambda architecture (x86_64, arm64)")
    parser.add_argument("--source", required=True, help="Source project directory")
    parser.add_argument("--destination", required=True, help="Destination AWS build directory")
    args = parser.parse_args()

    logger = setup_logger()
    
    # Check for arm64 support
    if args.aws_architecture == "arm64":
        logger.error("ARM64 architecture is not yet implemented")
        raise NotImplementedError("ARM64 architecture is not yet implemented")
    
    # Map runtime to Python version, ABI, and implementation
    runtime_mapping = {
        "py310": {"python_version": "3.10", "abi": "cp310"},
        "py311": {"python_version": "3.11", "abi": "cp311"},
        "py312": {"python_version": "3.12", "abi": "cp312"},
    }
    
    # Map architecture to platform
    architecture_mapping = {
        "x86_64": ["manylinux2014_x86_64", "manylinux_2_17_x86_64"],
    }
    
    runtime_info = runtime_mapping[args.aws_runtime]
    platforms = architecture_mapping[args.aws_architecture]
    
    config = BuildConfig(
        platform=platforms,
        abi=runtime_info["abi"],
        implementation="cp",  # Always "cp" for CPython
        python_version=runtime_info["python_version"],
        source=args.source,
        destination=args.destination,
    )

    # Set up the global cache directory.
    cache_dir = os.path.expanduser("~/.cache/aws_pylambda_sam_builder")
    os.makedirs(cache_dir, exist_ok=True)

    # Read the requirements.txt from the source directory.
    req_file = os.path.join(config.source, "requirements.txt")
    if not os.path.exists(req_file):
        logger.error("requirements.txt not found in source directory: %s", config.source)
        sys.exit(1)

    try:
        with open(req_file, "r") as f:
            # Skip empty lines and comments.
            requirements = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            requirements = [line.split(";")[0] for line in requirements]
    except Exception as e:
        logger.error("Error reading requirements.txt", exc_info=e)
        sys.exit(1)

    # Process each requirement.
    cached_dirs = []
    for req in requirements:
        cached_dir = process_requirement(req, config, cache_dir, logger)
        cached_dirs.append(cached_dir)

    # Symlink each requirement's unpacked wheel into the destination directory.
    logger.info("Symlinking requirement wheels to destination: %s", config.destination)
    for cache_folder in cached_dirs:
        unpacked = os.path.join(cache_folder, "unpacked_wheel")
        if os.path.exists(unpacked):
            symlink_directory_contents(unpacked, config.destination, logger)
        else:
            logger.error("Unpacked wheel folder missing in cache: %s", cache_folder)
            sys.exit(1)

    # Symlink the project files (excluding requirements.txt) to the destination.
    logger.info("Symlinking project files to destination: %s", config.destination)
    for item in os.listdir(config.source):
        if item == "requirements.txt":
            continue
        src_item = os.path.join(config.source, item)
        # Convert to absolute path to ensure symlinks are absolute
        src_item_abs = os.path.abspath(src_item)
        dest_item = os.path.join(config.destination, item)
        if os.path.lexists(dest_item):
            os.remove(dest_item)
        try:
            os.symlink(src_item_abs, dest_item)
            logger.debug("Symlinked project file %s -> %s", src_item_abs, dest_item)
        except Exception as e:
            logger.error("Failed to symlink project file %s to %s", src_item_abs, dest_item, exc_info=e)
            sys.exit(1)

    logger.info("Build completed successfully.")

if __name__ == "__main__":
    main()
