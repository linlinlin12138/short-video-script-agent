"""Recheck saved live runs without network or model calls.

Run from repository root: python3 -m examples.live.verify_results
"""

import json
from pathlib import Path

from src.tools import ToolSet
from src.tools.local import fingerprint


def main():
    root = Path(__file__).parent
    tools = ToolSet()
    expected = {
        'normal': {'completed'}, 'missing_info': {'needs_input'},
        'no_material': {'needs_input', 'insufficient_material'},
        'tool_failure': {'tool_error', 'completed'},
        'duration_revision': {'completed'},
    }
    reports = []
    for name, statuses in expected.items():
        folder = root / name
        request = json.loads((folder / 'input.json').read_text())
        output = json.loads((folder / 'output.json').read_text())
        trace = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
        decisions = [row for row in trace if row.get('event') == 'decision']
        assert trace[0]['mode'] == 'live'
        assert output['status'] in statuses, name
        assert output['tool_calls_used'] <= trace[0]['max_tools'] <= 10
        assert len(decisions) <= trace[0]['max_rounds'] <= 12
        report = {'case': name, 'status': output['status'], 'tool_calls_used': output['tool_calls_used'],
                  'actions': [row['action'] for row in decisions], 'verified': True}
        if output['status'] == 'completed':
            script = output['script']
            duration = tools.estimate_duration(script, request['target_duration_seconds'])
            rules = tools.check_rules(script)
            assert duration['status'] == rules['facts'] == rules['brand'] == 'passed'
            assert script['estimated_total_duration_seconds'] == duration['estimated_total_duration_seconds']
            assert [s['estimated_duration_seconds'] for s in script['scenes']] == [s['estimated_duration_seconds'] for s in duration['scenes']]
            checks = [row for row in decisions if row['action'] in ('estimate_duration', 'check_rules') and row['observation']['ok']]
            latest = {row['action']: row for row in checks}
            assert set(latest) == {'estimate_duration', 'check_rules'}
            assert latest['estimate_duration']['observation']['result']['script_hash'] == latest['check_rules']['observation']['result']['script_hash']
            checked_script = latest['check_rules']['arguments']['script']
            rendered = json.loads(json.dumps(checked_script))
            for scene, timing in zip(rendered['scenes'], duration['scenes']):
                scene['estimated_duration_seconds'] = timing['estimated_duration_seconds']
            rendered['estimated_total_duration_seconds'] = duration['estimated_total_duration_seconds']
            assert fingerprint(rendered) == fingerprint(script)
            assert output['checks']['script_version'] == script['version']
            retrieved = {(m['id'], fact['id']) for row in decisions if row['action'] == 'search_materials' and row['observation']['ok'] for m in row['observation']['result']['matches'] for fact in m['facts']}
            assert all((claim['source_id'], claim['fact_id']) in retrieved for scene in script['scenes'] for claim in scene['claims'])
            report['duration_seconds'] = duration['estimated_total_duration_seconds']
        if name == 'missing_info':
            assert output['missing_fields'] == ['target_duration_seconds'] and output['questions']
            assert '时长' in output['message'] or any('时长' in question or 'target_duration_seconds' in question for question in output['questions'])
        elif name == 'no_material':
            assert any(row['action'] == 'search_materials' and row['observation']['ok'] and not row['observation']['result']['matches'] for row in decisions)
        elif name == 'tool_failure':
            assert any(not row['observation']['ok'] and row['observation']['error']['code'] == 'INJECTED_FAILURE' for row in decisions)
        elif name == 'duration_revision':
            estimates = [row['observation']['result'] for row in decisions if row['action'] == 'estimate_duration' and row['observation']['ok']]
            assert estimates[0]['status'] == 'failed' and estimates[-1]['status'] == 'passed'
            assert estimates[-1]['script_version'] > estimates[0]['script_version']
            report['duration_change_seconds'] = [estimates[0]['estimated_total_duration_seconds'], estimates[-1]['estimated_total_duration_seconds']]
        reports.append(report)
    report = {'scope': 'single_live_run_per_final_case_not_statistical_reliability', 'cases': reports}
    (root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Verified 5 saved live cases; no network or model calls made.')


if __name__ == '__main__':
    main()
