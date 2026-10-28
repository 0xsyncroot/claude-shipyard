#!/usr/bin/env python3
"""Maintainer tool: copy the skills, agents and report rules from a working ~/.claude into this repo.

    python3 tools/export.py [--from ~/.claude]

- skills/feature-wave, skills/acceptance-testing, agents/wave-*.md + test-*.md (wave-qa is retired),
  rules/CLAUDE.md = the claude-shipyard block of ~/.claude/CLAUDE.md (or, before the first install,
  everything from the "## Output mode" heading on).
- Scrubs known private references, then FAILS if any term from ~/.claude/tools/shipyard-denylist.txt
  (one term per line, kept outside the repo on purpose) is still present. Review `git diff` before pushing.
"""
import argparse
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = ('feature-wave', 'acceptance-testing')
AGENT_RE = re.compile(r'^(wave|test)-[a-z-]+\.md$')
BEGIN, END = '<!-- claude-shipyard:rules:begin -->', '<!-- claude-shipyard:rules:end -->'

# Public wording for lines that name private projects.
SCRUB = [
    (re.compile(r'Distilled from real team runs \([^;]*; '), 'Distilled from real team runs (7 projects; '),
]


def rules_from(claude_md):
    s = open(claude_md, encoding='utf-8').read()
    if BEGIN in s and END in s:
        return s[s.index(BEGIN) + len(BEGIN):s.index(END)].strip() + '\n'
    m = re.search(r'^## Output mode', s, re.M)
    if not m:
        sys.exit(f'no "## Output mode" section and no claude-shipyard block in {claude_md}')
    return s[m.start():].strip() + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='src', default=os.path.expanduser('~/.claude'))
    a = ap.parse_args()
    src = os.path.abspath(a.src)

    for sk in SKILLS:
        dst = os.path.join(REPO, 'skills', sk)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(os.path.join(src, 'skills', sk), dst,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.venv', '*.zip', '*.tmp'))
    adir = os.path.join(REPO, 'agents')
    shutil.rmtree(adir, ignore_errors=True)
    os.makedirs(adir)
    for f in sorted(os.listdir(os.path.join(src, 'agents'))):
        if AGENT_RE.match(f) and f != 'wave-qa.md':
            shutil.copy(os.path.join(src, 'agents', f), os.path.join(adir, f))
    os.makedirs(os.path.join(REPO, 'rules'), exist_ok=True)
    with open(os.path.join(REPO, 'rules', 'CLAUDE.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(rules_from(os.path.join(src, 'CLAUDE.md')))

    files = [os.path.join(dp, f) for top in ('skills', 'agents', 'rules')
             for dp, _, fs in os.walk(os.path.join(REPO, top)) for f in fs]
    for p in files:
        s = open(p, encoding='utf-8').read()
        t = s
        for rx, repl in SCRUB:
            t = rx.sub(repl, t)
        if t != s:
            open(p, 'w', encoding='utf-8', newline='\n').write(t)

    deny_path = os.path.join(src, 'tools', 'shipyard-denylist.txt')
    terms = []
    if os.path.exists(deny_path):
        terms = [l.strip().lower() for l in open(deny_path, encoding='utf-8') if l.strip() and not l.startswith('#')]
    else:
        print(f'WARN no denylist at {deny_path} — private-term check skipped', file=sys.stderr)
    scan = files + [os.path.join(REPO, f) for f in ('README.md', 'install.sh') if os.path.exists(os.path.join(REPO, f))]
    hits = [(os.path.relpath(p, REPO), t) for p in scan for t in terms if t in open(p, encoding='utf-8').read().lower()]
    if hits:
        for p, t in hits:
            print(f'PRIVATE TERM {t!r} in {p}', file=sys.stderr)
        sys.exit(1)
    print(f'exported {len(files)} files from {src}; denylist {len(terms)} terms: clean')


if __name__ == '__main__':
    main()
