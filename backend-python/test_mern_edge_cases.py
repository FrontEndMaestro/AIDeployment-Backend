"""
Edge case tests for MERN project metadata detection.
Tests scenarios that could FAIL in real-world projects.
"""
import os
import json
import tempfile
from app.utils.command_extractor import (
    extract_nodejs_commands,
    extract_port_from_project,
    extract_frontend_port,
    extract_database_info
)


# EDGE CASES that could fail in real projects
EDGE_CASES = [
    # ===== EDGE CASE 1: TypeScript backend with ts-node =====
    {
        "name": "TypeScript Backend (ts-node)",
        "description": "Backend using ts-node for development - common in modern MERN",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "ts-backend",
                "main": "dist/index.js",
                "scripts": {
                    "start": "ts-node src/index.ts",
                    "build": "tsc",
                    "start:prod": "node dist/index.js"
                },
                "dependencies": {
                    "express": "^4.18.0",
                    "mongoose": "^7.0.0"
                },
                "devDependencies": {
                    "ts-node": "^10.9.0",
                    "typescript": "^5.0.0"
                }
            },
            "src/index.ts": "import express from 'express';\nconst app = express();\napp.listen(3001);"
        },
        "expected": {
            "start_command": "npm start",  # ts-node should trigger npm start
            "entry_point": None,  # Can't extract .ts entry easily
            "build_output": "dist",  # TypeScript builds to dist
            "port": 3001  # From src/index.ts
        },
        "potential_issue": "Port detection may miss .ts files, entry_point may not be detected"
    },
    
    # ===== EDGE CASE 2: Monorepo with workspaces =====
    {
        "name": "Monorepo Structure",
        "description": "Project with frontend and backend in separate folders",
        "type": "backend",
        "structure": {
            "project_root": {
                "package.json": {
                    "name": "monorepo",
                    "workspaces": ["frontend", "backend"]
                },
                "backend": {
                    "package.json": {
                        "name": "backend",
                        "scripts": {"start": "node app.js"},
                        "dependencies": {"express": "^4.18.0", "mongoose": "^7.0.0"}
                    },
                    "app.js": "app.listen(5001);",
                    ".env": "PORT=5001\nMONGO_URI=mongodb://localhost:27017/db"
                },
                "frontend": {
                    "package.json": {
                        "name": "frontend",
                        "dependencies": {"react": "^18.0.0", "vite": "^5.0.0"},
                        "scripts": {"build": "vite build"}
                    }
                }
            }
        },
        "expected": {
            "port": 5001,
            "port_source": "env",
            "build_output": None  # Backend has no build
        },
        "potential_issue": "Detection may pick up root package.json instead of backend/"
    },
    
    # ===== EDGE CASE 3: Complex start script =====
    {
        "name": "Complex Start Script",
        "description": "Start script with environment variables and options",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "complex-app",
                "scripts": {
                    "start": "NODE_ENV=production node --max-old-space-size=4096 server/index.js",
                    "dev": "nodemon --watch server server/index.js"
                },
                "dependencies": {
                    "express": "^4.18.0"
                }
            },
            "server/index.js": "const PORT = process.env.PORT || 8080;\napp.listen(PORT);"
        },
        "expected": {
            "start_command": "npm start",  # Complex script should use npm start
            "entry_point": "server/index.js",  # Should extract from complex script
            "port": 8080  # From server/index.js
        },
        "potential_issue": "Entry point extraction may fail with env vars prefix"
    },
    
    # ===== EDGE CASE 4: Port only in environment variable =====
    {
        "name": "Port Only From process.env",
        "description": "No hardcoded port, only process.env.PORT",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "env-port-app",
                "scripts": {"start": "node index.js"},
                "dependencies": {"express": "^4.18.0"}
            },
            "index.js": "const port = process.env.PORT;\napp.listen(port);",
            ".env.example": "PORT=3000"
        },
        "expected": {
            "port": 3000,  # Should detect from .env.example
            "port_source": "env"
        },
        "potential_issue": ".env.example may not be checked, would fall back to default"
    },
    
    # ===== EDGE CASE 5: Remix framework =====
    {
        "name": "Remix Framework",
        "description": "Remix.js project (not in detection list)",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "remix-app",
                "dependencies": {
                    "@remix-run/node": "^2.0.0",
                    "@remix-run/react": "^2.0.0",
                    "react": "^18.0.0"
                },
                "scripts": {
                    "build": "remix build",
                    "dev": "remix dev",
                    "start": "remix-serve build"
                }
            }
        },
        "expected": {
            "build_output": "build",  # Remix outputs to build/
            "port": 3000,
            "has_start_script": True
        },
        "potential_issue": "Remix not detected, will default to 'dist' for build_output"
    },
    
    # ===== EDGE CASE 6: SvelteKit project =====
    {
        "name": "SvelteKit Project",
        "description": "Svelte with SvelteKit adapter",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "sveltekit-app",
                "dependencies": {
                    "@sveltejs/kit": "^2.0.0",
                    "svelte": "^4.0.0"
                },
                "devDependencies": {
                    "vite": "^5.0.0"
                },
                "scripts": {
                    "build": "vite build",
                    "dev": "vite dev"
                }
            }
        },
        "expected": {
            "build_output": "dist",  # Vite detected
            "port": 5173
        },
        "potential_issue": "SvelteKit builds to .svelte-kit/output, not dist"
    },
    
    # ===== EDGE CASE 7: Custom Webpack without config file =====
    {
        "name": "Webpack Without Config",
        "description": "Webpack project without visible config",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "webpack-app",
                "dependencies": {
                    "react": "^18.0.0",
                    "react-dom": "^18.0.0"
                },
                "devDependencies": {
                    "webpack": "^5.0.0",
                    "webpack-cli": "^5.0.0"
                },
                "scripts": {
                    "build": "webpack --config configs/webpack.prod.js"
                }
            },
            "configs/webpack.prod.js": "output: { path: path.resolve(__dirname, '../public') }"
        },
        "expected": {
            "build_output": "public",  # From nested config
            "port": 3000
        },
        "potential_issue": "Config in nested folder won't be detected"
    },
    
    # ===== EDGE CASE 8: Backend with no start script =====
    {
        "name": "Backend No Start Script",
        "description": "CLI tool or library with only main field",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "cli-tool",
                "main": "lib/cli.js",
                "bin": {"mytool": "lib/cli.js"},
                "dependencies": {"express": "^4.18.0"}
            },
            "lib/cli.js": "#!/usr/bin/env node\napp.listen(9000);"
        },
        "expected": {
            "start_command": "node lib/cli.js",  # From main field
            "entry_point": "lib/cli.js",
            "port": 9000,
            "has_start_script": False
        },
        "potential_issue": "lib/ folder not in source scan list"
    },
    
    # ===== EDGE CASE 9: Multiple databases =====
    {
        "name": "Multiple Databases",
        "description": "Project using both MongoDB and Redis",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "multi-db-app",
                "scripts": {"start": "node server.js"},
                "dependencies": {
                    "express": "^4.18.0",
                    "mongoose": "^7.0.0",
                    "redis": "^4.0.0"
                }
            },
            "server.js": "app.listen(4000);",
            ".env": "MONGO_URI=mongodb://localhost:27017/db\nREDIS_URL=redis://localhost:6379"
        },
        "expected": {
            "db_type": "mongodb",  # Only first DB detected
            "needs_container": True
        },
        "potential_issue": "Only one database detected, Redis container won't be added"
    },
    
    # ===== EDGE CASE 10: Gatsby Static Site =====
    {
        "name": "Gatsby Static Site",
        "description": "Gatsby project with custom output",
        "type": "frontend",
        "files": {
            "package.json": {
                "name": "gatsby-site",
                "dependencies": {
                    "gatsby": "^5.0.0",
                    "react": "^18.0.0"
                },
                "scripts": {
                    "build": "gatsby build",
                    "develop": "gatsby develop"
                }
            }
        },
        "expected": {
            "build_output": "public",  # Gatsby outputs to public/
            "port": 8000,  # Gatsby default
            "has_start_script": False
        },
        "potential_issue": "Gatsby not detected, defaults to dist"
    },
    
    # ===== EDGE CASE 11: Express with PM2 =====
    {
        "name": "Express with PM2",
        "description": "Production setup using PM2 process manager",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "pm2-app",
                "scripts": {
                    "start": "pm2 start ecosystem.config.js",
                    "dev": "nodemon src/app.js"
                },
                "dependencies": {
                    "express": "^4.18.0"
                }
            },
            "ecosystem.config.js": "module.exports = { apps: [{ script: 'src/app.js', env: { PORT: 3300 } }] }",
            "src/app.js": "const PORT = process.env.PORT || 3000;\napp.listen(PORT);"
        },
        "expected": {
            "start_command": "npm start",  # PM2 can't be simplified
            "port": 3000,  # From source (ecosystem.config.js not parsed)
            "entry_point": "src/app.js"  # Should detect from dev script
        },
        "potential_issue": "PM2 ecosystem config not parsed for port"
    },
    
    # ===== EDGE CASE 12: Port in JSON config file =====
    {
        "name": "Port in Config File",
        "description": "Port defined in a config.json",
        "type": "backend",
        "files": {
            "package.json": {
                "name": "config-port-app",
                "scripts": {"start": "node index.js"},
                "dependencies": {"express": "^4.18.0"}
            },
            "index.js": "const config = require('./config');\napp.listen(config.port);",
            "config.json": {"port": 7777, "host": "0.0.0.0"}
        },
        "expected": {
            "port": 3000,  # Will fall back to default
            "port_source": "default"
        },
        "potential_issue": "Port in JSON config files is not detected"
    }
]


