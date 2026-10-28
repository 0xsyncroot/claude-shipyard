#!/usr/bin/env python3
"""Test-run CLI for the acceptance-testing skill. Works on <repo>/.qa/<slug>/.

  qa.py init    <slug> [--wave SLUG] [--base REV]    create .qa/<slug>/ (+ .qa/profile.yml, config, lib once per repo)
  qa.py lint    <slug> [--spec PATH] [--impl] [--ready]  validate testcases.yml + coverage gate (exit 1 on errors)
  qa.py select  <slug> [--since REV] [--bug BUG-n] [--stage Sn]  TCs to re-run (confirmation + regression) + --grep
  qa.py collect <slug> --run RUN-ID                  pw.json (+ manual.yml) -> runs/<id>/results.json
  qa.py status  <slug>                               cases, latest results, open defects
  qa.py report  <slug> [--plan] [--embed] [--out F]  self-contained HTML test completion report

Options common to all: --root <repo root> (default: git toplevel, else cwd).
Requires PyYAML (python3 -c "import yaml").
"""
import argparse
import base64
import datetime as dt
import fnmatch
import html
import json
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):  # Windows console = cp1252: Vietnamese / '·' → UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import yaml
except ImportError:  # pragma: no cover
    # install.sh (claude-shipyard) puts PyYAML in <skill>/.venv: Homebrew Python refuses system-wide pip
    # (PEP 668) and `python3 -I` ignores `pip --user`. Re-exec under that venv so every documented
    # `python3 -I …/qa.py` command keeps working unchanged.
    _venv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.venv')
    _py = os.path.join(_venv, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(_venv, 'bin', 'python')
    if os.path.exists(_py) and os.path.realpath(sys.prefix) != os.path.realpath(_venv):
        os.execv(_py, [_py, '-I', os.path.abspath(__file__), *sys.argv[1:]])
    sys.exit('PyYAML missing: run install.sh from claude-shipyard (creates <skill>/.venv), or: pip install pyyaml')

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(SKILL, 'templates')


def _rel(p, start=os.curdir):
    """relpath with '/' — Windows gives backslashes, which break report links and path matching."""
    return os.path.relpath(p, start).replace(os.sep, '/')

KINDS = ('ac', 'ask', 'keep', 'impact', 'rule', 'risk')
KIND_ID = {'ac': r'AC-\d+', 'ask': r'A-?\d+', 'keep': r'K-?\d+', 'impact': r'IMP-\d+', 'rule': r'R-\d+', 'risk': r'RISK-\d+'}
TYPES = ('functional', 'business-rule', 'ui', 'negative', 'security', 'data', 'regression', 'a11y', 'compat', 'exploratory')
TECHNIQUES = ('EP', 'BVA', 'decision-table', 'state-transition', 'use-case', 'error-guessing', 'checklist', 'exploratory')
PRIORITIES = ('P0', 'P1', 'P2')
CASE_STATUS = ('draft', 'ready', 'obsolete')
EXPECT_KINDS = ('ui', 'url', 'net', 'db', 'audit', 'console', 'file', 'visual')
BUG_OPEN = ('new', 'open', 'fixed', 'retest', 'reopened')
BUG_STATUS = BUG_OPEN + ('closed', 'deferred', 'rejected')
SEVERITIES = ('S1', 'S2', 'S3', 'S4')
TC_ID = re.compile(r'^TC-[A-Z0-9]+-\d{3}$')
TC_IN_TEXT = re.compile(r'TC-[A-Z0-9]+-\d{3}')
# Vague expected-result words; allowed only when the line also carries a quote or a number.
VAGUE = re.compile(r'\b(đúng|bình thường|ok|works?|correctly|properly|as expected|đầy đủ|hợp lệ|fine)\b', re.I)
MAX_STEPS = 12  # a longer case has more than one objective — split it (test-design.md §6)
ANSI = re.compile(r'\x1b\[[0-9;]*m')


# ---------------------------------------------------------------- helpers

def git(root, *args):
    r = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ''


def repo_root(arg):
    if arg:
        return os.path.abspath(arg)
    return git(os.getcwd(), 'rev-parse', '--show-toplevel') or os.getcwd()


def now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load_yaml(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or default


class Run:
    """Paths of one test run (.qa/<slug>)."""

    def __init__(self, root, slug):
        if not re.match(r'^[a-z0-9][a-z0-9-]{1,48}$', slug):
            sys.exit(f'bad slug "{slug}": use kebab-case, 2-49 chars')
        self.root, self.slug = root, slug
        self.qa = os.path.join(root, '.qa')
        self.dir = os.path.join(self.qa, slug)
        self.cases_path = os.path.join(self.dir, 'testcases.yml')

    def need(self):
        if not os.path.isfile(self.cases_path):
            sys.exit(f'{self.cases_path} missing — run: qa.py init {self.slug}')
        return self

    def doc(self):
        d = load_yaml(self.cases_path, {}) or {}
        d.setdefault('basis', [])
        d.setdefault('cases', [])
        return d

    def profile(self):
        return load_yaml(os.path.join(self.qa, 'profile.yml'), {}) or {}

    def run_ids(self):
        rd = os.path.join(self.dir, 'runs')
        if not os.path.isdir(rd):
            return []
        return sorted(r for r in os.listdir(rd) if os.path.isfile(os.path.join(rd, r, 'results.json')))

    def results(self, run_id):
        with open(os.path.join(self.dir, 'runs', run_id, 'results.json'), encoding='utf-8') as f:
            return json.load(f)

    def bugs(self):
        out = []
        dd = os.path.join(self.dir, 'defects')
        if not os.path.isdir(dd):
            return out
        for name in sorted(os.listdir(dd)):
            if not re.match(r'^BUG-\d+\.md$', name):
                continue
            path = os.path.join(dd, name)
            text = open(path, encoding='utf-8').read()
            m = re.match(r'^---\n(.*?)\n---\n?(.*)$', text, re.S)
            meta = (yaml.safe_load(m.group(1)) if m else {}) or {}
            meta.setdefault('id', name[:-3])
            meta['_body'] = m.group(2) if m else text
            meta['_path'] = _rel(path, self.dir)
            out.append(meta)
        return out


def live_cases(doc):
    return [c for c in doc['cases'] if c.get('status') != 'obsolete']


def effective(run, _doc=None):
    """Latest observed result per TC across runs: {tc: {status, run, rows}}."""
    eff = {}
    for rid in run.run_ids():
        rows = run.results(rid).get('results', [])
        by = {}
        for r in rows:
            by.setdefault(r['tc'], []).append(r)
        for tc, rs in by.items():
            eff[tc] = {'status': combine([r['status'] for r in rs]), 'run': rid, 'rows': rs}
    return eff


def combine(statuses):
    s = set(statuses)
    if 'fail' in s or 'flaky' in s:
        return 'flaky' if 'flaky' in s and 'fail' not in s else 'fail'
    if 'blocked' in s:
        return 'blocked'
    if 'pass' in s:
        return 'pass'
    return 'skipped'


def match_path(pattern, path):
    pattern = pattern.strip()
    if any(ch in pattern for ch in '*?['):
        return fnmatch.fnmatch(path, pattern)
    p = pattern.rstrip('/')
    return path == p or path.startswith(p + '/')


def grep_for(ids):
    if not ids:
        return ''
    # TC ids are [A-Z0-9-] only (TC_ID), so no regex escaping; the lookahead stops @TC-W-001 matching @TC-W-0010.
    return '(' + '|'.join('@' + i for i in sorted(ids)) + ')(?![\\w-])'


# ---------------------------------------------------------------- init

STATUS_TPL = """# Test status: {slug} — test-lead ledger (read first after compaction / new session)
Started: {now} · Mode: {mode} · Wave: {wave} · BASE: {base}
Surfaces: · Roles: · Viewports: · Profile: .qa/profile.yml

## Exit criteria (defaults from the skill; edit only with a reason)
1. Every basis item covered by >=1 ready TC (qa.py lint coverage 100%)
2. 100% of P0 TCs PASS in the latest run of the final build; >=95% of P1 PASS
3. 0 open S1/S2 defects; S3/S4 open only as deferred with the user's verbatim OK
4. No unexplained console errors / HTTP 5xx in P0 flows
5. Every PASS has evidence from the reported run
6. Final run of all ready TCs after the last fix, on the hand-over build

## Workflow
- [ ] T0 Init  - [ ] T1 Design  - [ ] T2 Review  - [ ] T3 Implement  - [ ] T4 Execute  - [ ] T5 Fix loop  - [ ] T6 Complete

## Log (ISO · phase · event · evidence)
- {now} · T0 · test run dir created

## Roster (name · role · state · handoff)

## Open questions (to the lead / user)

## Deviations from plan
none

## Blocking factors
none

## Residual risks
none

## Lessons learned
none

## Fact / Assumption / Unknown
- Fact:
- Assumption:
- Unknown:
"""


def cmd_init(a):
    root = repo_root(a.root)
    run = Run(root, a.slug)
    os.makedirs(run.qa, exist_ok=True)
    made = []
    for src, dst in (('profile.yml', 'profile.yml'), ('playwright.config.ts', 'playwright.config.ts'),
                     ('evidence.ts', os.path.join('lib', 'evidence.ts'))):
        d = os.path.join(run.qa, dst)
        if not os.path.exists(d):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy(os.path.join(TPL, src), d)
            made.append(_rel(d, root))
    for sub in ('tests', 'runs', 'defects', 'reviews', 'handoff', 'baseline'):
        os.makedirs(os.path.join(run.dir, sub), exist_ok=True)
    base = a.base or git(root, 'rev-parse', 'HEAD') or '(no git)'
    mode = 'wave' if a.wave else 'standalone'
    if not os.path.exists(run.cases_path):
        tpl = open(os.path.join(TPL, 'testcases.yml'), encoding='utf-8').read()
        tpl = tpl.replace('slug: <slug>', f'slug: {a.slug}').replace('base: <BASE sha>', f'base: {base}')
        tpl = tpl.replace('mode: wave            # wave | standalone',
                          f'mode: {mode}            # wave | standalone\nwave: {a.wave or "null"}')
        open(run.cases_path, 'w', encoding='utf-8').write(tpl)
        made.append(_rel(run.cases_path, root))
    st = os.path.join(run.dir, 'STATUS.md')
    if not os.path.exists(st):
        open(st, 'w', encoding='utf-8').write(STATUS_TPL.format(slug=a.slug, now=now(), mode=mode, wave=a.wave or '-', base=base))
        made.append(_rel(st, root))
    if git(root, 'rev-parse', '--git-dir'):
        ex = git(root, 'rev-parse', '--git-path', 'info/exclude')
        ex = ex if os.path.isabs(ex) else os.path.join(root, ex)
        os.makedirs(os.path.dirname(ex), exist_ok=True)
        lines = open(ex, encoding='utf-8').read().splitlines() if os.path.exists(ex) else []
        if '/.qa/' not in lines:
            with open(ex, 'a', encoding='utf-8', newline='\n') as f:
                f.write('/.qa/\n')
            made.append('.git/info/exclude += /.qa/')
    print(f'test run: {run.dir}')
    print(f'BASE: {base} · mode: {mode}' + (f' · wave: .wave/{a.wave}' if a.wave else ''))
    for m in made:
        print(f'  created {m}')
    if not os.path.isdir(os.path.join(run.qa, 'node_modules', '@playwright')):
        print(f'next: fill .qa/profile.yml, then: bash {SKILL}/scripts/pw-setup.sh {root}')


# ---------------------------------------------------------------- lint

def lint(run, spec=None, impl=False, ready=False):
    doc = run.doc()
    errors, warns = [], []
    basis = doc['basis']
    cases = doc['cases']
    bids = {}
    for b in basis:
        bid = b.get('id')
        if not bid:
            errors.append(f'basis item without id: {b}')
            continue
        if bid in bids:
            errors.append(f'duplicate basis id {bid}')
        bids[bid] = b
        k = b.get('kind')
        if k not in KINDS:
            errors.append(f'{bid}: kind "{k}" not in {KINDS}')
        elif not re.fullmatch(KIND_ID[k], bid):
            warns.append(f'{bid}: id does not follow the {k} pattern {KIND_ID[k]}')
        if not b.get('text'):
            errors.append(f'{bid}: text missing')
        if b.get('priority') not in PRIORITIES:
            errors.append(f'{bid}: priority must be one of {PRIORITIES}')
        if k == 'impact':
            if not b.get('changed'):
                errors.append(f'{bid}: impact item needs changed: [paths] (qa.py select uses them)')
            ev = str(b.get('evidence') or '')
            if not ev:
                errors.append(f'{bid}: impact item needs evidence (codegraph/grep caller chain)')
            elif ev.upper().startswith('ASSUMPTION'):
                warns.append(f'{bid}: impact evidence is an ASSUMPTION — reviewer must confirm')

    profile_vps = set((run.profile().get('viewports') or {}).keys())
    cids, sigs = set(), {}
    for c in cases:
        cid = c.get('id', '?')
        if cid in cids:
            errors.append(f'duplicate case id {cid}')
        cids.add(cid)
        if not TC_ID.match(cid):
            errors.append(f'{cid}: id must look like TC-W-001 (TC-<SURFACE>-<3 digits>)')
        for field in ('title', 'covers', 'type', 'priority', 'surface', 'steps', 'expected', 'automation', 'status'):
            if not c.get(field):
                errors.append(f'{cid}: {field} missing')
        if c.get('status') and c['status'] not in CASE_STATUS:
            errors.append(f'{cid}: status "{c["status"]}" not in {CASE_STATUS}')
        if c.get('type') and c['type'] not in TYPES:
            errors.append(f'{cid}: type "{c["type"]}" not in {TYPES}')
        if c.get('priority') and c['priority'] not in PRIORITIES:
            errors.append(f'{cid}: priority "{c["priority"]}" not in {PRIORITIES}')
        if c.get('technique') and c['technique'] not in TECHNIQUES:
            warns.append(f'{cid}: technique "{c["technique"]}" not in {TECHNIQUES}')
        for ref in c.get('covers') or []:
            if ref not in bids:
                errors.append(f'{cid}: covers unknown basis id {ref}')
        if c.get('status') == 'obsolete':
            continue
        steps = c.get('steps') or []
        if len(steps) > MAX_STEPS:
            warns.append(f'{cid}: {len(steps)} steps > {MAX_STEPS} — split into cases with one objective each')
        kinds = set()
        for e in c.get('expected') or []:
            m = re.match(r'^(\w+):\s*(\S.*)$', str(e))
            if not m or m.group(1) not in EXPECT_KINDS:
                errors.append(f'{cid}: expected "{e}" must start with one of {", ".join(k + ":" for k in EXPECT_KINDS)}')
                continue
            kinds.add(m.group(1))
            body = m.group(2)
            if VAGUE.search(body) and not re.search(r'["“”\'«»]|\d', body):
                errors.append(f'{cid}: vague expected "{e}" — quote the exact text or give a number/predicate')
        if c.get('priority') == 'P0' and not kinds & {'ui', 'db', 'net', 'audit', 'url', 'visual'}:
            warns.append(f'{cid}: P0 case asserts only {sorted(kinds)} — add a ui/db/net check')
        for vp in c.get('viewports') or []:
            if profile_vps and vp not in profile_vps:
                errors.append(f'{cid}: viewport "{vp}" not in .qa/profile.yml viewports {sorted(profile_vps)}')
        sig = json.dumps([steps, c.get('expected'), c.get('role'), c.get('data')], sort_keys=True, ensure_ascii=False)
        if sig in sigs:
            warns.append(f'{cid}: same steps/expected/role/data as {sigs[sig]} — duplicate?')
        sigs[sig] = cid
        auto = str(c.get('automation') or '')
        if auto.startswith('manual') and not re.match(r'^manual:\s*\S', auto):
            errors.append(f'{cid}: manual automation needs a reason ("manual: <why>")')
        if impl and c.get('status') == 'ready' and auto and not auto.startswith('manual'):
            path = os.path.join(run.dir, auto.split('#')[0])
            if not os.path.isfile(path):
                errors.append(f'{cid}: automation file {auto} not found')
            elif not re.search('@' + re.escape(cid) + r'(?![\w-])', open(path, encoding='utf-8').read()):
                errors.append(f'{cid}: tag @{cid} not found in {auto}')

    # coverage gate
    live = live_cases(doc)
    rows = []
    for bid, b in bids.items():
        cov = [c for c in live if bid in (c.get('covers') or [])]
        rcov = [c for c in cov if c.get('status') == 'ready']
        rows.append((bid, b.get('kind'), b.get('priority'), len(rcov), len(cov), sorted({c.get('type') for c in cov})))
        if not cov:
            errors.append(f'{bid}: not covered by any case')
        elif ready and not rcov:
            errors.append(f'{bid}: no ready case covers it')
        if b.get('kind') in ('ac', 'ask') and b.get('priority') == 'P0' and not str(b.get('negative', '')).startswith('n/a'):
            if not any(c.get('type') in ('negative', 'security') for c in cov):
                errors.append(f'{bid}: P0 {b["kind"]} has no negative/security case (or set negative: "n/a: <why>")')
        if b.get('kind') in ('impact', 'keep') and not any(c.get('type') == 'regression' for c in cov):
            errors.append(f'{bid}: {b["kind"]} item needs a regression case')
    for key, field in (('surfaces', 'surface'), ('roles', 'role')):
        used = {c.get(field) for c in live}
        for v in doc.get(key) or []:
            if v not in used:
                warns.append(f'{key[:-1]} "{v}" is listed but no case uses it')
    used_vp = {vp for c in live for vp in (c.get('viewports') or [])}
    for v in doc.get('viewports') or []:
        if v not in used_vp:
            warns.append(f'viewport "{v}" is listed but no case runs on it')

    if spec:
        spec_acs = {}
        for line in open(spec, encoding='utf-8'):
            m = re.match(r'^\s*\|?\s*(AC-\d+)\s*\|\s*([^|]+?)\s*\|', line)
            if m:
                spec_acs[m.group(1)] = m.group(2)
        norm = lambda s: re.sub(r'\W+', ' ', str(s)).strip().lower()
        for ac, text in spec_acs.items():
            if ac not in bids:
                errors.append(f'{ac} is in the spec but not in basis (spec changed?)')
            elif norm(bids[ac].get('text')) != norm(text):
                warns.append(f'{ac}: text differs from the spec — reworded? update basis + affected cases')
        for bid, b in bids.items():
            if b.get('kind') == 'ac' and bid not in spec_acs:
                warns.append(f'{bid}: not in the spec any more — mark its cases obsolete?')
    return errors, warns, rows, doc


def cmd_lint(a):
    run = Run(repo_root(a.root), a.slug).need()
    errors, warns, rows, doc = lint(run, a.spec, a.impl, a.ready)
    live = live_cases(doc)
    print(f'testcases: {len(live)} live ({sum(c.get("status") == "ready" for c in live)} ready) · basis: {len(rows)}')
    print(f'{"basis":9} {"kind":7} {"prio":4} {"ready/all":>9}  types')
    for bid, kind, prio, r, n, types in rows:
        print(f'{bid:9} {kind or "?":7} {prio or "?":4} {f"{r}/{n}":>9}  {", ".join(t for t in types if t)}')
    for w in warns:
        print(f'WARN  {w}')
    for e in errors:
        print(f'ERROR {e}')
    covered = sum(1 for r in rows if r[4] > 0)
    print(f'coverage: {covered}/{len(rows)} basis items · errors: {len(errors)} · warnings: {len(warns)}')
    sys.exit(1 if errors else 0)


# ---------------------------------------------------------------- select

def changed_files(root, since):
    files = set(filter(None, git(root, 'diff', '--name-only', since).splitlines()))
    files |= set(filter(None, git(root, 'ls-files', '--others', '--exclude-standard').splitlines()))
    return sorted(f for f in files if not f.startswith('.qa/') and not f.startswith('.wave/'))


def cmd_select(a):
    run = Run(repo_root(a.root), a.slug).need()
    doc = run.doc()
    cases = [c for c in doc['cases'] if c.get('status') == 'ready']
    by_id = {c['id']: c for c in cases}
    bids = {b['id']: b for b in doc['basis'] if b.get('id')}
    pick = {}

    def add(cid, why):
        if cid in by_id:
            pick.setdefault(cid, []).append(why)

    bugs = run.bugs()
    if a.bug:
        bugs = [b for b in bugs if b.get('id') == a.bug]
        if not bugs:
            sys.exit(f'{a.bug} not found in defects/')
    elif not a.stage:
        bugs = [b for b in bugs if b.get('status') in ('fixed', 'retest', 'reopened')]
    else:
        bugs = []
    conf_basis = set()
    for b in bugs:
        for cid in b.get('tcs') or []:
            add(cid, f'confirmation {b["id"]}')
            conf_basis |= set((by_id.get(cid) or {}).get('covers') or [])
        conf_basis |= set(b.get('covers') or [])
    for c in cases:
        shared = conf_basis & set(c.get('covers') or [])
        if shared and c['id'] not in pick:
            add(c['id'], 'regression: same basis ' + ','.join(sorted(shared)))

    if a.stage:
        for c in cases:
            if c.get('stage') == a.stage and c.get('priority') == 'P0':
                add(c['id'], f'stage {a.stage} smoke (P0)')

    if a.since and not a.bug:
        files = changed_files(run.root, a.since)
        hit_any = set()
        for b in bids.values():
            if b.get('kind') != 'impact':
                continue
            hits = [f for f in files if any(match_path(p, f) for p in b.get('changed') or [])]
            if hits:
                hit_any |= set(hits)
                for c in cases:
                    if b['id'] in (c.get('covers') or []):
                        add(c['id'], f'regression: {b["id"]} ← {hits[0]}' + (f' (+{len(hits) - 1})' if len(hits) > 1 else ''))
        uncovered = [f for f in files if f not in hit_any]
        print(f'changed since {a.since}: {len(files)} files, {len(uncovered)} not covered by any IMP item')
        for f in uncovered[:30]:
            print(f'  WARN no IMP covers {f}')
        if len(uncovered) > 30:
            print(f'  … {len(uncovered) - 30} more')

    if not a.bug and not a.stage:
        for c in cases:
            if c.get('priority') == 'P0':
                add(c['id'], 'P0 smoke')
        for cid, e in effective(run, doc).items():
            if e['status'] in ('fail', 'flaky', 'blocked'):
                add(cid, f'{e["status"]} in {e["run"]}')

    auto = sorted(c for c in pick if not str(by_id[c].get('automation', '')).startswith('manual'))
    manual = sorted(c for c in pick if c not in auto)
    print(f'selected: {len(pick)} TCs ({len(auto)} automated, {len(manual)} manual) of {len(cases)} ready')
    for cid in sorted(pick):
        print(f'  {cid}  {by_id[cid].get("priority")}  ' + '; '.join(dict.fromkeys(pick[cid])))
    if auto:
        print(f'--grep "{grep_for(auto)}"')
        print(f'run: cd {run.qa} && QA_SLUG={run.slug} QA_RUN=<run-id> npx playwright test --grep "{grep_for(auto)}"')
    if manual:
        print('manual (record in runs/<run-id>/manual.yml): ' + ' '.join(manual))


# ---------------------------------------------------------------- collect

def walk_specs(suite, out):
    for s in suite.get('specs') or []:
        out.append(s)
    for child in suite.get('suites') or []:
        walk_specs(child, out)


def cmd_collect(a):
    run = Run(repo_root(a.root), a.slug).need()
    rdir = os.path.join(run.dir, 'runs', a.run)
    if not os.path.isdir(rdir):
        sys.exit(f'{rdir} missing — run playwright with QA_RUN={a.run} first')
    rows, unknown = [], []
    pw = os.path.join(rdir, 'pw.json')
    if os.path.isfile(pw):
        data = json.load(open(pw, encoding='utf-8'))
        specs = []
        for s in data.get('suites') or []:
            walk_specs(s, specs)
        acc = {}
        for sp in specs:
            tags = [t.lstrip('@') for t in sp.get('tags') or []]
            tc = next((t for t in tags if TC_ID.match(t)), None)
            if not tc:
                m = TC_IN_TEXT.search(sp.get('title', ''))
                tc = m.group(0) if m else None
            if not tc:
                unknown.append(sp.get('title', '?'))
                continue
            for t in sp.get('tests') or []:
                key = (tc, t.get('projectName') or 'default')
                row = acc.setdefault(key, {'tc': tc, 'title': sp.get('title'), 'viewport': key[1], 'statuses': [],
                                           'duration_ms': 0, 'error': '', 'evidence': [], 'source': 'playwright'})
                for res in t.get('results') or []:
                    st = res.get('status')
                    row['statuses'].append('pass' if st == 'passed' else 'skipped' if st == 'skipped' else 'fail')
                    row['duration_ms'] += res.get('duration') or 0
                    errs = [e.get('message', '') for e in (res.get('errors') or [])] or \
                           ([res['error'].get('message', '')] if res.get('error') else [])
                    if errs and not row['error']:
                        row['error'] = ANSI.sub('', '\n'.join(errs))[:1500]
                    for att in res.get('attachments') or []:
                        p = att.get('path')
                        if p and os.path.isfile(p) and (att.get('contentType', '').startswith('image/') or p.endswith('.zip')):
                            row['evidence'].append(_rel(p, run.dir))
                        elif att.get('body') and att.get('name'):
                            body = base64.b64decode(att['body']).decode('utf-8', 'replace')[:800]
                            row.setdefault('notes', []).append(f'{att["name"]}: {body}')
        for row in acc.values():
            sts = row.pop('statuses')
            fails = sts.count('fail')
            if not sts:
                row['status'] = 'skipped'
            elif fails and fails < len(sts):
                row['status'], row['flaky'] = 'flaky', f'{fails}/{len(sts)} failed'
            else:
                row['status'] = combine(sts)
            rows.append(row)
    # A TC limited to some viewports skips itself on the others; those rows are not results.
    vps = {c.get('id'): set(c.get('viewports') or []) for c in run.doc()['cases']}
    rows = [r for r in rows if not (r['status'] == 'skipped' and vps.get(r['tc']) and r['viewport'] not in vps[r['tc']])]
    man = load_yaml(os.path.join(rdir, 'manual.yml'), []) or []
    for m in man:
        if m.get('status') not in ('pass', 'fail', 'blocked', 'skipped'):
            sys.exit(f'manual.yml: {m.get("tc")} status must be pass|fail|blocked|skipped')
        rows.append({'tc': m['tc'], 'title': m.get('title', ''), 'viewport': m.get('viewport', 'manual'),
                     'status': m['status'], 'duration_ms': 0, 'error': m.get('error', ''), 'actual': m.get('actual', ''),
                     'evidence': [e if not os.path.isabs(e) else _rel(e, run.dir) for e in m.get('evidence') or []],
                     'source': 'manual'})
    if not rows:
        sys.exit(f'no results in {rdir} (pw.json / manual.yml)')
    ready = {c['id'] for c in run.doc()['cases'] if c.get('status') == 'ready'}
    out = {'run': a.run, 'collected': now(), 'build': git(run.root, 'rev-parse', '--short', 'HEAD'),
           'dirty_files': len(git(run.root, 'status', '--porcelain').splitlines()), 'results': rows}
    json.dump(out, open(os.path.join(rdir, 'results.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    counts = {}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    print(f'{a.run}: {len(rows)} results · ' + ' · '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    for r in rows:
        if r['status'] != 'pass':
            print(f'  {r["status"].upper():7} {r["tc"]} [{r["viewport"]}] {(r.get("error") or r.get("actual") or "").splitlines()[0][:120] if (r.get("error") or r.get("actual")) else ""}')
    for r in rows:
        if r['status'] == 'pass' and not r['evidence'] and not r.get('notes'):
            print(f'  WARN pass without evidence: {r["tc"]} [{r["viewport"]}]')
    stray = sorted({r['tc'] for r in rows} - ready)
    if stray:
        print('  WARN results for TCs not ready in testcases.yml: ' + ' '.join(stray))
    for t in unknown:
        print(f'  WARN test without a TC id tag: {t}')


# ---------------------------------------------------------------- status / exit criteria

def evaluate(run, doc):
    errors, _, rows, _ = lint(run, ready=True)
    live = [c for c in doc['cases'] if c.get('status') == 'ready']
    eff = effective(run, doc)
    bugs = run.bugs()
    runs = run.run_ids()

    def rate(prio):
        cs = [c for c in live if c.get('priority') == prio]
        ok = sum(1 for c in cs if eff.get(c['id'], {}).get('status') == 'pass')
        return ok, len(cs)

    p0, p0n = rate('P0')
    p1, p1n = rate('P1')
    covered = sum(1 for r in rows if r[3] > 0)
    blocking = [b for b in bugs if b.get('severity') in ('S1', 'S2') and b.get('status') not in ('closed', 'rejected')]
    loose = [b for b in bugs if b.get('severity') in ('S3', 'S4') and b.get('status') in BUG_OPEN]
    console = [c['id'] for c in live if c.get('priority') == 'P0' and any(
        'console errors / 5xx' in (r.get('error') or '') for r in eff.get(c['id'], {}).get('rows', []))]
    passes = [(c['id'], r) for c in live for r in eff.get(c['id'], {}).get('rows', []) if r['status'] == 'pass']
    no_ev = sorted({cid for cid, r in passes if not r.get('evidence') and not r.get('notes')})
    last = runs[-1] if runs else None
    last_tcs = {r['tc'] for r in run.results(last)['results']} if last else set()
    missing_last = sorted({c['id'] for c in live} - last_tcs)
    crit = [
        ('Bao phủ test basis (mọi mục có TC ready)', covered == len(rows) and not errors, f'{covered}/{len(rows)} mục; lint lỗi {len(errors)}'),
        ('P0 PASS 100%', p0n > 0 and p0 == p0n, f'{p0}/{p0n}'),
        ('P1 PASS ≥ 95%', p1n == 0 or p1 / p1n >= 0.95, f'{p1}/{p1n}'),
        ('0 lỗi S1/S2 còn mở; S3/S4 mở phải được hoãn có đồng ý', not blocking and not loose,
         f'S1/S2 mở {len(blocking)} · S3/S4 chưa xử lý {len(loose)}'),
        ('Không lỗi console / 5xx trong luồng P0', not console, ', '.join(console) or '0'),
        ('Mọi PASS có bằng chứng', not no_ev, ', '.join(no_ev) or 'đủ'),
        ('Lần chạy cuối chứa toàn bộ TC ready', bool(last) and not missing_last,
         f'{last or "chưa chạy"}' + (f' thiếu {len(missing_last)}' if missing_last else '')),
    ]
    return crit, eff, bugs, runs


def cmd_status(a):
    run = Run(repo_root(a.root), a.slug).need()
    doc = run.doc()
    cs = doc['cases']
    by = {}
    for c in cs:
        by[c.get('status')] = by.get(c.get('status'), 0) + 1
    print(f'cases: {len(cs)} · ' + ' · '.join(f'{k} {v}' for k, v in by.items()))
    crit, eff, bugs, runs = evaluate(run, doc)
    print(f'runs: {", ".join(runs) or "none"}')
    st = {}
    for e in eff.values():
        st[e['status']] = st.get(e['status'], 0) + 1
    print('latest result per TC: ' + (' · '.join(f'{k} {v}' for k, v in sorted(st.items())) or 'none'))
    openb = [b for b in bugs if b.get('status') in BUG_OPEN]
    print(f'defects: {len(bugs)} · open {len(openb)}')
    for b in openb:
        print(f'  {b["id"]} {b.get("severity")} {b.get("status")} owner={b.get("owner")} {b.get("title")}')
    print('exit criteria:')
    for name, ok, val in crit:
        print(f'  [{"x" if ok else " "}] {name} — {val}')
    print('VERDICT: ' + ('READY TO HAND OVER' if all(c[1] for c in crit) else 'NOT READY'))


# ---------------------------------------------------------------- report

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#62625d;--line:#deded8;--pass:#1f7a3a;--fail:#b3261e;--warn:#8a5a00;--info:#2457a6;--chip:#efefea}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--card:#1f1f1d;--ink:#ececE8;--mute:#a3a39c;--line:#363633;--pass:#5cc27a;--fail:#ff8a80;--warn:#e0b252;--info:#8fb4ff;--chip:#2a2a27}}
:root[data-theme=dark]{--bg:#141413;--card:#1f1f1d;--ink:#ececE8;--mute:#a3a39c;--line:#363633;--pass:#5cc27a;--fail:#ff8a80;--warn:#e0b252;--info:#8fb4ff;--chip:#2a2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}h1{font-size:24px;margin:8px 0}h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
h3{font-size:15px;margin:0 0 6px}.mute{color:var(--mute)}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin:8px 0}
.verdict{font-size:18px;font-weight:700;padding:10px 14px;border-radius:10px;border:2px solid}.ok{color:var(--pass);border-color:var(--pass)}.bad{color:var(--fail);border-color:var(--fail)}
.b{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid currentColor;white-space:nowrap}
.pass{color:var(--pass)}.fail,.flaky{color:var(--fail)}.blocked,.skipped,.none{color:var(--warn)}.chip{background:var(--chip);border-radius:6px;padding:0 6px;font-size:12px;margin-right:4px;display:inline-block}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:6px;text-align:left;vertical-align:top}th{color:var(--mute);font-weight:600}
.scroll{overflow-x:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}.stat{font-size:22px;font-weight:700}
.shots{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}.shots a{display:block;width:180px}.shots img{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}
.shots figcaption{font-size:12px;color:var(--mute);word-break:break-all}pre{white-space:pre-wrap;word-break:break-word;background:var(--chip);padding:8px;border-radius:6px;font-size:12px;max-height:260px;overflow:auto}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2}
select,input{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
details>summary{cursor:pointer}svg text{fill:var(--ink);font-size:12px}svg .box{fill:var(--card);stroke:var(--line)}svg .arr{stroke:var(--mute);fill:none;marker-end:url(#ah)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}@media (max-width:640px){.pair{grid-template-columns:1fr}.shots a{width:46%}}
"""

SYM = {'pass': '✓ PASS', 'fail': '✗ FAIL', 'flaky': '≈ FLAKY', 'blocked': '⦸ BLOCKED', 'skipped': '– SKIPPED', 'none': '· CHƯA CHẠY'}

JS = """
const q=s=>document.querySelector(s);function f(){const st=q('#fs').value,pr=q('#fp').value,ty=q('#ft').value,su=q('#fu').value,tx=q('#fx').value.toLowerCase();let n=0;
document.querySelectorAll('.tc').forEach(e=>{const ok=(!st||e.dataset.st===st)&&(!pr||e.dataset.pr===pr)&&(!ty||e.dataset.ty===ty)&&(!su||e.dataset.su===su)&&(!tx||e.textContent.toLowerCase().includes(tx));e.style.display=ok?'':'none';n+=ok});q('#fn').textContent=n+' TC';}
document.querySelectorAll('.filters select,.filters input').forEach(e=>e.addEventListener('input',f));
q('#theme').onclick=()=>{const r=document.documentElement;r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'};
"""


def esc(s):
    return html.escape(str(s if s is not None else ''))


def badge(st):
    return f'<span class="b {esc(st)}">{SYM.get(st, esc(st))}</span>'


def md_sections(path, names):
    """Return {heading: text} for '## heading' sections of a markdown file."""
    if not path or not os.path.isfile(path):
        return {}
    text = open(path, encoding='utf-8').read()
    out = {}
    for m in re.finditer(r'^## (.+?)\n(.*?)(?=^## |\Z)', text, re.S | re.M):
        head = m.group(1).strip()
        for n in names:
            if head.lower().startswith(n.lower()):
                out[n] = m.group(2).strip()
    return out


def img(run, rel, embed):
    path = os.path.join(run.dir, rel)
    if embed and os.path.isfile(path) and rel.lower().endswith('.png'):
        src = 'data:image/png;base64,' + base64.b64encode(open(path, 'rb').read()).decode()
    else:
        src = esc(rel)
    if rel.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return f'<a href="{esc(rel)}" target="_blank"><img loading="lazy" src="{src}" alt="{esc(os.path.basename(rel))}"><figcaption>{esc(os.path.basename(rel))}</figcaption></a>'
    return f'<a href="{esc(rel)}">{esc(os.path.basename(rel))}</a>'


def flow_svg(n_basis, n_cases, n_ready, n_runs, n_bugs, n_open, verdict):
    boxes = [('Test basis', f'{n_basis} mục'), ('Test case', f'{n_ready}/{n_cases} ready'), ('Lần chạy', f'{n_runs}'),
             ('Lỗi', f'{n_bugs} · mở {n_open}'), ('Kết luận', verdict)]
    labels = ['thiết kế + review', 'tự động hoá', 'FAIL → BUG', 'đóng hết S1/S2']
    w, gap = 150, 40
    parts = ['<svg viewBox="0 0 {} 110" width="100%" role="img" aria-label="Quy trình kiểm thử">'.format(len(boxes) * (w + gap)),
             '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>']
    for i, (t, v) in enumerate(boxes):
        x = i * (w + gap)
        parts.append(f'<rect class="box" x="{x}" y="30" width="{w}" height="56" rx="8"/><text x="{x + 10}" y="52" font-weight="600">{esc(t)}</text><text x="{x + 10}" y="72">{esc(v)}</text>')
        if i < len(labels):
            x2 = x + w
            parts.append(f'<path class="arr" d="M{x2 + 2} 58 L{x2 + gap - 4} 58"/><text x="{x2 - 10}" y="20">{esc(labels[i])}</text>')
    parts.append('<path class="arr" d="M{0} 88 Q{0} 104 {1} 104 L{2} 104 Q{3} 104 {3} 88" stroke-dasharray="4 3"/>'.format(
        3 * (w + gap) + w / 2, 3 * (w + gap), 2 * (w + gap) + w, 2 * (w + gap) + w / 2))
    parts.append(f'<text x="{2 * (w + gap) + w + 6}" y="100">sửa → test lại</text></svg>')
    return ''.join(parts)


def cmd_report(a):
    run = Run(repo_root(a.root), a.slug).need()
    doc = run.doc()
    crit, eff, bugs, runs = evaluate(run, doc)
    _, warns, rows, _ = lint(run)
    live = live_cases(doc)
    ready = [c for c in live if c.get('status') == 'ready']
    plan = a.plan
    verdict_ok = all(c[1] for c in crit) and not plan
    verdict = 'KẾ HOẠCH — CHƯA CHẠY' if plan else ('SẴN SÀNG BÀN GIAO' if verdict_ok else 'CHƯA ĐẠT')
    openb = [b for b in bugs if b.get('status') in BUG_OPEN]
    status_md = os.path.join(run.dir, 'STATUS.md')
    notes = md_sections(status_md, ['Deviations', 'Blocking factors', 'Residual risks', 'Lessons learned', 'Fact / Assumption / Unknown'])
    wave = doc.get('wave')
    wave_status = os.path.join(run.root, '.wave', str(wave), 'STATUS.md') if wave and wave != 'null' else None
    build = md_sections(wave_status, ['Stage log', 'AC board']) if wave_status else {}
    base = doc.get('base') or ''
    diffstat = git(run.root, 'diff', '--shortstat', base) if base and not base.startswith('<') else ''
    o = ['<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>Kiểm thử {esc(doc.get("feature") or run.slug)}</title><style>{CSS}</style></head><body><main>',
         f'<div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><span class="mute">Báo cáo hoàn thành kiểm thử · {esc(run.slug)} · {now()}</span><button id="theme" type="button">Sáng/Tối</button></div>',
         f'<h1>{esc(doc.get("feature") or run.slug)}</h1>']
    p0 = next(c for c in crit if c[0].startswith('P0'))[2]
    o.append(f'<p class="verdict {"ok" if verdict_ok else "bad"}">{"✓" if verdict_ok else "✗"} {verdict}</p>')
    summary = (f'{len(ready)} test case ready / {len(rows)} mục test basis. ' +
               ('Chưa có lần chạy.' if not runs else f'P0 PASS {p0}; lỗi mở {len(openb)} ({sum(1 for b in openb if b.get("severity") in ("S1", "S2"))} nghiêm trọng S1/S2). Lần chạy cuối: {runs[-1]}.'))
    o.append(f'<p>{esc(summary)} Chế độ: {esc(doc.get("mode"))}{(" · wave " + esc(wave)) if wave and wave != "null" else ""} · BASE {esc(str(base)[:10])}.</p>')
    o.append('<h2>Quy trình</h2><div class="card scroll"><div style="min-width:760px">' + flow_svg(len(rows), len(live), len(ready), len(runs), len(bugs), len(openb), verdict) + '</div></div>')
    if not plan:
        o.append('<h2>Tiêu chí kết thúc</h2><div class="card scroll"><table><tr><th>Tiêu chí</th><th>Đạt?</th><th>Giá trị đo</th></tr>')
        for name, ok, val in crit:
            o.append(f'<tr><td>{esc(name)}</td><td>{badge("pass" if ok else "fail")}</td><td>{esc(val)}</td></tr>')
        o.append('</table></div>')
    # measures
    cnt = {}
    for c in ready:
        st = eff.get(c['id'], {}).get('status', 'none')
        cnt[st] = cnt.get(st, 0) + 1
    o.append('<h2>Số liệu</h2><div class="grid">')
    for st in ('pass', 'fail', 'flaky', 'blocked', 'skipped', 'none'):
        if cnt.get(st) or st in ('pass', 'fail'):
            o.append(f'<div class="card"><div class="stat {st}">{cnt.get(st, 0)}</div>{SYM[st]}</div>')
    o.append('</div>')
    for key, label in (('priority', 'Theo mức ưu tiên'), ('type', 'Theo loại test'), ('surface', 'Theo bề mặt')):
        vals = sorted({str(c.get(key)) for c in ready})
        o.append(f'<details class="card"><summary>{label}</summary><div class="scroll"><table><tr><th>{key}</th><th>TC</th><th>PASS</th><th>FAIL/FLAKY</th><th>Chưa chạy/khác</th></tr>')
        for v in vals:
            cs = [c for c in ready if str(c.get(key)) == v]
            s = [eff.get(c['id'], {}).get('status', 'none') for c in cs]
            o.append(f'<tr><td>{esc(v)}</td><td>{len(cs)}</td><td>{s.count("pass")}</td><td>{s.count("fail") + s.count("flaky")}</td><td>{len(s) - s.count("pass") - s.count("fail") - s.count("flaky")}</td></tr>')
        o.append('</table></div></details>')
    # coverage matrix
    bmap = {b['id']: b for b in doc['basis'] if b.get('id')}
    o.append('<h2>Ma trận bao phủ (test basis → test case)</h2><div class="card scroll"><table><tr><th>Mục</th><th>Loại</th><th>Ưu tiên</th><th>Nội dung</th><th>Test case (kết quả mới nhất)</th></tr>')
    for bid, b in bmap.items():
        cs = [c for c in live if bid in (c.get('covers') or [])]
        cells = ' '.join(f'<span class="chip">{esc(c["id"])} {SYM.get(eff.get(c["id"], {}).get("status", "none"), "")[:1]}</span>' for c in cs) or '<span class="b fail">✗ chưa có</span>'
        extra = ''
        if b.get('kind') == 'impact':
            extra = f'<div class="mute">đổi: {esc(", ".join(b.get("changed") or []))} → {esc(", ".join(b.get("reaches") or []))}<br>căn cứ: {esc(b.get("evidence"))}</div>'
        o.append(f'<tr><td>{esc(bid)}</td><td>{esc(b.get("kind"))}</td><td>{esc(b.get("priority"))}</td><td>{esc(b.get("text"))}{extra}</td><td>{cells}</td></tr>')
    o.append('</table></div>')
    if warns:
        o.append('<details class="card"><summary>Cảnh báo lint (' + str(len(warns)) + ')</summary><pre>' + esc('\n'.join(warns)) + '</pre></details>')
    # defects
    if not plan:
        o.append(f'<h2>Lỗi ({len(bugs)} · đang mở {len(openb)})</h2>')
        if openb:
            o.append('<div class="card"><h3>Gửi team thi công — lỗi đang mở</h3><div class="scroll"><table><tr><th>ID</th><th>Mức</th><th>Trạng thái</th><th>Owner</th><th>TC</th><th>Mô tả</th></tr>')
            for b in openb:
                o.append(f'<tr><td><a href="{esc(b["_path"])}">{esc(b["id"])}</a></td><td>{esc(b.get("severity"))}/{esc(b.get("priority"))}</td><td>{esc(b.get("status"))}</td><td>{esc(b.get("owner"))}</td><td>{esc(", ".join(b.get("tcs") or []))}</td><td>{esc(b.get("title"))}</td></tr>')
            o.append('</table></div></div>')
        for b in bugs:
            hist = '\n'.join(str(h) for h in b.get('history') or [])
            o.append(f'<details class="card"><summary><b>{esc(b["id"])}</b> {esc(b.get("severity"))} · {esc(b.get("status"))} · mở lại {esc(b.get("reopen_count", 0))} lần — {esc(b.get("title"))}</summary>'
                     f'<p class="mute">owner {esc(b.get("owner"))} · TC {esc(", ".join(b.get("tcs") or []))} · basis {esc(", ".join(b.get("covers") or []))} · build {esc(b.get("build"))} · fix {esc(b.get("fix_commit") or "-")}</p>'
                     f'<pre>{esc(hist)}</pre><pre>{esc(b["_body"].strip())}</pre></details>')
    # run history + before/after
    if runs:
        o.append('<h2>Lịch sử chạy</h2><div class="card scroll"><table><tr><th>Lần chạy</th><th>Build</th><th>Kết quả</th><th>PASS</th><th>FAIL</th><th>Khác</th></tr>')
        hist = {}
        for rid in runs:
            res = run.results(rid)
            by = {}
            for r in res['results']:
                by.setdefault(r['tc'], []).append(r)
            agg = {tc: combine([r['status'] for r in rs]) for tc, rs in by.items()}
            hist[rid] = (agg, by)
            v = list(agg.values())
            dirty = f' (+{res.get("dirty_files")} file chưa commit)' if res.get('dirty_files') else ''
            o.append(f'<tr><td>{esc(rid)}</td><td>{esc(res.get("build"))}{esc(dirty)}</td><td>{len(v)} TC</td><td>{v.count("pass")}</td><td>{v.count("fail") + v.count("flaky")}</td><td>{len(v) - v.count("pass") - v.count("fail") - v.count("flaky")}</td></tr>')
        o.append('</table></div>')
        pairs = []
        for c in ready:
            seq = [(rid, hist[rid]) for rid in runs if c['id'] in hist[rid][0]]
            fails = [(rid, h) for rid, h in seq if h[0][c['id']] in ('fail', 'flaky')]
            if fails and seq[-1][1][0][c['id']] == 'pass':
                pairs.append((c, fails[-1], seq[-1]))
        if pairs:
            o.append(f'<h2>Trước / sau khi sửa ({len(pairs)} TC)</h2>')
            for c, (rf, hf), (rp, hp) in pairs:
                def shots(h):
                    ev = [e for r in h[1][c['id']] for e in r.get('evidence') or []]
                    return ''.join(img(run, e, a.embed) for e in ev[:3]) or '<span class="mute">không có ảnh</span>'
                o.append(f'<div class="card"><h3>{esc(c["id"])} {esc(c.get("title"))}</h3><div class="pair"><div>{badge("fail")} {esc(rf)}<div class="shots">{shots(hf)}</div></div>'
                         f'<div>{badge("pass")} {esc(rp)}<div class="shots">{shots(hp)}</div></div></div></div>')
    # build section
    if build or diffstat:
        o.append('<h2>Thi công</h2><div class="card">')
        if diffstat:
            o.append(f'<p>Thay đổi so với BASE: {esc(diffstat)}</p>')
        for k, v in build.items():
            o.append(f'<details><summary>{esc(k)}</summary><pre>{esc(v)}</pre></details>')
        o.append('</div>')
    # cases
    o.append(f'<h2>Chi tiết test case</h2><div class="filters">'
             '<select id="fs" aria-label="Trạng thái"><option value="">Mọi trạng thái</option>' + ''.join(f'<option value="{k}">{v}</option>' for k, v in SYM.items()) + '</select>'
             '<select id="fp" aria-label="Ưu tiên"><option value="">Mọi ưu tiên</option>' + ''.join(f'<option>{p}</option>' for p in PRIORITIES) + '</select>'
             '<select id="ft" aria-label="Loại"><option value="">Mọi loại</option>' + ''.join(f'<option>{esc(t)}</option>' for t in sorted({str(c.get("type")) for c in live})) + '</select>'
             '<select id="fu" aria-label="Bề mặt"><option value="">Mọi bề mặt</option>' + ''.join(f'<option>{esc(t)}</option>' for t in sorted({str(c.get("surface")) for c in live})) + '</select>'
             f'<input id="fx" type="search" placeholder="Tìm…" aria-label="Tìm"><span id="fn" class="mute">{len(live)} TC</span></div>')
    for c in live:
        e = eff.get(c['id'], {})
        st = 'none' if plan else e.get('status', 'none')
        o.append(f'<div class="card tc" data-st="{esc(st)}" data-pr="{esc(c.get("priority"))}" data-ty="{esc(c.get("type"))}" data-su="{esc(c.get("surface"))}">'
                 f'<h3>{badge(st)} {esc(c["id"])} · {esc(c.get("title"))}</h3>'
                 f'<div><span class="chip">{esc(c.get("priority"))}</span><span class="chip">{esc(c.get("type"))}</span><span class="chip">{esc(c.get("technique") or "-")}</span>'
                 f'<span class="chip">{esc(c.get("surface"))}</span><span class="chip">vai trò {esc(c.get("role") or "-")}</span><span class="chip">{esc(", ".join(c.get("viewports") or []))}</span>'
                 f'<span class="chip">covers {esc(", ".join(c.get("covers") or []))}</span>{"<span class=chip>" + esc(c["stage"]) + "</span>" if c.get("stage") else ""}<span class="chip">{esc(c.get("status"))}</span></div>')
        o.append('<details><summary>Bước & kết quả mong đợi</summary>')
        if c.get('preconditions'):
            o.append('<p class="mute">Tiền điều kiện:</p><ul>' + ''.join(f'<li>{esc(p)}</li>' for p in c['preconditions']) + '</ul>')
        o.append('<ol>' + ''.join(f'<li>{esc(s)}</li>' for s in c.get('steps') or []) + '</ol><p class="mute">Mong đợi:</p><ul>' +
                 ''.join(f'<li>{esc(x)}</li>' for x in c.get('expected') or []) + f'</ul><p class="mute">Tự động hoá: {esc(c.get("automation"))}</p></details>')
        if not plan:
            for r in e.get('rows', []):
                o.append(f'<div style="margin-top:6px">{badge(r["status"])} <b>{esc(r["viewport"])}</b> <span class="mute">{esc(e.get("run"))} · {r.get("duration_ms", 0) // 1000}s {esc(r.get("flaky", ""))}</span>')
                if r.get('actual'):
                    o.append(f'<div>Thực tế: {esc(r["actual"])}</div>')
                if r.get('error'):
                    o.append(f'<pre>{esc(r["error"])}</pre>')
                if r.get('notes'):
                    o.append(f'<pre>{esc(chr(10).join(r["notes"]))}</pre>')
                ev = r.get('evidence') or []
                if ev:
                    o.append('<div class="shots">' + ''.join(img(run, x, a.embed) for x in ev) + '</div>')
                o.append('</div>')
            bl = [b['id'] for b in bugs if c['id'] in (b.get('tcs') or [])]
            if bl:
                o.append(f'<p class="mute">Lỗi liên quan: {esc(", ".join(bl))}</p>')
        o.append('</div>')
    # completion notes
    o.append('<h2>Sai lệch · Cản trở · Rủi ro còn lại · Bài học</h2><div class="card">')
    for k, label in (('Deviations', 'Sai lệch so với kế hoạch'), ('Blocking factors', 'Yếu tố cản trở'),
                     ('Residual risks', 'Rủi ro còn lại'), ('Lessons learned', 'Bài học')):
        o.append(f'<h3>{label}</h3><pre>{esc(notes.get(k, "chưa ghi"))}</pre>')
    o.append('</div><h2>Fact / Assumption / Unknown</h2><div class="card"><pre>' + esc(notes.get('Fact / Assumption / Unknown', 'chưa ghi')) + '</pre></div>')
    srcs = ['.qa/' + run.slug + '/testcases.yml', '.qa/' + run.slug + '/STATUS.md'] + [f'.qa/{run.slug}/runs/{r}/results.json' for r in runs] + \
           [f'.qa/{run.slug}/{b["_path"]}' for b in bugs] + ([_rel(wave_status, run.root)] if wave_status and os.path.isfile(wave_status) else [])
    o.append('<h2>Nguồn</h2><div class="card"><ul>' + ''.join(f'<li><code>{esc(s)}</code></li>' for s in srcs) + '</ul>'
             '<p class="mute">Số liệu tính bởi qa.py từ các file trên; trạng thái từng TC = kết quả của lần chạy gần nhất có TC đó.</p></div>')
    o.append(f'</main><script>{JS}</script></body></html>')
    out = a.out or os.path.join(run.dir, 'plan.html' if plan else 'report.html')
    open(out, 'w', encoding='utf-8').write('\n'.join(o))
    print(f'{out} · {verdict} · {len(live)} TC · {len(runs)} runs · {len(bugs)} defects ({len(openb)} open)')


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', help='repo root (default: git toplevel or cwd)')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('init', help='create .qa/<slug>/')
    s.add_argument('slug'); s.add_argument('--wave'); s.add_argument('--base')
    s = sub.add_parser('lint', help='validate testcases.yml + coverage gate')
    s.add_argument('slug'); s.add_argument('--spec', help='wave spec.md: compare its AC table with basis')
    s.add_argument('--impl', action='store_true', help='ready TCs must have their @tag in the automation file')
    s.add_argument('--ready', action='store_true', help='coverage counts ready cases only')
    s = sub.add_parser('select', help='TCs to re-run after a fix')
    s.add_argument('slug'); s.add_argument('--since', help='git rev; files changed since it drive impact regression')
    s.add_argument('--bug', help='only this defect: confirmation + same-basis regression (builder self-check)')
    s.add_argument('--stage', help='P0 TCs of this stage (per-stage smoke)')
    s = sub.add_parser('collect', help='normalize a run into results.json')
    s.add_argument('slug'); s.add_argument('--run', required=True)
    s = sub.add_parser('status', help='summary + exit criteria')
    s.add_argument('slug')
    s = sub.add_parser('report', help='HTML test completion report')
    s.add_argument('slug'); s.add_argument('--plan', action='store_true', help='design only, before execution')
    s.add_argument('--embed', action='store_true', help='inline PNG evidence (bigger file, shareable alone)')
    s.add_argument('--out')
    for sp in sub.choices.values():
        sp.add_argument('--root', default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    a = p.parse_args()
    a.root = getattr(a, 'root', None)
    {'init': cmd_init, 'lint': cmd_lint, 'select': cmd_select, 'collect': cmd_collect,
     'status': cmd_status, 'report': cmd_report}[a.cmd](a)


if __name__ == '__main__':
    main()
