"""Strict L3 input boundary: no directory traversal or private metadata loading."""
import json
from pathlib import Path

FIELDS = {'log_id', 'timestamp', 'agent_id', 'team', 'request', 'sql',
          'answer_text', 'definition_note', 'reported_values', 'referenced_concepts'}


def load_public(path):
    path = Path(path)
    if path.name != 'logs.jsonl':
        raise ValueError('Only logs.jsonl is a public input')
    result, seen = [], set()
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != FIELDS:
                raise ValueError('Invalid public fields')
            for key in FIELDS - {'reported_values', 'referenced_concepts'}:
                if not isinstance(row[key], str):
                    raise ValueError('Expected text field')
            values = row['reported_values']
            if not isinstance(values, list) or len(values) != 1:
                raise ValueError('Expected one Scenario A value')
            value = values[0]
            if (not isinstance(value, dict) or set(value) != {'concept_id', 'value', 'period'}
                    or value['concept_id'] != 'large_orders'
                    or type(value['value']) is not int or value['value'] < 0
                    or not isinstance(value['period'], str)
                    or row['referenced_concepts'] != ['large_orders']):
                raise ValueError('Invalid reported values')
            if not row['log_id'] or row['log_id'] in seen:
                raise ValueError('Duplicate or empty log_id')
            seen.add(row['log_id'])
            result.append(row)
    return result
