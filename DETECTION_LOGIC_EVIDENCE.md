# Detection Logic (Strict Evidence-Based Documentation)

This document describes the current detection logic exactly as implemented in the codebase

Repository root used: `devops-autopilot`

## 1. Entry Points and Call Flow

### 1.1 API/controller entry
- Project analysis starts in `analyze_project_handler()`, which calls `detect_framework(project["extracted_path"], use_ml=use_ml)`.
  - Evidence: `backend-python/app/controllers/analyze_controller.py:9`, `:70-72`.
- After detection, controller runs a second env-variable pass on the original extracted path and overwrites `detection["env_variables"]` if values are found.
  - Evidence: `backend-python/app/controllers/analyze_controller.py:81-84`.

### 1.2 Detector orchestrator entry
- Main orchestration is `detect_framework(project_path, use_ml=True)`.
  - Evidence: `backend-python/app/utils/detector.py:291`.
- It first resolves `actual_path = find_project_root(project_path, max_depth=3)`.
  - Evidence: `backend-python/app/utils/detector.py:298`.

## 2. Project Root Resolution (`find_project_root`)

### 2.1 Search strategy
- `find_project_root()` defines framework/manifest files and excluded directories.
  - Evidence: `backend-python/app/utils/detector.py:175-184`.
- Inner `search_unique()`:
  - Stops when depth exceeds `max_depth`.
  - Returns current path immediately if that path has a manifest.
  - Recursively scans children excluding configured excluded dirs.
  - Returns a child path only when exactly one unique manifest-containing candidate exists; otherwise returns `None`.
  - Evidence: `backend-python/app/utils/detector.py:192-232`.

### 2.2 Post-search guard
- After `final_path = search_unique(extracted_path) or extracted_path`, guard logic checks if `final_path` leaf name is a service-like folder.
  - Evidence: `backend-python/app/utils/detector.py:234-257`.
- It inspects parent directory, computes:
  - `parent_has_dep` from `{package.json, requirements.txt, pyproject.toml, pom.xml, go.mod, manage.py}`.
  - `siblings` as service-named directories in parent (excluding noise dirs).
  - Evidence: `backend-python/app/utils/detector.py:259-270`.
- It promotes to parent if `not parent_has_dep OR len(siblings) >= 2`.
  - Evidence: `backend-python/app/utils/detector.py:271-275`.

### 2.3 Test evidence for root detection
- `TestFindProjectRoot` validates:
  - root manifest case,
  - single nested project,
  - deeper nesting,
  - max-depth behavior,
  - ambiguous siblings stays at root,
  - infra dir ignore.
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:247-290`.
- Additional wrapper case exists in legacy-style tests (`wrapper/actual-project`).
  - Evidence: `backend-python/tests/test_detector.py:346-355`.

## 3. Heuristic Language/Framework + Runtime

### 3.1 Language heuristic
- Scores language from:
  - extension matches (`+0.3`),
  - language config files (`+0.7`),
  - import marker substrings in source (`+0.4`).
  - Evidence: `backend-python/app/utils/detection_language.py:239-275`.
- Chooses highest score, confidence is `min(best_score / 2.0, 1.0)`.
  - Evidence: `backend-python/app/utils/detection_language.py:282-295`.

### 3.2 Framework heuristic
- Builds dependency set from:
  - `requirements.txt`, `package.json`, `composer.json`, `pom.xml`.
  - Evidence: `backend-python/app/utils/detection_language.py:305-348`.
- Adds framework score from dependency hits (`+0.8`), configured marker files (`+0.6`), and source markers (`+0.5`).
  - Evidence: `backend-python/app/utils/detection_language.py:350-378`.
- Applies language-compatibility penalty (`*0.5`) for mismatched framework-language pairs.
  - Evidence: `backend-python/app/utils/detection_language.py:388-397`.

### 3.3 Runtime defaults and framework overrides
- `get_runtime_info()` provides base image, default port, build command, start command by language.
  - Evidence: `backend-python/app/utils/detection_language.py:166-213`.
- Framework-specific overrides apply afterward.
  - Evidence: `backend-python/app/utils/detection_language.py:215-236`.

### 3.4 Orchestrator post-processing
- `detect_framework()` runs heuristics, optional ML supplement when heuristic confidence is low.
  - Evidence: `backend-python/app/utils/detector.py:343-373`.
- It enforces framework-language compatibility correction.
  - Evidence: `backend-python/app/utils/detector.py:375-390`.

## 4. Dependency Parsing

### 4.1 Supported parsers
- `parse_dependencies_file()` has explicit logic for:
  - `requirements.txt`,
  - `package.json`,
  - `pom.xml`,
  - `go.mod`,
  - `pyproject.toml`,
  - `Pipfile`,
  - `poetry.lock`,
  - `composer.json`,
  - `Cargo.toml`.
  - Evidence: `backend-python/app/utils/detection_language.py:25-148`.
- Output is deduplicated, order-preserving, capped at 50.
  - Evidence: `backend-python/app/utils/detection_language.py:152-163`.

### 4.2 Test evidence
- Comprehensive parser tests cover:
  - requirements edge cases, package.json merges/bad JSON, pom.xml, go.mod, cap at 50, unknown file type.
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:104-211`.

