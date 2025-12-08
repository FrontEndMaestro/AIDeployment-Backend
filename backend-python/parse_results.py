import json

data = json.load(open('llm_test_results.json'))

print("=" * 60)
print("LLM DOCKER GENERATION TEST RESULTS")
print("=" * 60)

total_passed = 0
total_checks = 0

for scenario in data:
    name = scenario['scenario']
    checks = scenario['checks']
    passed = sum(1 for c in checks if c['passed'])
    total = len(checks)
    
    total_passed += passed
    total_checks += total
    
    print(f"\n{name}:")
    print(f"  Passed: {passed}/{total}")
    
    for c in checks:
        status = "PASS" if c['passed'] else "FAIL"
        print(f"    [{status}] {c['description']}")

print("\n" + "=" * 60)
print(f"OVERALL: {total_passed}/{total_checks} ({total_passed/total_checks*100:.0f}%)")
print("=" * 60)

if total_passed / total_checks >= 0.8:
    print("\nVERDICT: LLM prompt is working well for most cases")
else:
    print("\nVERDICT: LLM prompt needs improvement")

# Identify common failures
failures = [c for s in data for c in s['checks'] if not c['passed']]
if failures:
    print("\nFAILURES TO ADDRESS:")
    for f in failures:
        print(f"  - {f['description']}")
