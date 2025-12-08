"""Quick test for react-job-portal-main project"""
import sys
sys.path.insert(0, '.')
from app.utils.command_extractor import extract_port_from_project, extract_frontend_port, extract_nodejs_commands

backend_path = 'uploads/user_abdulahadabbassi2@gmail.com/extracted/project-69369f75c6b8eec74911b96f/react-job-portal-main/backend'
frontend_path = 'uploads/user_abdulahadabbassi2@gmail.com/extracted/project-69369f75c6b8eec74911b96f/react-job-portal-main/frontend'

print('='*50)
print('BACKEND PORT DETECTION')
print('='*50)
bp = extract_port_from_project(backend_path, 'Express.js', 'JavaScript')
print(f'Port: {bp["port"]}')
print(f'Source: {bp["source"]}')

print()
print('='*50)
print('FRONTEND PORT DETECTION')
print('='*50)
fp = extract_frontend_port(frontend_path)
print(f'Port: {fp["port"]}')
print(f'Source: {fp["source"]}')

print()
print('='*50)
print('BACKEND COMMANDS')
print('='*50)
bc = extract_nodejs_commands(backend_path)
for k, v in bc.items():
    print(f'{k}: {v}')

print()
print('='*50)
print('FRONTEND COMMANDS')
print('='*50)
fc = extract_nodejs_commands(frontend_path)
for k, v in fc.items():
    print(f'{k}: {v}')
