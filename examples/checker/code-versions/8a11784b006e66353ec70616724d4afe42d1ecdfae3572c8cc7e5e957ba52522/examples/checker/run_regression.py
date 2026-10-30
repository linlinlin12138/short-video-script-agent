"""Actual offline adversarial checks. Run: python3 -m examples.checker.run_regression."""

import json
from pathlib import Path

from src.tools import ToolSet
from src.tools.local import ROOT


def script_with_claim(text):
    return {
        "version": 1, "title": "字幕功能介绍",
        "scenes": [{
            "id": "S01", "visual": "创作者举起纸卡。", "voiceover": text,
            "subtitle": "支持字幕",
            "claims": [{"text": "支持字幕", "source_id": "P01", "fact_id": "P01-F1"}],
        }],
    }


def main():
    cases = json.loads((ROOT / 'data/evaluation_claims.json').read_text())
    rules = json.loads((ROOT / 'data/brand_rules.json').read_text())
    tools = ToolSet()
    records = []
    for category, texts in cases.items():
        expected = 'failed' if category == 'unsupported_claims' else 'passed'
        for text in texts:
            script = script_with_claim(text)
            output = tools.execute('check_rules', {'script': script})
            passed = output['ok'] and output['result']['facts'] == expected
            records.append({
                'category': category, 'text': text, 'expected_facts': expected,
                'input': script, 'output': output, 'expectation_met': passed,
            })
    report = {
        'scope': 'fixed_adversarial_regression_not_general_semantic_accuracy',
        'rules_version': rules['rules_version'], 'records': records,
        'all_expectations_met': all(row['expectation_met'] for row in records),
    }
    target = Path(__file__).with_name('current-results.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"Recorded {len(records)} actual local checks; all expectations met: {report['all_expectations_met']}")
    if not report['all_expectations_met']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
