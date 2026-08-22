#!/usr/bin/env python3
"""NIRVANA local-subagent — run a task on the local bonsai server (no cloud credits).
Uses /v1/responses with reasoning effort minimal (fast) unless --full-reason.
Usage: local-subagent.py "prompt" [context-file] [--full-reason] [--model paddle-ocr-vl-1.6-lmk]"""
import json, os, sys, urllib.request

ENDPOINT = 'http://192.168.1.232:443/v1/responses'
KEY = ''
for line in open('/root/.hermes/.env'):
    if line.startswith('AUXILIARY_VISION_API_KEY='):
        KEY = line.split('=', 1)[1].strip()
        break

def run(prompt, context='', model='prism-ml/bonsai-27b', effort=None, tools=None):
    content = prompt
    if context:
        content = prompt + '\n\n=== CONTEXT ===\n' + context
    payload = {
        'model': model,
        'input': content,
        'tool_choice': 'auto' if tools else 'none',
    }
    # bonsai reasoning: on/off or numeric budget. User ticked it OFF in LM Studio,
    # so omit the field entirely (server default applies). Sending 'off' as an
    # effort value gets a 400 from this server version.
    if effort:
        payload['reasoning'] = {'effort': effort}
    if tools:
        payload['tools'] = tools
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + KEY})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    out = []
    for o in d.get('output', []):
        if o.get('type') == 'function_call':
            out.append('FUNC:%s(%s)' % (o.get('name'), o.get('arguments')))
        elif o.get('type') == 'message':
            for c in o.get('content', []):
                if c.get('type') == 'output_text':
                    out.append(c.get('text', ''))
    return '\n'.join(out).strip()

if __name__ == '__main__':
    prompt = sys.argv[1]
    ctx = ''
    model = 'prism-ml/bonsai-27b'
    effort = 'minimal'
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--full-reason':
            effort = 'high'
        elif args[i] == '--model' and i + 1 < len(args):
            model = args[i + 1]
            i += 1
        elif not args[i].startswith('--'):
            ctx = open(args[i], encoding='utf-8', errors='replace').read()
        i += 1
    print(run(prompt, ctx, model, effort))
