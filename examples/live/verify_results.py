"""Recheck saved live runs without network or model calls.

Run from repository root: python3 -m examples.live.verify_results
"""

import json
from pathlib import Path

from src.tools import ToolSet
from src.tools.local import fingerprint
from src.contracts import validate_finish_arguments
from .verify_semantic_runs import BASE, verify_attempt


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
    selection_path = BASE / 'selection.json'
    selection = json.loads(selection_path.read_text()) if selection_path.exists() else {}
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
        if name in selection:
            recorded_folder = BASE / selection[name]
            for filename in ('input.json', 'output.json', 'trace.jsonl', 'api-audit.json', 'runtime-manifest.json'):
                assert (folder / filename).read_bytes() == (recorded_folder / filename).read_bytes()
            report.update(verify_attempt(recorded_folder))
            report['semantic_review'] = 'actual_live_response_matched_and_offline_replay_passed'
            reports.append(report)
            continue
        validate_finish_arguments(
            {key: output[key] for key in ('status', 'message', 'questions')},
            output['missing_fields'],
        )
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
            assert output['source_ids'] == sorted({claim['source_id'] for scene in script['scenes'] for claim in scene['claims']})
            retrieved = {(m['id'], fact['id']) for row in decisions if row['action'] == 'search_materials' and row['observation']['ok'] for m in row['observation']['result']['matches'] for fact in m['facts']}
            assert all((claim['source_id'], claim['fact_id']) in retrieved for scene in script['scenes'] for claim in scene['claims'])
            report['duration_seconds'] = duration['estimated_total_duration_seconds']
            # Runs recorded after the semantic layer was added must show a live judge pass
            # on the final draft; earlier runs are reported as predating it, never as passed.
            final_rules = latest['check_rules']['observation']['result']
            if 'semantic' in final_rules:
                assert final_rules['semantic']['status'] == 'passed', name
                assert final_rules['semantic']['judge_mode'] == 'live', name
                report['semantic_review'] = 'live_judge_passed'
            else:
                report['semantic_review'] = 'not_recorded_run_predates_semantic_layer'
        if name == 'missing_info':
            assert output['missing_fields'] == ['target_duration_seconds'] and output['questions']
            assert '时长' in output['message'] or any('时长' in question or 'target_duration_seconds' in question for question in output['questions'])
        elif name == 'no_material':
            assert any(row['action'] == 'search_materials' and row['observation']['ok'] and not row['observation']['result']['matches'] for row in decisions)
            assert sum(row['action'] == 'search_materials' for row in decisions) >= 2
        elif name == 'tool_failure':
            assert any(not row['observation']['ok'] and row['observation']['error']['code'] == 'INJECTED_FAILURE' for row in decisions)
            assert output['status'] == 'completed'
            assert any(row['action'] == 'search_materials' and row['observation']['ok'] for row in decisions)
        elif name == 'duration_revision':
            estimates = [row['observation']['result'] for row in decisions if row['action'] == 'estimate_duration' and row['observation']['ok']]
            overlong = [result for result in estimates if result['direction'] == 'too_long']
            assert overlong and estimates[-1]['status'] == 'passed'
            assert estimates[-1]['script_version'] > overlong[-1]['script_version']
            assert request['target_duration_seconds'] == 30
            assert request['style'] == '简洁、实用'
            assert all(row['observation'].get('error', {}).get('code') != 'GUARD_REJECTED' for row in decisions)
            report['all_estimates_seconds'] = [result['estimated_total_duration_seconds'] for result in estimates]
            report['duration_change_seconds'] = [overlong[-1]['estimated_total_duration_seconds'], estimates[-1]['estimated_total_duration_seconds']]
        reports.append(report)
    report = {
        'scope': 'selected_real_runs_not_statistical_reliability',
        'normal_and_duration_share_one_run': not bool(selection),
        'sampling_notes': 'Current normal/duration/tool_failure are independent audited semantic-layer runs; missing_info/no_material retain earlier historical evidence.' if selection else 'Historical runs predate semantic-layer rerun.',
        'cases': reports,
    }
    (root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Verified 5 saved live cases; no network or model calls made.')


if __name__ == '__main__':
    main()
