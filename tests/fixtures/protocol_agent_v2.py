"""Independent JSONL v2 transport double; does not generate SQL or call a model."""

import json
import sys

json.loads(sys.stdin.buffer.readline().decode("utf-8"))
with open(sys.argv[1], encoding="utf-8") as stream:
    response = json.load(stream)
sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
