"""Validate a JSON fact or replay the language-neutral conformance suite."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

import rfc8785

from .contract import FactValidationError, content_hash, fact_identity, identity_fields, validate_fact


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field.')
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)


def fact_path(value):
    """Resolve --fact (symlinks and ..) and confine it to a JSON file under the working directory."""
    base = os.path.realpath(os.getcwd())
    path = os.path.realpath(value)
    if not path.startswith(base + os.sep) or not path.endswith('.json'):
        raise ValueError('The fact must be a .json file inside the working directory.')
    return path


def _identity_conformance(root, failures):
    vectors = read_json(root / 'identity' / 'identity-vectors-v1.json')
    for case in vectors['cases']:
        try:
            passed = (identity_fields(case['input']) == case['canonical_identity']
                      and rfc8785.dumps(identity_fields(case['input'])).decode('utf-8') == case['canonical_json']
                      and fact_identity(case['input']) == case['expected'])
        except FactValidationError:
            passed = False
        if not passed:
            failures.append('identity:' + case['name'])
    for case in vectors['negative']:
        try:
            validate_fact(case['input'], submission=False)
            passed = False
        except FactValidationError as error:
            passed = any(issue.code == case['expected_error']['code']
                         and issue.path == case['expected_error']['path'] for issue in error.issues)
        if not passed:
            failures.append('identity-negative:' + case['name'])
    return len(vectors['cases']), len(vectors['negative'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fact', type=Path)
    source.add_argument('--conformance', action='store_true')
    parser.add_argument('--stored', action='store_true', help='Validate memory-owned validity states.')
    args = parser.parse_args(argv)
    if args.conformance:
        root = Path(__file__).parent / 'conformance' / 'v1'
        manifest = read_json(root / 'manifest.json')
        cases = manifest['cases']
        failures = []
        for case in cases:
            try:
                validate_fact(read_json(root / case['file']), submission=case['submission'])
                passed = case['accepted']
            except FactValidationError as error:
                passed = not case['accepted'] and any(
                    issue.code == case['expected_error']['code'] and issue.path == case['expected_error']['path']
                    for issue in error.issues
                )
            if not passed:
                failures.append(case['file'])
        hash_cases = read_json(root / manifest['hash_vectors'])
        for case in hash_cases:
            actual = content_hash(case['source_utf8'].encode('utf-8'), case.get('line_start'), case.get('line_end'))
            if actual != case['expected']:
                failures.append('hash:' + case['name'])
        positive, negative = _identity_conformance(root.parent, failures)
        print(json.dumps({'total': len(cases), 'hash_vectors': len(hash_cases),
                          'identity_vectors': positive, 'identity_negative_vectors': negative, 'failed': failures}))
        return 1 if failures else 0
    try:
        validate_fact(read_json(fact_path(args.fact)), submission=not args.stored)
    except FactValidationError as error:
        print(json.dumps({'valid': False, 'errors': [asdict(i) for i in error.issues]}))
        return 1
    except (OSError, ValueError):
        print(json.dumps({'valid': False, 'errors': [{'code': 'JSON_INPUT', 'path': '/', 'message': 'Cannot read an unambiguous UTF-8 JSON document inside the working directory.'}]}))
        return 1
    print(json.dumps({'valid': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
