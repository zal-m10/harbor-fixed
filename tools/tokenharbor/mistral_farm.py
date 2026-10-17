#!/usr/bin/env python3
"""
Mistral AI free-key farm (Ory registration/api chain).
Adapted for VPS: proxy from /root/universal-farm/tools/proxies.txt (TUI-managed),
no WARP dependency. Pure HTTP, no browser.

Chain:
  1. tempmail.lol v2 inbox create -> check MX of domain BEFORE using.
  2. Ory registration: GET https://auth.mistral.ai/self-service/registration/api
     -> POST ui.action -> 200 session_token.
  3. Email verify (method=code): trigger -> poll inbox for 6-digit code -> submit.
  4. Key mint: console.mistral.ai session cookie flow -> POST /api/billing/api-keys.

Account file: /root/mistral_keys.txt (email|password|session_token|status|api_key)
Progress:     /root/mistral_farm_progress.txt
Usage:
  python3 /root/mistral_farm.py --count 1
"""
import urllib.request, urllib.parse, urllib.error, json, time, re, subprocess, random, string, sys, os
from pathlib import Path

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36'
KEYS_FILE = '/root/mistral_keys.txt'
PROGRESS  = '/root/mistral_farm_progress.txt'
PROXY_FILES = [Path(__file__).resolve().parent.parent / "proxies.txt"]  # <repo>/tools/proxies.txt

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(PROGRESS, 'a') as f:
        f.write(line + '\n')

def load_proxy():
    """First usable proxy from TUI-managed file, as curl -x value."""
    for p in PROXY_FILES:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                if '://' not in line:
                    line = 'http://' + line
                return line
    return None

PROXY = load_proxy()
if PROXY:
    _masked = PROXY.split('@')[-1] if '@' in PROXY else PROXY
    print(f"[proxy] using {_masked}", flush=True)
else:
    print("[proxy] none found, direct connection", flush=True)

def http(url, method='GET', data=None, headers=None, timeout=30):
    h = ['-H', f'User-Agent: {UA}', '-H', 'Accept: application/json']
    if headers:
        for k, v in headers.items():
            h += ['-H', f'{k}: {v}']
    args = ['curl', '-s', '--max-time', str(timeout), '-w', '\n%{http_code}'] + h
    if PROXY:
        args += ['-x', PROXY]
    if method == 'POST':
        args += ['-X', 'POST']
    if data is not None:
        if isinstance(data, dict):
            args += ['--data', urllib.parse.urlencode(data)]
        else:
            args += ['--data', data]
    args.append(url)
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 15)
    out = r.stdout.rsplit('\n', 1)
    body = out[0] if len(out) > 1 else r.stdout
    code = int(out[-1]) if out[-1].isdigit() else 0
    return code, body

def has_mx(domain):
    try:
        out = subprocess.run(['dig', '+short', 'MX', domain, '@1.1.1.1'],
                             capture_output=True, text=True, timeout=8).stdout.strip()
        return bool(out)
    except Exception:
        return False

def create_inbox(max_tries=12):
    """tempmail.lol inbox with a LIVE MX domain. Returns (address, token, provider)."""
    for i in range(max_tries):
        s, body = http('https://api.tempmail.lol/v2/inbox/create', 'POST', '',
                       {'Content-Type': 'application/json'})
        if s != 201:
            log(f'  inbox create {i}: HTTP {s}, backoff 8s')
            time.sleep(8); continue
        d = json.loads(body)
        addr, tok = d['address'], d['token']
        dom = addr.split('@')[1]
        if has_mx(dom):
            log(f'  inbox OK: {addr} (MX {dom})')
            return addr, tok, 'tempmail'
        log(f'  inbox {i}: {dom} NO MX, discard + retry')
        time.sleep(5)
    return None

def poll_inbox(tok, want_code=True, max_wait=180, provider='tempmail'):
    """Poll tempmail.lol inbox; return (code, flow_id_from_link)."""
    url = f'https://api.tempmail.lol/v2/inbox?token={tok}'
    start = time.time()
    while time.time() - start < max_wait:
        s, body = http(url)
        if s == 200:
            d = json.loads(body)
            for e in d.get('emails', []):
                raw = (e.get('body') or '') + (e.get('html') or '')
                m = re.search(r'verification\?code=(\d{6})&flow=([\w-]+)', raw)
                if m:
                    return m.group(1), m.group(2)
                codes = re.findall(r'\b(\d{6})\b', raw)
                if codes:
                    return codes[0], None
        time.sleep(6)
    return None, None

def ory_register(email, pw):
    """Ory registration API -> session_token."""
    s, body = http('https://auth.mistral.ai/self-service/registration/api')
    if s != 200:
        log(f'  register flow fail: HTTP {s}')
        return None
    d = json.loads(body)
    csrf = [n['attributes'].get('value', '') for n in d['ui']['nodes']
            if n['attributes'].get('name') == 'csrf_token'][0]
    payload = {'csrf_token': csrf, 'traits.email': email, 'password': pw,
               'method': 'password', 'traits.name.first': 'Quart',
               'traits.name.last': 'Farm'}
    s, body = http(d['ui']['action'], 'POST', payload)
    if s != 200:
        log(f'  register fail: HTTP {s} {body[:120]}')
        return None
    return json.loads(body).get('session_token')

