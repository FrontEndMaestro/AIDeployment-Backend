"""
Test script to verify port detection flow works correctly.
Tests: .env parsing -> source code scanning -> framework defaults
"""
import os
import tempfile
import shutil
from app.utils.command_extractor import (
    extract_port_from_project,
    _parse_env_for_port,
    _scan_source_for_port
)

def test_env_port_detection():
    """Test that PORT from .env is correctly detected."""
    test_dir = tempfile.mkdtemp(prefix="port_test_")
    try:
        # Create .env with PORT=4000
        with open(os.path.join(test_dir, ".env"), "w") as f:
            f.write("PORT=4000\nNODE_ENV=production\n")
        
        # Test _parse_env_for_port
        port = _parse_env_for_port(test_dir)
        assert port == 4000, f"Expected 4000, got {port}"
        print("✅ Test 1 PASSED: .env PORT=4000 detected correctly")
        
        # Test extract_port_from_project
        result = extract_port_from_project(test_dir, "Express.js", "JavaScript")
        assert result["port"] == 4000, f"Expected 4000, got {result['port']}"
        assert result["source"] == "env", f"Expected 'env', got {result['source']}"
        print("✅ Test 2 PASSED: extract_port_from_project returns {port: 4000, source: 'env'}")
        
    finally:
        shutil.rmtree(test_dir)

def test_source_code_port_detection():
    """Test that port from source code is detected when no .env."""
    test_dir = tempfile.mkdtemp(prefix="port_test_")
    try:
        # Create server.js with app.listen(5000)
        with open(os.path.join(test_dir, "server.js"), "w") as f:
            f.write("const app = require('express')();\napp.listen(5000);\n")
        
        # Test _scan_source_for_port
        port = _scan_source_for_port(test_dir, "JavaScript")
        assert port == 5000, f"Expected 5000, got {port}"
        print("✅ Test 3 PASSED: source code port 5000 detected from server.js")
        
        # Test extract_port_from_project (no .env, should use source)
        result = extract_port_from_project(test_dir, "Express.js", "JavaScript")
        assert result["port"] == 5000, f"Expected 5000, got {result['port']}"
        assert result["source"] == "source", f"Expected 'source', got {result['source']}"
        print("✅ Test 4 PASSED: extract_port_from_project returns {port: 5000, source: 'source'}")
        
    finally:
        shutil.rmtree(test_dir)

def test_default_port_fallback():
    """Test that framework default is used when no .env and no source code port."""
    test_dir = tempfile.mkdtemp(prefix="port_test_")
    try:
        # Create empty package.json
        with open(os.path.join(test_dir, "package.json"), "w") as f:
            f.write('{"name": "test"}\n')
        
        # Test extract_port_from_project (no .env, no source port)
        result = extract_port_from_project(test_dir, "Express.js", "JavaScript")
        assert result["port"] == 3000, f"Expected 3000 (Express default), got {result['port']}"
        assert result["source"] == "default", f"Expected 'default', got {result['source']}"
        print("✅ Test 5 PASSED: extract_port_from_project returns {port: 3000, source: 'default'}")
        
    finally:
        shutil.rmtree(test_dir)

def test_env_priority_over_source():
    """Test that .env port takes priority over source code port."""
    test_dir = tempfile.mkdtemp(prefix="port_test_")
    try:
        # Create .env with PORT=4000
        with open(os.path.join(test_dir, ".env"), "w") as f:
            f.write("PORT=4000\n")
        
        # Create server.js with app.listen(5000)
        with open(os.path.join(test_dir, "server.js"), "w") as f:
            f.write("const app = require('express')();\napp.listen(5000);\n")
        
        # .env should take priority
        result = extract_port_from_project(test_dir, "Express.js", "JavaScript")
        assert result["port"] == 4000, f"Expected 4000 (.env), got {result['port']}"
        assert result["source"] == "env", f"Expected 'env', got {result['source']}"
        print("✅ Test 6 PASSED: .env PORT takes priority over source code port")
        
    finally:
        shutil.rmtree(test_dir)

if __name__ == "__main__":
    print("\n=== Port Detection Flow Tests ===\n")
    test_env_port_detection()
    test_source_code_port_detection()
    test_default_port_fallback()
    test_env_priority_over_source()
    print("\n✅ All 6 tests passed! Port detection flow works correctly.\n")
