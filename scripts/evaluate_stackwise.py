"""Small, labeled static/retrieval fixture evaluation; no cloud model or client code execution."""
import json
from pathlib import Path
import time
from datetime import datetime, timezone
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.stackwise.analysis import review_pull, retrieve
from src.stackwise.demo import FILES, SHA


def evaluate():
    fixtures = [
        ('tls-off', 'import requests\nrequests.get(url, verify=False)\n', True),
        ('sql-interpolation', 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n', True),
        ('shell-call', 'subprocess.run(command, shell=True)\n', True),
        ('dynamic-eval', 'eval(request_value)\n', True),
        ('tls-on', 'requests.get(url, verify=True)\n', False),
        ('bound-sql', 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))\n', False),
        ('shell-off', 'subprocess.run(["echo", value], shell=False)\n', False),
        ('literal-example', 'example = "Never use eval(request_value) or verify=False"\n', False),
        ('comment-example', '# requests.get(url, verify=False)\nprint("safe")\n', False),
    ]
    rows = []
    for name, source, expected in fixtures:
        started = time.perf_counter()
        pull = {'sha': SHA, 'title': name, 'snapshot': {'sha': SHA, 'files': {'example.py': source}},
                'files': [{'path': 'example.py', 'patch': '@@ -0,0 +1,20 @@\n' + ''.join('+' + line + '\n' for line in source.splitlines())}]}
        result = review_pull(pull, use_ai=False)
        rows.append({'case': name, 'expected_pattern_risk': expected, 'finding_count': len(result['findings']),
                     'matched_label': bool(result['findings']) == expected,
                     'elapsed_ms': round((time.perf_counter() - started) * 1000, 3)})
    questions = [('get_account user_id', 'auth/routes.py'), ('fetch_account balance', 'services/accounts.py'), ('test_account_shape', 'tests/test_accounts.py')]
    retrieval = []
    for question, target in questions:
        started = time.perf_counter(); refs = retrieve({'sha': SHA, 'files': FILES}, question, 3)
        retrieval.append({'question': question, 'expected_file': target, 'top_3_files': [r['path'] for r in refs],
                          'hit_at_3': target in [r['path'] for r in refs], 'elapsed_ms': round((time.perf_counter() - started) * 1000, 3)})
    tp = sum(r['expected_pattern_risk'] and r['finding_count'] > 0 for r in rows)
    fp = sum(not r['expected_pattern_risk'] and r['finding_count'] > 0 for r in rows)
    fn = sum(r['expected_pattern_risk'] and not r['finding_count'] for r in rows)
    return {'generated_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'Nine authored Python static-pattern fixtures and three sample-repository retrieval questions. No live model quality benchmark or proof of production accuracy.',
            'static': {'true_positive_cases': tp, 'false_positive_cases': fp, 'false_negative_cases': fn, 'cases': rows},
            'retrieval': {'hits_at_3': sum(r['hit_at_3'] for r in retrieval), 'questions': retrieval},
            'limitations': ['Labels describe expected pattern warnings, not proven exploitable bugs.', 'Latency is local fixture analysis only; excludes GitHub downloads, queue wait and Groq.', 'Useful/false-positive feedback from real reviewers must be measured after deployment.']}


if __name__ == '__main__':
    report = evaluate()
    output = Path(__file__).resolve().parents[1] / 'data/evaluation/stackwise_fixture_report.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Static fixture labels matched:', sum(r['matched_label'] for r in report['static']['cases']), '/ 9')
    print('Static false-positive cases:', report['static']['false_positive_cases'])
    print('Retrieval hits at 3:', report['retrieval']['hits_at_3'], '/ 3')
    print('Saved:', output)