## 5. Environment Variable Collection

### 5.1 Key-only env collection
- `detect_env_variables(project_path)` scans only root-level files:
  - `.env`, `.env.example`, `.env.sample`, `.env.local`,
  - collects only keys from `KEY=VALUE` lines.
  - Evidence: `backend-python/app/utils/detector.py:128-147`.

### 5.2 Key-value env collection
- `_read_env_key_values(project_path)` reads root-level and common env variants, stores key-value pairs.
  - Evidence: `backend-python/app/utils/detector.py:150-169`.

### 5.3 Test evidence
- Env key parsing tests exist for key extraction and no-file behavior.
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:214-244`.

## 6. Port Detection Logic

There are two port-detection paths used in the system.

### 6.1 Service-local backend/frontend port extraction (`command_extractor.py`)
- `extract_port_from_project()` priority:
  1. `_parse_env_for_port()` (`PORT=...` from env files),
  2. `_scan_source_for_port()`,
  3. framework/language defaults.
  - Evidence: `backend-python/app/utils/command_extractor.py:664-702`.
- `_parse_env_for_port()` regex allows optional spaces (`PORT = 4000`).
  - Evidence: `backend-python/app/utils/command_extractor.py:533-549`.
- `_scan_source_for_port()` searches specific known source-file paths and regex patterns for JS/TS or Python.
  - Evidence: `backend-python/app/utils/command_extractor.py:560-630`.
- `extract_frontend_port()` checks:
  1. `vite.config.*`,
  2. env `PORT`,
  3. dependency-based defaults (`vite`, `react-scripts`, `next`, `@vue/cli-service`, `@angular/cli`).
  - Evidence: `backend-python/app/utils/command_extractor.py:705-776`.

### 6.2 Project-level backend/frontend/docker ports (`detection_ports.py`)
- `detect_ports_for_project()` computes metadata-level ports and docker port sets.
  - Evidence: `backend-python/app/utils/detection_ports.py:398-706`.
- For JS/TS:
  - Detects fullstack structure via folder names + presence of `package.json`.
  - Applies root and nested env extraction logic with explicit backend/frontend key groups and generic `PORT`.
  - Evidence: `backend-python/app/utils/detection_ports.py:14-49`, `:452-556`.
- For non-JS/TS:
  - uses `_scan_code_for_ports()` then defaults by language; applies explicit backend env override.
  - Evidence: `backend-python/app/utils/detection_ports.py:602-627`.
- Docker:
  - parses docker-compose host/container mappings and Dockerfile `EXPOSE`,
  - classifies service names into backend/frontend/database/other.
  - Evidence: `backend-python/app/utils/detection_ports.py:229-343`, `:345-395`, `:629-706`.

### 6.3 Test evidence
- Command extraction and port extraction are covered extensively in `test_detection_comprehensive.py`.
  - Entry-point tests: `:67-210`.
  - Port tests (env/source/default/frontend): `:263-430`.
  - Mixed realistic backend scenarios: `:488-620`.

## 7. Database Detection Logic

### 7.1 Metadata-level DB inference (`detection_database.py`)
- `detect_databases(project_path, dependencies, env_vars)` scoring sources:
  - dependency pattern matches (`+1.0`),
  - explicit env key matches (`+0.8`),
  - env-key substring heuristics (`+0.4`),
  - compose image hints (`+0.7`).
  - Evidence: `backend-python/app/utils/detection_database.py:167-199`.
- It merges env info from root and (if detected as fullstack) nested backend/frontend folders.
  - Evidence: `backend-python/app/utils/detection_database.py:141-153`.
- Database port inference uses DB-specific env keys first, then compose mapping fallback, then default DB port.
  - Evidence: `backend-python/app/utils/detection_database.py:14-109`.

### 7.2 Service-level container decision (`command_extractor.py`)
- `extract_database_info()`:
  - parses env DB URLs,
  - classifies cloud/local using URL patterns,
  - sets `needs_container`,
  - falls back from detected DB string if env URL absent.
  - Evidence: `backend-python/app/utils/command_extractor.py:825-954`.

### 7.3 Test evidence
- Exhaustive DB tests include nested backend env and cloud Mongo URI handling.
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:540-552`.

