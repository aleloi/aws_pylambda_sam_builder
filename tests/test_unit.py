# AI-generated tests, probably crashes at any modification :-(
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, Mock
import subprocess
import shutil

from aws_pylambda_sam_builder import (
    compute_hash, 
    process_requirement, 
    symlink_directory_contents, 
    BuildConfig,
    main
)

# Test data
@pytest.fixture
def build_config():
    return BuildConfig(
        platform=["manylinux2014_x86_64", "manylinux_2_17_x86_64"],
        abi="cp311",
        implementation="cp",
        python_version="3.11",
        source=Path("/fake/source"),
        destination=Path("/fake/destination")
    )

@pytest.fixture
def mock_cache_dir(monkeypatch, tmp_path):
    """Create a temporary directory for the cache"""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return tmp_path

# Test compute_hash function
def test_compute_hash(build_config):
    requirement = "requests==2.28.1"
    hash_value = compute_hash(requirement, build_config)
    
    # Verify the hash is a valid SHA256 hash (64 characters)
    assert len(hash_value) == 64
    assert all(c in "0123456789abcdef" for c in hash_value)
    
    # Verify the same input produces the same hash
    assert compute_hash(requirement, build_config) == hash_value
    
    # Verify different input produces different hash
    different_req = "flask==2.0.1"
    assert compute_hash(different_req, build_config) != hash_value

# Test process_requirement function with existing cache
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
@patch("aws_pylambda_sam_builder.FileLock")
def test_process_requirement_cached(mock_filelock, mock_mkdir, mock_exists, build_config):
    mock_exists.return_value = True
    
    # Set up FileLock mock to be used as a context manager
    mock_lock_instance = MagicMock()
    mock_filelock.return_value = mock_lock_instance
    
    requirement = "requests==2.28.1"
    cache_dir = Path("/fake/cache")
    logger = MagicMock()
    
    result = process_requirement(requirement, build_config, cache_dir, logger)
    
    # Verify correct hash directory is returned
    hash_value = compute_hash(requirement, build_config)
    expected_dir = Path("/fake/cache") / hash_value
    assert result == expected_dir
    
    # Verify log message
    logger.info.assert_called_with("Another process created the cache for: %s", requirement.strip())
    
    # Verify no directories were created
    mock_mkdir.assert_not_called()

# Test process_requirement function with new wheel
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
@patch("pathlib.Path.glob")
@patch("subprocess.run")
@patch("pathlib.Path.write_text")
@patch("aws_pylambda_sam_builder.FileLock")
def test_process_requirement_new_wheel(mock_filelock, mock_write_text, mock_run, mock_glob, 
                                      mock_mkdir, mock_exists, build_config):
    # Set up mocks
    mock_exists.return_value = False
    mock_glob.return_value = [Path("package-1.0-py3-none-any.whl")]
    
    # Set up FileLock mock to be used as a context manager
    mock_lock_instance = MagicMock()
    mock_filelock.return_value = mock_lock_instance
    
    requirement = "package==1.0"
    cache_dir = Path("/fake/cache")
    logger = MagicMock()
    
    result = process_requirement(requirement, build_config, cache_dir, logger)
    
    # Verify correct hash directory is returned
    hash_value = compute_hash(requirement, build_config)
    expected_dir = Path("/fake/cache") / hash_value
    assert result == expected_dir
    
    # Verify directories were created
    assert mock_mkdir.call_count == 2
    
    # Verify pip command was run
    assert mock_run.call_count == 2
    
    # Verify metadata was saved
    mock_write_text.assert_called()

# Test process_requirement function with error after directory creation
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
@patch("pathlib.Path.glob")
@patch("subprocess.run")
@patch("pathlib.Path.write_text")
@patch("aws_pylambda_sam_builder.FileLock")
@patch("shutil.rmtree")
def test_process_requirement_error_cleanup(mock_rmtree, mock_filelock, mock_write_text, mock_run, 
                                         mock_glob, mock_mkdir, mock_exists, build_config):
    # Set up mocks
    mock_exists.return_value = False
    mock_glob.return_value = [Path("package-1.0-py3-none-any.whl")]
    
    # Set up FileLock mock to be used as a context manager
    mock_lock_instance = MagicMock()
    mock_filelock.return_value = mock_lock_instance
    
    # Make subprocess.run raise an exception after first successful call
    mock_run.side_effect = [
        MagicMock(),  # First call succeeds (pip download)
        subprocess.CalledProcessError(1, "unzip", "Failed to unzip")  # Second call fails
    ]
    
    requirement = "package==1.0"
    cache_dir = Path("/fake/cache")
    logger = MagicMock()
    
    # The function should raise the exception
    with pytest.raises(subprocess.CalledProcessError):
        process_requirement(requirement, build_config, cache_dir, logger)
    
    # Verify directories were created
    assert mock_mkdir.call_count == 2
    
    # Verify cleanup was attempted
    hash_value = compute_hash(requirement, build_config)
    expected_dir = cache_dir / hash_value
    mock_rmtree.assert_called_once_with(expected_dir)
    
    # Verify error was logged
    logger.error.assert_called_once()

