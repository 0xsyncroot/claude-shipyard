#!/usr/bin/env python3
"""Token cost of a feature-wave by role, from Claude Code transcripts.

Usage: wave-cost.py <session-id | transcript.jsonl> [...]
Reads ~/.claude/projects/*/<session-id>.jsonl (lead) and its subagents/*.jsonl + *.meta.json.
Prints, per role: agents, median/p90 turns, median/max peak context, cache-read, cache-write, output.
Cost grows with context x turns; compare waves on cache-read and on the top agents.
"""
import glob
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):  # Windows console = cp1252: Vietnamese / '·' → UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROLES = ('wave-researcher', 'wave-critic', 'wave-auditor', 'wave-builder',
         'test-designer', 'test-reviewer', 'test-executor', 'wave-qa')


def resolve(arg):
    if arg.endswith('.jsonl') and os.path.isfile(arg):
        return [arg]
    return glob.glob(os.path.expanduser(f'~/.claude/projects/*/{arg}.jsonl'))


def usage(path):
    """Per assistant message id keep the largest usage seen (streamed lines repeat the id)."""
    best = {}
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if '"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get('type') != 'assistant':
                continue
            m = d.get('message') or {}
            mid, u = m.get('id'), m.get('usage') or {}
            if not mid:
                continue
            row = (u.get('input_tokens') or 0, u.get('cache_creation_input_tokens') or 0,
                   u.get('cache_read_input_tokens') or 0, u.get('output_tokens') or 0)
            if mid not in best or row[3] > best[mid][3]:
                best[mid] = row
    rows = list(best.values())
    return {
        'turns': len(rows),
        'write': sum(r[1] for r in rows),
        'read': sum(r[2] for r in rows),
        'out': sum(r[3] for r in rows),
        'peak': max((r[0] + r[1] + r[2] for r in rows), default=0),
    }


def role_of(meta):
    role = meta.get('agentType') or '?'
    if role.startswith(('wave-', 'test-')) or role in ('general-purpose', 'fork', 'Explore', 'Plan'):
        return role
    name = (meta.get('name') or role).lower()  # older transcripts stored the name as agentType
    for key, r in (('critic', 'wave-critic'), ('audit', 'wave-auditor'), ('qa', 'wave-qa')):
        if key in name:
            return r
    return 'wave-researcher' if re.match(r'r-|res', name) else 'wave-builder'


def fmt(n):
    return f'{n / 1e9:.2f}B' if n >= 1e9 else f'{n / 1e6:.1f}M' if n >= 1e6 else f'{n / 1e3:.0f}k'


def main(args):
    paths = [p for a in args for p in resolve(a)]
    if not paths:
        sys.exit('no transcript found; pass a session id or a .jsonl path')
    lead = {'turns': 0, 'write': 0, 'read': 0, 'out': 0, 'peak': 0}
    agents = defaultdict(list)
    for p in paths:
        u = usage(p)
        for k in ('turns', 'write', 'read', 'out'):
            lead[k] += u[k]
        lead['peak'] = max(lead['peak'], u['peak'])
        for meta_path in glob.glob(p[:-len('.jsonl')] + '/subagents/*.meta.json'):
            try:
                meta = json.load(open(meta_path, encoding='utf-8'))
            except ValueError:
                continue
            jl = meta_path[:-len('.meta.json')] + '.jsonl'
            if os.path.isfile(jl):
                a = usage(jl)
                a['name'] = meta.get('name') or meta.get('description', '')[:24]
                agents[role_of(meta)].append(a)

    print(f'transcripts: {len(paths)}')
    print(f"{'role':16}{'agents':>7}{'turns med/p90':>15}{'peak med/max':>15}{'cache-read':>12}{'cache-write':>12}{'output':>9}")
    print(f"{'lead':16}{1:>7}{lead['turns']:>15}{fmt(lead['peak']):>15}{fmt(lead['read']):>12}{fmt(lead['write']):>12}{fmt(lead['out']):>9}")
    total_read = 0
    order = [r for r in ROLES if r in agents] + sorted(r for r in agents if r not in ROLES)
    for role in order:
        L = agents[role]
        turns = sorted(a['turns'] for a in L)
        peaks = [a['peak'] for a in L]
        read = sum(a['read'] for a in L)
        total_read += read
        p90 = turns[max(0, math.ceil(len(turns) * 0.9) - 1)]  # nearest-rank
        print(f"{role:16}{len(L):>7}{f'{statistics.median(turns):.0f}/{p90}':>15}"
              f"{f'{fmt(statistics.median(peaks))}/{fmt(max(peaks))}':>15}{fmt(read):>12}"
              f"{fmt(sum(a['write'] for a in L)):>12}{fmt(sum(a['out'] for a in L)):>9}")
    print(f'subagent cache-read total: {fmt(total_read)} (lead {fmt(lead["read"])})')
    top = sorted(((a['read'], role, a) for role, L in agents.items() for a in L), key=lambda x: -x[0])[:5]
    if top:
        print('top agents by cache-read (name · role · turns · peak):')
        for read, role, a in top:
            print(f"  {fmt(read):>8}  {a['name']} · {role} · {a['turns']} · {fmt(a['peak'])}")
    over = sum(1 for L in agents.values() for a in L if a['peak'] > 250_000)
    print(f'agents with peak context > 250k: {over}')


if __name__ == '__main__':
    main(sys.argv[1:] or sys.exit(__doc__))