## 8. Service Inference Logic (`detection_services.py`)

### 8.1 Stub discovery
- Node stubs:
  - `_find_all_services_by_deps()` walks for `package.json`,
  - classifies via `BACKEND_DEPS`/`FRONTEND_DEPS`,
  - skips `package.json` with no backend/frontend dep match.
  - Evidence: `backend-python/app/utils/detection_services.py:109-151`.
- Python stubs:
  - `_find_python_services()` detects frameworks via `manage.py` or dependency text in requirements/pyproject/Pipfile.
  - If no framework detected, directory is skipped.
  - Evidence: `backend-python/app/utils/detection_services.py:246-310`.

### 8.2 Type inference fallback
- `_infer_service_type()` order:
  1. `package.json` deps -> backend/frontend/monolith,
  2. DB keyword service names -> `other`,
  3. folder-name heuristic by substring match.
  - Evidence: `backend-python/app/utils/detection_services.py:57-106`.

### 8.3 Root suppression helper
- `_suppress_root_if_children_found()` rules:
  - root monolith keeps root + DB children only,
  - root backend keeps all,
  - root frontend/other with >=2 real non-root services drops root.
  - Evidence: `backend-python/app/utils/detection_services.py:154-199`.

### 8.4 Full `infer_services()` flow
- `infer_services()` pipeline:
  1. build Node stubs,
  2. build Python stubs,
  3. merge by path (`Python` preferred if framework is detected),
  4. apply root-suppression helper,
  5. populate service fields (ports, entry points, env files, package manager),
  6. drop empty shells (`no port` and `no entry_point`, except `database`/`other`),
  7. fallback single-service logic if empty,
  8. compose hints,
  9. optional monolith child suppression,
  10. database service append logic,
  11. final phantom-root suppression block.
  - Evidence: `backend-python/app/utils/detection_services.py:410-740`.

### 8.5 Final phantom-root suppression block (current implementation)
- At the end of `infer_services()`, if any subdirectory services exist and root has no dependency file, services are replaced with only `_subdir_services`.
  - Evidence: `backend-python/app/utils/detection_services.py:716-738`.

### 8.6 Test evidence
- Dep-based discovery and skip behavior:
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:1021-1071`.
- Root suppression helper tests:
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:1120-1164`, `:1267-1320`.
- Python stub detection tests:
  - Evidence: `backend-python/tests/test_detector_exhaustive.py:1173-1241`.
- End-to-end service detection in realistic repos:
  - Evidence: `backend-python/tests/test_detection_comprehensive.py:731-909`.

## 9. `detect_framework()` Orchestration Sequence and Metadata

### 9.1 Sequence
- In order, `detect_framework()` performs:
  1. root resolution,
  2. heuristic language/framework detection,
  3. optional ML supplement,
  4. compatibility correction,
  5. runtime defaults,
  6. command extraction overrides,
  7. key file presence flags and static-only detection,
  8. dependency collection (root + nested),
  9. Docker file detection,
  10. env variable key extraction,
  11. DB + port detection,
  12. service inference,
  13. service-port consolidation into top-level metadata,
  14. cloud-db clearing of `database_port`,
  15. deploy-blocked/warning checks for backend env requirements,
  16. dedupe of detected files.
  - Evidence: `backend-python/app/utils/detector.py:298-662`.

