#!/usr/bin/env python3
"""NIRVANA organize-corpus — batch-run local subagents over the SDK doc corpus
into training-format JSONL (one entry per doc). All inference on bonsai (local).
Usage: organize-corpus.py [corpus-dir] [out-jsonl] [max-docs]"""
import concurrent.futures, importlib.util, json, os, re, sys

_spec = importlib.util.spec_from_file_location('lsa', '/root/bin/local-subagent.py')
_lsa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lsa)
run = _lsa.run

CORPUS = sys.argv[1] if len(sys.argv) > 1 else '/root/datasets/NPU-STACK/internal/datasets/npu-sdk-docs'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/root/datasets/NPU-STACK/internal/datasets/npu-sdk-docs/training.jsonl'
MAX = int(sys.argv[3]) if len(sys.argv) > 3 else 0

PROMPT = """You are a dataset prep worker. Extract the key technical facts from the document in CONTEXT into STRICT JSON with exactly these keys:
{"source": "the document filename", "topic": "one-line topic", "key_points": ["list of 3-8 concrete technical points"], "apis": ["any API/function/command names mentioned"], "models": ["any model names/formats mentioned"]}
Rules: output ONLY the JSON object, no markdown fences, no commentary. If the doc is empty or unparseable, output {"source": "FILENAME", "topic": "unparseable", "key_points": [], "apis": [], "models": []}"""

def extract_json(text):
    text = text.strip()
    # strip markdown fences if the model added them anyway
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # try to salvage: find balanced braces
        s = text.find('{')
        depth = 0
        for i in range(s, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[s:i + 1])
                    except Exception:
                        return None
    return None

def main():
    files = []
    for root, _, names in os.walk(CORPUS):
        for n in names:
            if n.endswith('.md') and not n.endswith('.jsonl'):
                files.append(os.path.join(root, n))
    files.sort()
    if MAX > 0:
        files = files[:MAX]
    print('corpus: %d docs -> %s' % (len(files), OUT), flush=True)

    entries = []
    def work(path):
        import time
        for attempt in range(3):
            try:
                ctx = open(path, encoding='utf-8', errors='replace').read()[:12000]
                text = run(PROMPT.replace('FILENAME', os.path.basename(path)), ctx)
                data = extract_json(text)
                if data is None:
                    data = {'source': os.path.basename(path), 'topic': 'PARSE-FAIL',
                            'key_points': [], 'apis': [], 'models': [], 'raw': text[:300]}
                return data
            except Exception as e:
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                else:
                    return {'source': os.path.basename(path), 'topic': 'ERROR: %s' % e,
                            'key_points': [], 'apis': [], 'models': []}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for i, data in enumerate(ex.map(work, files), 1):
            entries.append(data)
            print('[%d/%d] %s' % (i, len(files), data.get('source')), flush=True)

    with open(OUT, 'w') as f:
        for e in entries:
            f.write(json.dumps(e) + '\n')
    ok = sum(1 for e in entries if e.get('topic') not in ('PARSE-FAIL',) and not str(e.get('topic', '')).startswith('ERROR'))
    print('done: %d/%d structured cleanly -> %s' % (ok, len(entries), OUT), flush=True)

if __name__ == '__main__':
    main()
