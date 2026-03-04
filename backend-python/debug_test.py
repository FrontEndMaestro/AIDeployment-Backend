import json, tempfile, os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock

d = tempfile.mkdtemp()
p = Path(d)

(p / 'package.json').write_text(json.dumps({
    'name': 'fullstack-app',
    'scripts': {'start': 'concurrently'},
}))

backend = p / 'backend'
backend.mkdir()
(backend / 'package.json').write_text(json.dumps({
    'name': 'backend',
    'dependencies': {'express': '4.18', 'mongoose': '7.0'},
}))
(backend / 'server.js').write_text('app.listen(5000)')
(backend / '.env').write_text('MONGO_URI=mongodb://localhost/test\nPORT=5000\n')

frontend = p / 'frontend'
frontend.mkdir()
(frontend / 'package.json').write_text(json.dumps({
    'name': 'frontend',
    'dependencies': {'react': '18.0', 'react-dom': '18.0'},
    'devDependencies': {'vite': '5.0'},
}))
(p / 'frontend' / 'src').mkdir()
(p / 'frontend' / 'src' / 'App.jsx').write_text('import React')

from app.utils.detector import _find_all_services_by_deps, _find_python_services, _suppress_root_if_children_found, infer_services

stubs = _find_all_services_by_deps(d)
print('NODE STUBS:', [(s['name'], s['type']) for s in stubs])

py_stubs = _find_python_services(d)
print('PY STUBS:', [(s['name'], s['type']) for s in py_stubs])

with patch('app.utils.detector.extract_port_from_project', return_value={'port': 5000, 'source': 'env'}), \
     patch('app.utils.detector.extract_nodejs_commands', return_value={'start_command': 'node server.js', 'entry_point': 'server.js'}), \
     patch('app.utils.detector.extract_frontend_port', return_value={'port': 3000, 'source': 'default'}), \
     patch('app.utils.detector.extract_database_info', return_value={'db_type': 'mongodb', 'is_cloud': False, 'database_env_var': 'MONGO_URI'}), \
     patch('app.utils.detector.extract_python_commands', return_value={}):
    meta = {}
    svcs = infer_services(d, 'JavaScript', 'Express.js', meta)
    print("---SERVICES---")
    for s in svcs:
        print(f"SVC: name={s.get('name')} type={s.get('type')} env_file={s.get('env_file')} port={s.get('port')}")
    print('ARCH:', meta.get('architecture'))