def create_project_files(files_dict, base_path):
    """Recursively create project files from dictionary."""
    for name, content in files_dict.items():
        path = os.path.join(base_path, name)
        if isinstance(content, dict) and not any(k in content for k in ['name', 'version', 'dependencies', 'scripts', 'port']):
            # It's a directory
            os.makedirs(path, exist_ok=True)
            create_project_files(content, path)
        else:
            # It's a file
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
            if isinstance(content, dict):
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=2)
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(str(content))


def run_detection(project_dir, test_type, expected):
    """Run detection and return comparison."""
    results = {}
    issues = []
    
    # Run Node.js command extraction
    nodejs_cmds = extract_nodejs_commands(project_dir)
    
    # Check each expected field
    field_map = {
        "build_output": nodejs_cmds.get("build_output"),
        "start_command": nodejs_cmds.get("start_command"),
        "entry_point": nodejs_cmds.get("entry_point"),
        "has_start_script": nodejs_cmds.get("has_start_script"),
        "build_command": nodejs_cmds.get("build_command"),
    }
    
    # Port detection
    if test_type == "frontend":
        port_info = extract_frontend_port(project_dir)
    else:
        port_info = extract_port_from_project(project_dir, "Express.js", "JavaScript")
    
    field_map["port"] = port_info.get("port")
    field_map["port_source"] = port_info.get("source")
    
    # Database detection
    db_info = extract_database_info(project_dir, "MongoDB")
    field_map["db_type"] = db_info.get("db_type")
    field_map["is_cloud"] = db_info.get("is_cloud")
    field_map["needs_container"] = db_info.get("needs_container")
    
    # Compare
    for key, exp_value in expected.items():
        actual = field_map.get(key)
        status = "PASS" if exp_value == actual else "FAIL"
        results[key] = {
            "expected": exp_value,
            "actual": actual,
            "status": status
        }
        if status == "FAIL":
            issues.append(f"{key}: expected={exp_value}, actual={actual}")
    
    return results, issues


