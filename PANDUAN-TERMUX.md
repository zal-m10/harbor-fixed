# Panduan Menjalankan Harbor di Termux (Android)

Harbor = tool auto-create akun TokenHarbor (CLI Python, HTTP-only, tanpa browser).

## 1. Persiapan Termux

```bash
pkg update -y && pkg install -y python git
pip install rich requests
```

## 2. Clone dan setup

```bash
git clone https://github.com/zal-m10/harbor-fixed
cd harbor-fixed
cp tools/tokenharbor/example.config.toml tools/tokenharbor/config.toml
```

## 3. Isi config

Edit `tools/tokenharbor/config.toml`, bagian `[tempik]` — ganti dengan URL
instance Tempik kamu:

```toml
[tempik]
base_url = "https://tempik.domain-kamu.com"
```

## 4. Capsolver key

Simpan API key Capsolver di `tools/.capsolver_key` (satu baris):

```bash
printf '%s\n' 'CAP-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' > tools/.capsolver_key
chmod 600 tools/.capsolver_key
```

Cek balance dulu (gratis, tidak memotong saldo):

```bash
python -c "
import json, urllib.request
key = open('tools/.capsolver_key').read().strip()
req = urllib.request.Request('https://api.capsolver.com/getBalance',
    data=json.dumps({'clientKey': key}).encode(),
    headers={'Content-Type': 'application/json'})
print(json.load(urllib.request.urlopen(req, timeout=20)))
"
```

## 5. Proxy

Satu proxy per baris di `tools/proxies.txt`, format:

```
user:pass@host:port
```

Kalau format proxymu `host:port:user:pass` (misal novaproxy), balik dulu
menjadi `user:pass@host:port`. Cek proxy hidup:

```bash
python -m tools.tokenharbor.cli check-proxies
```

> Wajib pakai proxy residensial/premium — IP datacenter diblokir
> TokenHarbor saat signup.

## 6. Jalankan

```bash
# Test 1 akun dulu (disarankan)
python -m tools.tokenharbor.cli full-setup

# Kalau 1 akun sukses, baru batch
python -m tools.tokenharbor.cli batch 5
```

Hasil akun tersimpan otomatis di `account.json` (email + password + API key).

## 7. Perintah lain

```bash
python -m tools.tokenharbor.cli test-key thk_live_xxxx
python -m tools.tokenharbor.cli create-key --email x --password y
python -m tools.tokenharbor.cli status --email x --password y
python -m tools.tokenharbor.cli enable-free --email x --password y
```

## Catatan biaya

- Capsolver: ~$3 untuk ratusan solve Turnstile.
- Proxy: butuh proxy residensial/premium.

## Yang di-fix dari upstream (hirotomasato/harbor)

- `tools/tokenharbor/client.py` → `_build_multipart_body`: field `0`
  dikirim sebagai `["$K1"]` (sebelumnya `["$undefined","$K1"]`). Tanpa fix
  ini, server memanggil `signUp(undefined, undefined, formData)` sehingga
  email/password terbaca kosong dan signup selalu gagal dengan error
  "Email and password are required."
