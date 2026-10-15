# 🏗️ Harbor (Fixed)

> **TokenHarbor Auto CLI** — HTTP-only, no browser, pure Python.

Auto create accounts, generate API keys, and activate free models on [TokenHarbor](https://tokenharbor.ai).

Fixed fork of [hirotomasato/harbor](https://github.com/hirotomasato/harbor).

## Quick Start

```bash
git clone https://github.com/zal-m10/harbor-fixed.git
cd harbor-fixed
python3 -m venv .venv && source .venv/bin/activate
pip install rich requests
cp tools/tokenharbor/example.config.toml tools/tokenharbor/config.toml
# edit config.toml with your Capsolver key + proxy list
python3 -m tools.tokenharbor.cli
```

📱 **Termux (Android):** see [PANDUAN-TERMUX.md](PANDUAN-TERMUX.md) for the full
step-by-step guide in Indonesian.

## Docs

See [tools/tokenharbor/README.md](tools/tokenharbor/README.md) for full documentation.

## Fixes vs upstream

- `tools/tokenharbor/client.py` → `_build_multipart_body`: the multipart field
  `0` is now `["$K1"]` (was `["$undefined","$K1"]`). The old value made the
  server invoke `signUp(undefined, undefined, formData)`, so email/password
  arrived empty and every signup failed with "Email and password are required."

## License

MIT
