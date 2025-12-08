"""
Test script for MERN project metadata detection.
Tests against various MERN project structures from GitHub.
"""
import os
import json
import shutil
import tempfile
from app.utils.command_extractor import (
    extract_nodejs_commands,
    extract_port_from_project,
    extract_frontend_port,
    extract_database_info
)


# Test cases based on real GitHub MERN projects
TEST_CASES = [
    {
        "name": "MERN Memories - CRA Frontend",
        "description": "Create React App frontend with react-scripts",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "mern-stack-client",
                "proxy": "http://localhost:5000",
                "dependencies": {
                    "@material-ui/core": "^4.9.10",
                    "axios": "^0.19.2",
                    "react": "^16.12.0",
                    "react-dom": "^16.12.0",
                    "react-scripts": "3.4.1",
                    "redux": "^4.0.5"
                },
                "scripts": {
                    "start": "react-scripts start",
                    "build": "react-scripts build",
                    "test": "react-scripts test"
                }
            }
        },
        "expected": {
            "build_output": "build",
            "port": 3000,
            "port_source": "cra_default",
            "start_command": "npm start",
            "has_start_script": True
        }
    },
    {
        "name": "IDURAR ERP - Vite Frontend",
        "description": "Vite-based React frontend",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "idurar-erp-crm",
                "dependencies": {
                    "react": "^18.3.1",
                    "react-dom": "^18.2.0",
                    "vite": "^5.4.8",
                    "axios": "^1.6.2"
                },
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview"
                }
            }
        },
        "expected": {
            "build_output": "dist",
            "port": 5173,
            "port_source": "vite_default",
            "start_command": None,  # No start script
            "has_start_script": False
        }
    },
    {
        "name": "MERN Memories - Express Backend",
        "description": "Express backend with mongoose, nodemon start, hardcoded port",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "mern-stack-api",
                "main": "index.js",
                "scripts": {
                    "start": "nodemon index.js"
                },
                "dependencies": {
                    "express": "^4.17.1",
                    "mongoose": "^5.9.29",
                    "cors": "^2.8.5"
                }
            },
            "index.js": '''
import express from 'express';
import mongoose from 'mongoose';
const app = express();
const PORT = process.env.PORT|| 5000;
mongoose.connect(CONNECTION_URL)
  .then(() => app.listen(PORT, () => console.log('Server Running')))
'''
        },
        "expected": {
            "build_output": None,
            "port": 5000,
            "port_source": "source",  # From source code scanning
            "start_command": "node index.js",  # nodemon converted to node
            "entry_point": "index.js",
            "has_start_script": True,
            "db_type": "mongodb",
            "needs_container": False  # No .env with local mongo URL
        }
    },
    {
        "name": "IDURAR ERP - Express Backend",
        "description": "Express backend with node start script",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "idurar-erp-crm",
                "main": "server.js",
                "scripts": {
                    "start": "node src/server.js",
                    "dev": "nodemon src/server.js"
                },
                "dependencies": {
                    "express": "^4.18.2",
                    "mongoose": "^8.1.1",
                    "dotenv": "16.3.1"
                }
            },
            ".env": "PORT=8888\nMONGO_URI=mongodb://localhost:27017/idurar"
        },
        "expected": {
            "build_output": None,
            "port": 8888,
            "port_source": "env",  # From .env file
            "start_command": "node src/server.js",
            "entry_point": "src/server.js",
            "has_start_script": True,
            "db_type": "mongodb",
            "is_cloud": False,
            "needs_container": True  # Local mongo
        }
    },
    {
        "name": "Next.js Frontend",
        "description": "Next.js with static export",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "nextjs-app",
                "dependencies": {
                    "next": "^14.0.0",
                    "react": "^18.0.0",
                    "react-dom": "^18.0.0"
                },
                "scripts": {
                    "dev": "next dev",
                    "build": "next build && next export",
                    "start": "next start"
                }
            }
        },
        "expected": {
            "build_output": "out",  # next export outputs to out/
            "port": 3000,
            "port_source": "next_default",
            "start_command": "npm start",
            "has_start_script": True
        }
    },
    {
        "name": "Vite React with Custom Port",
        "description": "Vite frontend with custom port in config",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "custom-vite-app",
                "dependencies": {
                    "react": "^18.0.0",
                    "vite": "^5.0.0"
                },
                "scripts": {
                    "dev": "vite",
                    "build": "vite build"
                }
            },
            "vite.config.js": '''
export default {
  server: {
    port: 3001
  },
  build: {
    outDir: 'public'
  }
}
'''
        },
        "expected": {
            "build_output": "public",  # Custom outDir
            "port": 3001,  # Custom port from config
            "port_source": "vite.config.js",
            "start_command": None,
            "has_start_script": False
        }
    },
    {
        "name": "Express with Cloud MongoDB",
        "description": "Express backend with MongoDB Atlas connection",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "cloud-mongo-app",
                "scripts": {
                    "start": "node server.js"
                },
                "dependencies": {
                    "express": "^4.18.0",
                    "mongoose": "^7.0.0"
                }
            },
            "server.js": '''
const express = require('express');
const app = express();
app.listen(4000);
''',
            ".env": "MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/mydb"
        },
        "expected": {
            "port": 4000,
            "port_source": "source",
            "start_command": "node server.js",
            "entry_point": "server.js",
            "db_type": "mongodb",
            "is_cloud": True,
            "needs_container": False  # Cloud DB - no container needed
        }
    },
    {
        "name": "Express with PostgreSQL",
        "description": "Express backend with PostgreSQL",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "postgres-app",
                "scripts": {
                    "start": "node app.js"
                },
                "dependencies": {
                    "express": "^4.18.0",
                    "pg": "^8.0.0"
                }
            },
            "app.js": "const app = require('express')();\napp.listen(5432);",
            ".env": "DATABASE_URL=postgres://user:pass@localhost:5432/mydb"
        },
        "expected": {
            "port": 5432,  # From source
            "port_source": "source",
            "db_type": "postgresql",
            "is_cloud": False,
            "needs_container": True
        }
    }
]