### 9.2 Metadata keys explicitly initialized
- Result dict includes:
  - framework/language/runtime,
  - commands and env vars,
  - detection confidence,
  - static-only flags,
  - DB and multi-port fields,
  - docker host/container port fields,
  - Dockerfile expose ports.
  - Evidence: `backend-python/app/utils/detector.py:300-340`.

### 9.3 Export/use evidence
- Controller export handler reads both legacy and extended metadata fields.
  - Evidence: `backend-python/app/controllers/analyze_controller.py:407-446`.

## 10. Deterministic Constraints and Gaps (Code-Observable)

These statements are direct consequences of implementation predicates, not assumptions:

1. Node service discovery ignores `package.json` files with no deps intersecting `BACKEND_DEPS` or `FRONTEND_DEPS`.
   - Evidence: `backend-python/app/utils/detection_services.py:131-141`; dep sets in `backend-python/app/utils/detection_constants.py:183-192`.

2. Python service discovery skips directories unless a known framework signal is found.
   - Evidence: `backend-python/app/utils/detection_services.py:261-310`; framework dep set in `backend-python/app/utils/detection_constants.py:199-201`.

3. Fullstack folder detection in `detection_ports.py` is name-limited to specific labels and requires `package.json` in those child folders.
   - Evidence: `backend-python/app/utils/detection_ports.py:37-46`.

4. `infer_services()` contains a second phantom-root suppression pass after DB append logic.
   - Evidence: `backend-python/app/utils/detection_services.py:688-738`.

5. Controller performs a second env-var extraction on `extracted_path` and may overwrite values set from resolved root path.
   - Evidence: `backend-python/app/controllers/analyze_controller.py:81-84`; detector root/env call points `backend-python/app/utils/detector.py:298`, `:511-513`.

6. `find_project_root()` parent promotion condition uses `not parent_has_dep OR len(siblings) >= 2`.
   - Evidence: `backend-python/app/utils/detector.py:271-275`.

7. `_infer_service_type()` fallback name logic uses substring checks (`k in name_lower`) against configured name sets.
   - Evidence: `backend-python/app/utils/detection_services.py:86-105`.

8. In non-JS path of `detect_ports_for_project()`, generic env `PORT` is only applied when `backend_port is None`; code sets `backend_port` before that check.
   - Evidence: `backend-python/app/utils/detection_ports.py:604-623`.

## 11. Test Coverage Map (Direct Evidence)

### Strongly covered areas
- Dependency parsing logic:
  - `backend-python/tests/test_detector_exhaustive.py:104-211`.
- Root path basics:
  - `backend-python/tests/test_detector_exhaustive.py:247-290`,
  - `backend-python/tests/test_detector.py:346-355`.
- Command extraction + port extraction realism:
  - `backend-python/tests/test_detection_comprehensive.py:67-430`, `:488-620`.
- Fullstack structure canonical names:
  - `backend-python/tests/test_detector_exhaustive.py:560-594`.
- Service discovery/suppression helper behavior:
  - `backend-python/tests/test_detector_exhaustive.py:1021-1164`, `:1267-1320`.
- Python service detection:
  - `backend-python/tests/test_detector_exhaustive.py:1173-1241`.
- End-to-end detect framework scenarios:
  - `backend-python/tests/test_detection_comprehensive.py:731-909`.

### Areas where tests do not directly target specific implementation points
- No direct tests were located for `analyze_project_handler` env overwrite path.
  - Evidence basis: no test references found for that controller function in `backend-python/tests`.
- Root DB-preservation behavior for the final `infer_services()` phantom-root block is not directly covered by a dedicated test.
  - Evidence: helper suppression is tested (`test_detector_exhaustive.py:1120+`), final block is separate logic at `detection_services.py:716+`.

## 12. Verification Context

- Test execution in this environment is currently blocked by filesystem permission errors during `pytest` temp-dir setup/cleanup (e.g., access denied under `C:\\Users\\abdul\\AppData\\Local\\Temp\\pytest-of-abdul` and custom basetemp cleanup).
- This document therefore relies on static code inspection and test-source inspection evidence.

