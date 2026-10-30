"""Offline audit of newly recorded real runs; never calls a model.

Replays saved, real judge verdicts through the program's checks. A replay is
reported as replay, never represented as a new live semantic judgment.
"""

import copy
import hashlib
import json
from pathlib import Path

from src.tools import ToolSet
from src.tools.local import ROOT, fingerprint
from src.verifier import JUDGE_INSTRUCTIONS, split_segments

BASE = ROOT / 'examples/live/semantic-rerun'


def read(path):
    return json.loads(path.read_text())


class RecordedJudge:
    mode = 'replay'

    def __init__(self, record):
        self.record = record
        self.name = record['requested_model']

    def judge(self, payload):
        assert payload == self.record['judge_input'], 'Saved verdict belongs to different text/facts'
        return copy.deepcopy(self.record['verdict'])


def verify_attempt(folder):
    output = read(folder / 'output.json')
    request = read(folder / 'input.json')
    trace = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
    audit = read(folder / 'api-audit.json')
    for name, digest in read(folder / 'runtime-manifest.json').items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert trace[0]['mode'] == 'live'
    decisions = [row for row in trace if row.get('event') == 'decision']
    assert output['tool_calls_used'] <= trace[0]['max_tools']
    assert len(decisions) <= trace[0]['max_rounds']
    estimates = [row['observation']['result'] for row in decisions
                 if row['action'] == 'estimate_duration' and row['observation']['ok']]
    judge_calls = [row for row in audit['calls'] if row['kind'] == 'semantic_judge']
    report = {
        'directory': str(folder.relative_to(BASE)), 'status': output['status'],
        'output_semantic': output['checks']['semantic'],
        'tool_calls_used': output['tool_calls_used'], 'api_calls': len(audit['calls']),
        'judge_api_calls': len(judge_calls),
        'estimated_seconds': [item['estimated_total_duration_seconds'] for item in estimates],
        'guard_rejections': sum(row['observation'].get('error', {}).get('code') == 'GUARD_REJECTED'
                                for row in decisions),
        'tool_failure_seen': any(row['observation'].get('error', {}).get('code') == 'INJECTED_FAILURE'
                                 for row in decisions),
        'natural_overlong_correction': any(
            first['direction'] == 'too_long' and later['status'] == 'passed'
            and later['script_version'] > first['script_version']
            for index, first in enumerate(estimates) for later in estimates[index + 1:]),
    }
    if output['status'] != 'completed':
        report['final_semantic_audit'] = 'not_completed_no_pass_claimed'
        return report
    assert output['checks']['semantic'] == 'passed'
    latest = {
        row['action']: row for row in decisions
        if row['action'] in ('estimate_duration', 'check_rules') and row['observation']['ok']
    }
    assert set(latest) == {'estimate_duration', 'check_rules'}
    script = latest['check_rules']['arguments']['script']
    rules = latest['check_rules']['observation']['result']
    semantic = rules['semantic']
    assert semantic['status'] == 'passed' and semantic['judge_mode'] == 'live'
    assert rules['script_hash'] == fingerprint(script)
    assert latest['estimate_duration']['observation']['result']['script_hash'] == fingerprint(script)
    assert output['checks']['script_version'] == script['version']
    materials = read(ROOT / 'data/materials.json')['materials']
    facts = sorted((m['id'], f['id'], f['text']) for m in materials for f in m['facts'])
    expected_payload = {
        'facts': [{'source_id': source, 'fact_id': fid, 'text': text} for source, fid, text in facts],
        'segments': [{key: segment[key] for key in ('id', 'location', 'text')}
                     for segment in split_segments(script)],
    }
    matching = [record for record in judge_calls
                if record.get('transport_status') == 'success'
                and record.get('judge_input') == expected_payload and 'verdict' in record]
    assert matching, 'No actual successful judge response for final script'
    final_call = matching[-1]
    expected_instructions_hash = hashlib.sha256(json.dumps(
        JUDGE_INSTRUCTIONS, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert final_call['instructions_hash'] == expected_instructions_hash
    assert final_call['requested_model'] == semantic['judge'] == trace[0]['judge']
    ids = [item['id'] for item in final_call['verdict']['segments']]
    assert len(ids) == len(set(ids)) == len(expected_payload['segments'])
    assert set(ids) == {item['id'] for item in expected_payload['segments']}
    assert semantic['segments_reviewed'] == len(ids)
    assert semantic['claims'] and all(claim['verdict'] == 'supported' for claim in semantic['claims'])
    replay = ToolSet(judge=RecordedJudge(final_call)).check_rules(script)
    assert replay['facts'] == replay['brand'] == replay['semantic']['status'] == 'passed'
    assert replay['semantic']['claims'] == semantic['claims']
    timing = ToolSet().estimate_duration(script, request['target_duration_seconds'])
    assert timing['status'] == 'passed'
    rendered = copy.deepcopy(script)
    for scene, estimate in zip(rendered['scenes'], timing['scenes']):
        scene['estimated_duration_seconds'] = estimate['estimated_duration_seconds']
    rendered['estimated_total_duration_seconds'] = timing['estimated_total_duration_seconds']
    assert rendered == output['script']
    assert output['source_ids'] == sorted({c['source_id'] for s in script['scenes'] for c in s['claims']})
    report.update(
        final_semantic_audit='actual_live_response_matched_and_offline_replay_passed',
        judge=semantic['judge'], returned_judge_model=final_call.get('returned_model'),
        segments_reviewed=len(ids), supported_claims=len(semantic['claims']),
        final_version=script['version'], final_seconds=timing['estimated_total_duration_seconds'],
        final_judge_response_id=final_call.get('response_id'),
    )
    return report


def main():
    reports = [verify_attempt(path.parent) for path in sorted(BASE.glob('*/*/output.json'))]
    selection = read(BASE / 'selection.json')
    by_directory = {report['directory']: report for report in reports}
    selected = {name: by_directory[directory] for name, directory in selection.items()}
    for report in selected.values():
        assert report['status'] == 'completed'
        assert report['final_semantic_audit'] == 'actual_live_response_matched_and_offline_replay_passed'
    assert selected['duration_revision']['natural_overlong_correction']
    assert selected['tool_failure']['tool_failure_seen']
    response_ids = [report['final_judge_response_id'] for report in selected.values()]
    assert all(response_ids) and len(response_ids) == len(set(response_ids)), 'Selected runs must be independent'
    target = BASE / 'verification.json'
    target.write_text(json.dumps({
        'scope': 'saved_real_HTTP_responses_audited_without_new_model_calls',
        'selected': selected, 'all_attempts': reports,
    }, ensure_ascii=False, indent=2) + '\n')
    print('Three independent real runs verified; final semantic judgments match actual API responses.')


if __name__ == '__main__':
    main()
