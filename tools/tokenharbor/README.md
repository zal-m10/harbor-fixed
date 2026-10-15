# 🏗️ Harbor — TokenHarbor Auto CLI

> **HTTP-only** · **No browser** · **Pure Python**  
> Auto create accounts, generate API keys, and activate free models on TokenHarbor.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/mode-HTTP%20only-orange.svg" alt="HTTP Only">
</p>

---

## ✨ Features

- 🔐 **Auto signup** — Next.js Server Action + Capsolver Turnstile bypass
- 📧 **Disposable email** — Tempik integration, random domain rotation
- 🔑 **API key generation** — Auto create + extract plaintext key
- 🆓 **Free model activation** — One-click enable all free models
- 🚀 **Batch mode** — Create N accounts in one go
- 🛡️ **Proxy auto-check** — Scan 100 proxies before use, filter alive only
- 🎨 **Rich TUI** — Interactive terminal UI with panels, tables, progress bars
- ⚙️ **Config-driven** — Zero hardcode, everything in `config.toml`

## 📦 Requirements

```bash
pip install rich requests
```

## 🚀 Quick Start

```bash
cd /path/to/harbor
source .venv/bin/activate

# Interactive menu (recommended)
python3 -m tools.tokenharbor.cli

# Or one-shot commands
python3 -m tools.tokenharbor.cli full-setup
python3 -m tools.tokenharbor.cli batch 5
python3 -m tools.tokenharbor.cli test-key thk_live_xxxxxxxx
```

## 📋 Menu

| Key | Command | Description |
|:---:|---------|-------------|
| `1` | **Full Setup** | Register → Verify → Login → API Key → Free Models → Test |
| `2` | **Batch Create** | Create multiple accounts at once |
| `3` | **Create API Key** | Login with existing account, create new key |
| `4` | **Test API Key** | Test against all free models |
| `5` | **Enable Free** | Enable free models for existing account |
| `6` | **Account Status** | Check free tier, privacy, API keys |
| `7` | **Check Proxies** | Scan all proxies, show alive/dead |
| `8` | **List Accounts** | View saved accounts from `account.json` |

## 🔧 Configuration

All settings in `tools/tokenharbor/config.toml`:

```toml
[tokenharbor]
base_url = "https://tokenharbor.ai"
turnstile_sitekey = "0x4AAAAAADBuC8Knz1EJZx9-"

[tempik]
base_url = "https://your-tempik-instance.com"    # URL instance Tempik kamu (self-host recommended)

[files]
capsolver_key = "tools/.capsolver_key"
proxy_list = "tools/proxyscrape_premium_http_proxies.txt"
account_output = "account.json"

[models]
free = [
    "deepseek-v4-flash:free",
    "mimo-v2.5:free",
    "qwen3.8-27b:free",
]
```

### 1. Capsolver API Key

Simpan di `tools/.capsolver_key`:

```
CAP-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Daftar di [capsolver.com](https://capsolver.com) — topup ~$3 cukup untuk ratusan solve.

### 2. Premium Proxy

Simpan di `tools/proxyscrape_premium_http_proxies.txt`:

```
user:pass@host:port
user:pass@host:port
...
```

Format proxyscrape premium (satu proxy per baris). Proxy di-scan otomatis — cuma yang alive yang dipake.

### 3. Tempik (Disposable Email)

CLI ini menggunakan [Tempik](https://github.com/hirotomasato/tempik) — disposable email API open-source.

> ⚠️ **Default instance** (`your-tempik-instance.com`) adalah public shared instance.  
> Untuk production / batch massal, **sangat disarankan self-host** Tempik sendiri.

#### Self-host Tempik

```bash
git clone https://github.com/hirotomasato/tempik
cd tempik
```

Lalu update `config.toml`:

```toml
[tempik]
base_url = "https://tempik.your-domain.com"   # 👈 ganti ke instance kamu
```

Tempik akan auto-detect domain yang tersedia dari instance kamu — gak ada hardcode domain.

## 📁 File Structure

```
tools/
├── .capsolver_key                          # Capsolver API key (secret)
├── proxyscrape_premium_http_proxies.txt     # Premium HTTP proxies
└── tokenharbor/
    ├── config.toml      # ⚙️ All configuration
    ├── __init__.py
    ├── client.py        # Core HTTP client (signup, login, API key, free models)
    ├── cli.py           # Interactive CLI + Rich TUI
    ├── capsolver.py     # Capsolver Turnstile solver
    └── tempik.py        # Tempik disposable email client
```

## 🔄 How It Works

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌───────────┐
│  SIGNUP  │───▶│  EMAIL   │───▶│  VERIFY   │───▶│  LOGIN   │───▶│ API KEY   │
│ Next.js  │    │ Tempik   │    │ Email     │    │ Cookie   │    │ POST      │
│ Action   │    │ inbox    │    │ link      │    │ auth     │    │ /api/keys │
└──────────┘    └──────────┘    └───────────┘    └──────────┘    └───────────┘
                                                                      │
                                                               ┌──────▼───────┐
                                                               │  FREE MODELS │
                                                               │  POST        │
                                                               │  /api/me/    │
                                                               │  privacy     │
                                                               └──────────────┘
```

1. **Signup** — Multipart form data ke Next.js Server Action, Turnstile token dari Capsolver
2. **Email** — Tempik disposable inbox, polling verification link
3. **Verify** — GET verification link dengan session cookies
4. **Login** — Server Action signin, extract Supabase chunked cookies → access token
5. **API Key** — `POST /api/keys` dengan cookie auth, ambil `plaintext` key
6. **Free Models** — `POST /api/me/privacy` dengan cookie auth
7. **Test** — `POST /v1/chat/completions` dengan API key Bearer auth

## 🆓 Free Models

| Model ID | Provider |
|---|---|
| `deepseek-v4-flash:free` | DeepSeek |
| `mimo-v2.5:free` | MiMo |
| `qwen3.8-27b:free` | Qwen |

Model list bisa diedit di `config.toml`.

## 📝 CLI Reference

```bash
# Interactive menu
python3 -m tools.tokenharbor.cli

# Full flow (auto email + password)
python3 -m tools.tokenharbor.cli full-setup

# Custom email
python3 -m tools.tokenharbor.cli full-setup --email me@mydomain.com --password 'Str0ng!Pass'

# Batch create N accounts
python3 -m tools.tokenharbor.cli batch 10

# Create key from existing account
python3 -m tools.tokenharbor.cli create-key --email me@mydomain.com --password 'Str0ng!Pass'

# Test an API key
python3 -m tools.tokenharbor.cli test-key thk_live_xxxxxxxx

# Enable free models
python3 -m tools.tokenharbor.cli enable-free --email me@mydomain.com --password 'Str0ng!Pass'

# Check account status
python3 -m tools.tokenharbor.cli status --email me@mydomain.com --password 'Str0ng!Pass'

# Check all proxies
python3 -m tools.tokenharbor.cli check-proxies
```

## 💡 Tips

- Akun otomatis disimpan ke `account.json` (append mode)
- Email pakai random domain dari Tempik (auto-detected)
- Proxy di-scan sebelum create — gak bakal pake proxy mati
- Rate limit TokenHarbor di-bypass via rotasi proxy premium
- Capsolver solve ~3-5 detik per Turnstile
- Batch mode kasih delay 2 detik antar akun

---

<p align="center">
  <sub>by <b>MASANTOID</b> · <a href="https://github.com/hirotomasato/tempik">Tempik</a> · <a href="https://tokenharbor.ai">TokenHarbor</a></sub>
</p>