def trigger_verify_code(st, email):
    """Create verification flow + trigger code email. Returns flow id."""
    s, body = http('https://auth.mistral.ai/self-service/verification/api',
                   headers={'X-Session-Token': st})
    if s != 200:
        log(f'  verify flow fail: HTTP {s}')
        return None
    d = json.loads(body)
    flow = d['id']
    s, body = http(d['ui']['action'], 'POST',
                   {'csrf_token': '', 'email': email, 'method': 'code'},
                   {'X-Session-Token': st})
    if s != 200:
        log(f'  verify trigger fail: HTTP {s}')
        return None
    log(f'  code sent, polling inbox...')
    return flow

def submit_verify_code(session_token, flow, code):
    action = f'https://auth.mistral.ai/self-service/verification?flow={flow}'
    s, body = http(action, 'POST', {'csrf_token': '', 'code': code, 'method': 'code'},
                   {'X-Session-Token': session_token,
                    'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        j = json.loads(body)
        state = j.get('state')
    except Exception:
        state = f'HTTP{s}'
    return state

def mint_key(email, password, key_name='farm'):
    """Full login -> mint. Returns (api_key, session_cookie_str) or (None, reason)."""
    import http.cookiejar as hcj
    cj = hcj.CookieJar()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), NoRedirect)
    op.addheaders = [('User-Agent', UA), ('Accept', 'application/json')]

    r = op.open(urllib.request.Request(
        'https://auth.mistral.ai/self-service/login/browser?return_to=https%3A%2F%2Fconsole.mistral.ai%2F',
        headers={'Cookie': ''}), timeout=30)
    flow = json.loads(r.read().decode())
    csrf1 = [n['attributes'].get('value','') for n in flow['ui']['nodes'] if n['attributes'].get('name')=='csrf_token'][0]

    def post(url, data):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded',
                     'Referer': 'https://v2.auth.mistral.ai/login'})
        try:
            resp = op.open(req, timeout=30)
            return resp.status, json.loads(resp.read().decode()), None
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try: return e.code, json.loads(raw), e
            except Exception: return e.code, raw[:200], e

    s, j2, e = post(flow['ui']['action'], {'csrf_token': csrf1, 'identifier': email, 'method': 'identifier_first'})
    if s != 400:
        return None, f'login step1 HTTP {s}'
    csrf2 = [n['attributes'].get('value','') for n in j2['ui']['nodes'] if n['attributes'].get('name')=='csrf_token'][0]
    s, j3, e = post(j2['ui']['action'], {'csrf_token': csrf2, 'identifier': email, 'password': password, 'method': 'password'})
    if s != 200:
        return None, f'login password HTTP {s}'
    sess = [c for c in cj if c.name.startswith('ory_session_')]
    if not sess:
        return None, 'no ory_session cookie'
    SESS = f'{sess[0].name}={sess[0].value}'

    r = subprocess.run(['curl','-s','-i','--max-time','20','--compressed',
        '-H', f'User-Agent: {UA}', '-H', f'Cookie: {SESS}',
        'https://console.mistral.ai/api/users/me'], capture_output=True, text=True, timeout=30)
    m = re.search(r'[sS]et-[cC]ookie: csrftoken=([^;]+)', r.stdout)
    if not m:
        return None, 'no csrftoken cookie'
    csrf = m.group(1)

    r = subprocess.run(['curl','-s','--max-time','25','--compressed','-X','POST',
        '-H', f'User-Agent: {UA}', '-H', f'Cookie: {SESS}; csrftoken={csrf}',
        '-H', 'Content-Type: application/json', '-H', f'X-CSRF-Token: {csrf}',
        '--data', json.dumps({'name': key_name, 'expires_at': None}),
        'https://console.mistral.ai/api/billing/api-keys'], capture_output=True, text=True, timeout=40)
    try:
        j = json.loads(r.stdout)
        return j.get('key'), SESS
    except Exception:
        return None, f'mint: {r.stdout[:150]}'

def farm_one(idx):
    log(f'=== account #{idx} ===')
    inbox = create_inbox()
    if not inbox:
        log('  ABORT: no usable inbox'); return None
    email, tok, prov = inbox
    pw = 'Mx#frm' + ''.join(random.choices(string.ascii_letters + string.digits, k=12)) + '!7'

    st = ory_register(email, pw)
    if not st:
        log('  FAIL: register'); return None
    log(f'  registered, session_token {st[:16]}...')

    flow = trigger_verify_code(st, email)
    if not flow:
        log('  FAIL: verify trigger'); return None

    code, link_flow = poll_inbox(tok, want_code=True, max_wait=180)
    if not code:
        log('  FAIL: no code in 180s'); return None
    log(f'  code: {code}')

    state = submit_verify_code(st, link_flow or flow, code)
    log(f'  verify state: {state}')

    status = 'VERIFIED' if state == 'passed_challenge' else f'VERIFY_{state}'
    api_key = None
    if status == 'VERIFIED':
        api_key, sessinfo = mint_key(email, pw, f'farm-{idx}')
        if api_key:
            log(f'  KEY MINTED: {api_key[:14]}...')
            status = 'KEYED'
        else:
            log(f'  mint failed: {sessinfo}')
    row = f"{email}|{pw}|{st}|{status}|{api_key or ''}"
    with open(KEYS_FILE, 'a') as f:
        f.write(row + '\n')
    log(f'  SAVED [{status}]: {email}')
    return {'email': email, 'password': pw, 'session_token': st, 'status': status, 'api_key': api_key}

def main():
    count = 1
    if '--count' in sys.argv:
        count = int(sys.argv[sys.argv.index('--count') + 1])
    ok = 0
    for i in range(1, count + 1):
        r = farm_one(i)
        if r and r['status'] in ('VERIFIED', 'KEYED'):
            ok += 1
        time.sleep(10)
    log(f'=== DONE: {ok}/{count} verified ===')

if __name__ == '__main__':
    main()