def create_test_project(test_case, base_dir):
    """Create a temporary project structure for testing."""
    project_dir = os.path.join(base_dir, test_case["name"].replace(" ", "_"))
    os.makedirs(project_dir, exist_ok=True)
    
    for filename, content in test_case["files"].items():
        filepath = os.path.join(project_dir, filename)
        if isinstance(content, dict):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
    
    return project_dir


def run_detection(project_dir, test_type):
    """Run all detection functions on a project."""
    results = {}
    
    # Run Node.js command extraction
    nodejs_cmds = extract_nodejs_commands(project_dir)
    results["build_output"] = nodejs_cmds.get("build_output")
    results["start_command"] = nodejs_cmds.get("start_command")
    results["entry_point"] = nodejs_cmds.get("entry_point")
    results["has_start_script"] = nodejs_cmds.get("has_start_script")
    results["build_command"] = nodejs_cmds.get("build_command")
    
    # Run port detection
    if test_type == "frontend":
        port_info = extract_frontend_port(project_dir)
    else:
        port_info = extract_port_from_project(project_dir, "Express.js", "JavaScript")
    
    results["port"] = port_info.get("port")
    results["port_source"] = port_info.get("source")
    
    # Run database detection
    db_info = extract_database_info(project_dir, "MongoDB")
    results["db_type"] = db_info.get("db_type")
    results["is_cloud"] = db_info.get("is_cloud")
    results["needs_container"] = db_info.get("needs_container")
    
    return results


def compare_results(expected, actual, test_name):
    """Compare expected vs actual results."""
    issues = []
    matches = []
    
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if expected_value == actual_value:
            matches.append(f"[PASS] {key}: {actual_value}")
        else:
            issues.append(f"[FAIL] {key}: expected={expected_value}, actual={actual_value}")
    
    return matches, issues


def run_tests():
    """Run all test cases and output results."""
    print("=" * 80)
    print("MERN PROJECT METADATA DETECTION TEST RESULTS")
    print("=" * 80)
    print()
    
    all_issues = []
    total_tests = 0
    passed_tests = 0
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for test_case in TEST_CASES:
            print(f"\n{'='*60}")
            print(f"TEST: {test_case['name']}")
            print(f"Description: {test_case['description']}")
            print(f"Type: {test_case['type']}")
            print("-" * 60)
            
            # Create test project
            project_dir = create_test_project(test_case, temp_dir)
            
            # Run detection
            actual = run_detection(project_dir, test_case["type"])
            
            # Compare results
            matches, issues = compare_results(test_case["expected"], actual, test_case["name"])
            
            # Print results
            print("\nRESULTS:")
            for match in matches:
                print(f"  {match}")
            for issue in issues:
                print(f"  {issue}")
            
            total_tests += len(test_case["expected"])
            passed_tests += len(matches)
            
            if issues:
                all_issues.append({
                    "test": test_case["name"],
                    "issues": issues
                })
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total checks: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {passed_tests/total_tests*100:.1f}%")
    
    if all_issues:
        print("\n" + "-" * 40)
        print("ISSUES TO ADDRESS:")
        for issue_group in all_issues:
            print(f"\n{issue_group['test']}:")
            for issue in issue_group["issues"]:
                print(f"  {issue}")
    
    return all_issues


if __name__ == "__main__":
    issues = run_tests()
    
    print("\n" + "=" * 80)
    print("SUGGESTIONS FOR METADATA LOGIC IMPROVEMENTS")
    print("=" * 80)
    
    suggestions = []
    
    # Analyze issues and generate suggestions
    for issue_group in issues:
        for issue in issue_group["issues"]:
            if "port_source" in issue and "vite.config" in issue:
                suggestions.append(
                    "- Frontend port detection from vite.config.js is not working correctly"
                )
            if "build_output" in issue and "public" in issue:
                suggestions.append(
                    "- Custom outDir in vite.config.js is not being parsed correctly"
                )
            if "db_type" in issue:
                suggestions.append(
                    "- Database type detection needs improvement for certain patterns"
                )
    
    if suggestions:
        for s in set(suggestions):
            print(s)
    else:
        print("No major improvements needed based on test results.")
