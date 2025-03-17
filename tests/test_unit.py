# AI-generated tests, probably crashes at any modification :-(
import os
import sys
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

# Add the src directory to the path so we can import the package
#sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
        source="/fake/source",
        destination="/fake/destination"
    )

@pytest.fixture
def mock_cache_dir(monkeypatch, tmp_path):
    """Create a temporary directory for the cache"""
    monkeypatch.setattr("os.path.expanduser", lambda path: str(tmp_path) if "~" in path else path)
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
@patch("os.path.exists")
@patch("os.makedirs")
def test_process_requirement_cached(mock_makedirs, mock_exists, build_config):
    mock_exists.return_value = True
    
    requirement = "requests==2.28.1"
    cache_dir = "/fake/cache"
    logger = MagicMock()
    
    result = process_requirement(requirement, build_config, cache_dir, logger)
    
    # Verify correct hash directory is returned
    hash_value = compute_hash(requirement, build_config)
    expected_dir = f"/fake/cache/{hash_value}"
    assert result == expected_dir
    
    # Verify log message
    logger.info.assert_called_with("Using cached wheel for requirement: %s", requirement.strip())
    
    # Verify no directories were created
    mock_makedirs.assert_not_called()

# Test process_requirement function with new wheel
@patch("os.path.exists")
@patch("os.makedirs")
@patch("os.listdir")
@patch("subprocess.run")
@patch("builtins.open", new_callable=mock_open)
def test_process_requirement_new_wheel(mock_file, mock_run, mock_listdir, 
                                      mock_makedirs, mock_exists, build_config):
    # Set up mocks
    mock_exists.return_value = False
    mock_listdir.return_value = ["package-1.0-py3-none-any.whl"]
    
    requirement = "package==1.0"
    cache_dir = "/fake/cache"
    logger = MagicMock()
    
    result = process_requirement(requirement, build_config, cache_dir, logger)
    
    # Verify correct hash directory is returned
    hash_value = compute_hash(requirement, build_config)
    expected_dir = f"/fake/cache/{hash_value}"
    assert result == expected_dir
    
    # Verify directories were created
    assert mock_makedirs.call_count == 2
    
    # Verify pip command was run
    assert mock_run.call_count == 2
    
    # Verify metadata was saved
    mock_file.assert_called()

# Test symlink_directory_contents function
@patch("os.path.exists")
@patch("os.makedirs")
@patch("os.listdir")
@patch("os.path.lexists")
@patch("os.remove")
@patch("os.symlink")
def test_symlink_directory_contents(mock_symlink, mock_remove, mock_lexists, 
                                   mock_listdir, mock_makedirs, mock_exists):
    mock_exists.return_value = True
    mock_lexists.return_value = True
    mock_listdir.return_value = ["file1.py", "file2.py"]
    
    src_dir = "/fake/source"
    dest_dir = "/fake/destination"
    logger = MagicMock()
    
    symlink_directory_contents(src_dir, dest_dir, logger)
    
    # Verify existing files were removed
    assert mock_remove.call_count == 2
    
    # Verify symlinks were created
    assert mock_symlink.call_count == 2
    
    # Check symlink calls
    mock_symlink.assert_any_call("/fake/source/file1.py", "/fake/destination/file1.py")
    mock_symlink.assert_any_call("/fake/source/file2.py", "/fake/destination/file2.py")

# Test main function with mocks
@patch("argparse.ArgumentParser")
@patch("os.path.exists")
@patch("os.makedirs")
@patch("os.listdir")
@patch("os.path.lexists")
@patch("os.remove")
@patch("os.symlink")
@patch("builtins.open", new_callable=mock_open, read_data="requests==2.28.1\nflask==2.0.1\n")
def test_main(mock_file, mock_symlink, mock_remove, mock_lexists, 
             mock_listdir, mock_makedirs, mock_exists, mock_parser):
    # Set up ArgumentParser mock
    parser_instance = mock_parser.return_value
    parser_instance.parse_args.return_value = MagicMock(
        aws_runtime="py311",
        aws_architecture="x86_64",
        source="/fake/source",
        destination="/fake/destination"
    )
    
    mock_exists.return_value = True
    mock_lexists.return_value = False
    mock_listdir.side_effect = [
        ["package-1.0-py3-none-any.whl"],  # For the wheel directory
        ["unpacked_wheel"],  # For the cache directory contents
        ["file1.py", "file2.py", "requirements.txt"]  # For the source directory
    ]
    
    # Need to patch process_requirement separately
    with patch("aws_pylambda_sam_builder.process_requirement") as mock_process:
        mock_process.side_effect = ["/fake/cache/hash1", "/fake/cache/hash2"]
        
        # Run the main function
        main()
        
        # Verify process_requirement was called twice (for the two requirements)
        assert mock_process.call_count == 2

if __name__ == "__main__":
    pytest.main(["-xvs", __file__]) 