# Test symlink_directory_contents function
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
@patch("pathlib.Path.iterdir")
@patch("pathlib.Path.unlink")
@patch("pathlib.Path.symlink_to")
def test_symlink_directory_contents(mock_symlink_to, mock_unlink, mock_iterdir, 
                                   mock_mkdir, mock_exists):
    mock_exists.return_value = True
    mock_iterdir.return_value = [Path("file1.py"), Path("file2.py")]
    
    src_dir = Path("/fake/source")
    dest_dir = Path("/fake/destination")
    logger = MagicMock()
    
    symlink_directory_contents(src_dir, dest_dir, logger)
    
    # Verify existing files were removed
    assert mock_unlink.call_count == 2
    
    # Verify symlinks were created
    assert mock_symlink_to.call_count == 2
    
    # Check symlink calls
    mock_symlink_to.assert_any_call(Path("file1.py"))
    mock_symlink_to.assert_any_call(Path("file2.py"))

# Test main function with mocks
@patch("argparse.ArgumentParser")
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
@patch("pathlib.Path.iterdir")
@patch("pathlib.Path.unlink")
@patch("pathlib.Path.symlink_to")
@patch("pathlib.Path.read_text")
def test_main(mock_read_text, mock_symlink_to, mock_unlink, mock_iterdir, 
             mock_mkdir, mock_exists, mock_parser):
    # Set up ArgumentParser mock
    parser_instance = mock_parser.return_value
    parser_instance.parse_args.return_value = MagicMock(
        aws_runtime="py311",
        aws_architecture="x86_64",
        source="/fake/source",
        destination="/fake/destination",
        package_as=None,
    )
    
    mock_exists.return_value = True
    mock_read_text.return_value = "requests==2.28.1\nflask==2.0.1\n"
    mock_iterdir.side_effect = [
        [Path("package-1.0-py3-none-any.whl")],  # For the wheel directory
        [Path("unpacked_wheel")],  # For the cache directory contents
        [Path("file1.py"), Path("file2.py"), Path("requirements.txt")]  # For the source directory
    ]
    
    # Need to patch process_requirement separately
    with patch("aws_pylambda_sam_builder.process_requirement") as mock_process:
        mock_process.side_effect = [Path("/fake/cache/hash1"), Path("/fake/cache/hash2")]
        
        # Run the main function
        main()
        
        # Verify process_requirement was called twice (for the two requirements)
        assert mock_process.call_count == 2

# Test builder exits when --package-as is provided but __init__.py is missing
@patch("argparse.ArgumentParser")
@patch("pathlib.Path.exists")
@patch("pathlib.Path.mkdir")
@patch("pathlib.Path.iterdir")
@patch("pathlib.Path.unlink")
@patch("pathlib.Path.symlink_to")
@patch("pathlib.Path.read_text")
def test_package_as_without_init(mock_read_text, mock_symlink_to, mock_unlink, mock_iterdir, mock_mkdir, mock_exists, mock_parser):
    """Ensure the builder crashes when --package-as is used but __init__.py does not exist in source."""
    # Configure parse_args to include a package_as value
    parser_instance = mock_parser.return_value
    parser_instance.parse_args.return_value = MagicMock(
        aws_runtime="py311",
        aws_architecture="x86_64",
        source="/fake/source",
        destination="/fake/destination",
        package_as="my_pkg",
    )

    # First Path.exists() call is for requirements.txt -> True
    # Second call is for __init__.py -> False
    call_counter = {"i": 0}

    def exists_side_effect(*args, **kwargs):
        call_counter["i"] += 1
        if call_counter["i"] == 1:
            return True  # requirements.txt exists
        if call_counter["i"] == 2:
            return False  # __init__.py missing
        return True

    mock_exists.side_effect = exists_side_effect

    # Provide dummy requirements
    mock_read_text.return_value = "requests==2.28.1\n"

    # Simplify: Path.iterdir is not critical for this failure path.
    mock_iterdir.return_value = []

    # Patch process_requirement to bypass actual logic
    with patch("aws_pylambda_sam_builder.process_requirement") as mock_process:
        mock_process.return_value = Path("/fake/cache/hash1")

        with pytest.raises(SystemExit):
            main()

if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 