"""Run the unchanged live CLI and record actual transport evidence, without credentials.

All arguments are forwarded to src.cli. API responses are never substituted.
Only the semantic judge's structured verdict is saved; reasoning is not logged.
"""

import hashlib
import json
from pathlib import Path
import sys
import time

from src.cli import main as cli_main
from src.models import HTTPModel


ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if '--model' not in args or args[args.index('--model') + 1] != 'live':
        raise SystemExit('This recorder requires --model live.')
    folder = Path(args[args.index('--output-dir') + 1])
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'api-audit.json').exists():
        raise SystemExit('Choose a new output directory; previous evidence is never overwritten.')
    manifest = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for group in ('src', 'data', 'schemas')
        for path in sorted((ROOT / group).rglob('*'))
        if path.is_file() and path.suffix in ('.py', '.json')
    }
    (folder / 'runtime-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    records = []
    original_post = HTTPModel._post

    def save():
        (folder / 'api-audit.json').write_text(json.dumps({
            'scope': 'actual_HTTPModel_post_calls_no_response_substitution',
            'command_arguments': args, 'calls': records,
        }, ensure_ascii=False, indent=2) + '\n')

    def audited_post(client, endpoint, body):
        judge = body.get('text', {}).get('format', {}).get('name') == 'claim_verdicts'
        record = {
            'index': len(records) + 1, 'kind': 'semantic_judge' if judge else 'agent',
            'endpoint': endpoint, 'requested_model': body.get('model'),
            'request_hash': digest(body),
        }
        if judge:
            record['judge_input'] = json.loads(body['input'][0]['content'])
            record['instructions_hash'] = digest(body.get('instructions'))
        records.append(record)
        started = time.monotonic()
        try:
            # Real transport and its real response; do not modify either.
            response = original_post(client, endpoint, body)
            record.update(
                transport_status='success', returned_model=response.get('model'),
                response_id=response.get('id'), response_hash=digest(response),
            )
            if judge:
                text = ''.join(
                    part.get('text', '')
                    for item in response.get('output', []) if item.get('type') == 'message'
                    for part in item.get('content', []) if part.get('type') == 'output_text'
                )
                try:
                    record['verdict'] = json.loads(text)
                except ValueError:
                    record['verdict_parse_error'] = True
            return response
        except Exception as exc:
            record.update(transport_status='error', error_type=type(exc).__name__)
            raise
        finally:
            record['elapsed_seconds'] = round(time.monotonic() - started, 3)
            save()

    HTTPModel._post = audited_post
    try:
        code = cli_main(args)
        return code
    finally:
        HTTPModel._post = original_post
        save()


if __name__ == '__main__':
    raise SystemExit(main())