def run_edge_case_tests():
    """Run all edge case tests."""
    print("=" * 80)
    print("MERN METADATA DETECTION - EDGE CASE TESTS")
    print("=" * 80)
    
    failures = []
    summary = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for test in EDGE_CASES:
            print(f"\n{'='*60}")
            print(f"TEST: {test['name']}")
            print(f"Type: {test['type']}")
            print(f"Potential Issue: {test.get('potential_issue', 'N/A')}")
            print("-" * 60)
            
            # Create project
            if "files" in test:
                project_dir = os.path.join(temp_dir, test["name"].replace(" ", "_"))
                os.makedirs(project_dir, exist_ok=True)
                create_project_files(test["files"], project_dir)
            elif "structure" in test:
                # Complex structure - skip for now
                print("  [SKIPPED] Complex structure test")
                summary["skipped"] += 1
                continue
            else:
                continue
            
            # Run detection
            results, issues = run_detection(project_dir, test["type"], test["expected"])
            
            # Print results
            print("\nResults:")
            for key, data in results.items():
                status_icon = "[PASS]" if data["status"] == "PASS" else "[FAIL]"
                print(f"  {status_icon} {key}: expected={data['expected']}, actual={data['actual']}")
                summary["total"] += 1
                if data["status"] == "PASS":
                    summary["passed"] += 1
                else:
                    summary["failed"] += 1
            
            if issues:
                failures.append({
                    "test": test["name"],
                    "potential_issue": test.get("potential_issue"),
                    "issues": issues
                })
    
    # Summary
    print("\n" + "=" * 80)
    print("EDGE CASE TEST SUMMARY")
    print("=" * 80)
    print(f"Total checks: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Success rate: {summary['passed']/summary['total']*100:.1f}%" if summary['total'] > 0 else "N/A")
    
    if failures:
        print("\n" + "-" * 40)
        print("IDENTIFIED GAPS IN DETECTION LOGIC:")
        print("-" * 40)
        for f in failures:
            print(f"\n{f['test']}:")
            print(f"  Reason: {f['potential_issue']}")
            for issue in f['issues']:
                print(f"    - {issue}")
    
    return failures, summary


if __name__ == "__main__":
    failures, summary = run_edge_case_tests()
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS FOR METADATA LOGIC EXTENSION")
    print("=" * 80)
    
    # Analyze failures and generate recommendations
    recommendations = set()
    
    for f in failures:
        issue = f.get("potential_issue", "")
        if ".ts" in issue or "TypeScript" in f["test"]:
            recommendations.add("1. Add TypeScript source file scanning (.ts, .tsx)")
        if "Remix" in f["test"] or "Gatsby" in f["test"] or "SvelteKit" in f["test"]:
            recommendations.add("2. Add detection for Remix (build/), Gatsby (public/), SvelteKit (.svelte-kit/)")
        if "nested" in issue or "config" in issue.lower():
            recommendations.add("3. Check for config files in subdirectories (configs/, config/)")
        if "Multiple" in f["test"]:
            recommendations.add("4. Support detecting multiple databases")
        if "PM2" in f["test"] or "ecosystem" in issue:
            recommendations.add("5. Parse PM2 ecosystem.config.js for port")
        if "lib/" in str(f["issues"]):
            recommendations.add("6. Add lib/ to source file scan list")
    
    if recommendations:
        print("\nBased on edge case failures, consider these extensions:")
        for r in sorted(recommendations):
            print(f"  {r}")
    else:
        print("No critical extensions needed.")
