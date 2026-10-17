# Harbor Fixed — Multi-Provider API Key Farm

TUI interaktif untuk farming API key dari beberapa provider AI: **TokenHarbor**, **Mistral AI**, dan **Dahl Inference**. Hasil farm bisa otomatis di-inject ke database **9Router** dan notifikasi dikirim ke **Telegram**.

Fork dari [hirotomasato/harbor](https://github.com/hirotomasato/harbor), dikembangkan jauh melampaui upstream.

## Fitur

- **3 provider**: TokenHarbor (browser Chromium sungguhan), Mistral AI (murni HTTP), Dahl Inference (murni HTTP, tanpa email/captcha)
- **TUI interaktif** — menu bernomor, jalan di terminal
- **Auto-inject 9Router** — key hasil farm otomatis masuk ke SQLite 9Router (berbasis baseUrl, idempoten, skip duplikat)
- **Notifikasi Telegram** — ringkasan + daftar key per run, termasuk progress per 30 key untuk batch besar
- **Rotasi proxy** per akun, format `user:pass@host:port`
- **Pilihan email disposable**: Tempik (instance sendiri) atau Temp Mail (tempmail.lol, tanpa setup)
- **Capsolver opsional** — bisa ON/OFF, farm tetap jalan tanpanya
- **Parallel farm** — semua provider jalan background sekaligus, tahan disconnect SSH

## Instalasi (one-line)

```bash
curl -fsSL https://raw.githubusercontent.com/zal-m10/universal-farm/main/install.sh | bash
```

atau dengan `wget`:

```bash
wget -qO- https://raw.githubusercontent.com/zal-m10/universal-farm/main/install.sh | bash
```

Script installer akan: install paket sistem (python3, git, curl), clone repo ke `~/universal-farm`, buat virtualenv + install dependensi Python, install Chromium untuk Playwright, dan memasang perintah `farm`.

Setelah selesai, ketik `farm` untuk membuka menu.

## Instalasi manual

```bash
git clone https://github.com/zal-m10/universal-farm.git
cd universal-farm
python3 -m venv .venv
.venv/bin/pip install playwright requests rich
.venv/bin/python -m playwright install chromium
# di Debian/Ubuntu, install juga dependensi OS Chromium:
.venv/bin/python -m playwright install-deps chromium
```

Jalankan:

```bash
.venv/bin/python -m tools.tokenharbor.farm_tui
```

## Cara pakai

Menu utama:

| No | Menu | Keterangan |
|----|------|------------|
| 1 | Farm TokenHarbor | Farming akun TokenHarbor (browser) |
| 2 | Farm Mistral keys | Farming API key Mistral AI (HTTP) |
| 3 | Farm Dahl keys | Farming API key Dahl Inference (HTTP) |
| 4 | Parallel farm | Semua provider jalan background sekaligus |
| 5 | Delay setting | Jeda antar akun (detik), default 30 |
| 6 | Setup Proxy | Tambah/hapus proxy |
| 7 | Setup Bot Tele | Token bot + chat ID Telegram |
| 0 | Exit | |

### Submenu Farm TokenHarbor

| No | Menu | Keterangan |
|----|------|------------|
| 1 | Run farm | foreground (live) atau background |
| 2 | Results | lihat/hapus hasil, salin semua key |
| 3 | Setup email | pilih **Tempik** atau **Temp Mail**; atur URL Tempik |
| 4 | Setup capsolver | toggle ON/OFF, set/hapus API key |
| 5 | Auto inject 9Router | ON/OFF |
| 0 | Back | |

Submenu Mistral dan Dahl strukturnya sama (Run farm, Results, Auto inject 9Router).

## Setup

### Proxy — [6] Setup Proxy

Satu proxy per baris di `tools/proxies.txt`, format:

```
user:pass@host:port
```

> **Penting:** `@` sebelum host itu wajib. Format `user:pass:host:port` (titik dua) **salah** dan bikin koneksi proxy gagal.

File ini tidak ikut ke repo (gitignored) karena berisi kredensial.

### Email disposable — [1] > [3] Setup email

Dua pilihan:

- **Tempik** — instance Tempik milikmu sendiri. Masukkan base URL-nya, misal `https://tempik.domain-kamu.com`.
- **Temp Mail** — pakai tempmail.lol, tanpa setup apa-apa. Catatan: pengiriman email verifikasi ke domain temp-mail belum selalu konsisten — kalau verifikasi tidak masuk, pakai Tempik.

### Capsolver — [1] > [4] Setup capsolver

Opsional. Toggle ON/OFF tersedia; farm TokenHarbor jalan normal tanpa Capsolver karena signup memakai browser Chromium sungguhan (Turnstile terverifikasi otomatis). Key disimpan di `tools/.capsolver_key` (gitignored).

### Bot Telegram — [7] Setup Bot Tele

Isi Bot Token (dari [@BotFather](https://t.me/BotFather)) dan Chat ID. Setelah itu setiap farm selesai mengirim ringkasan + daftar API key ke Telegram. Untuk batch besar, progress dikirim tiap 30 key baru.

## Auto-inject 9Router

Kalau diaktifkan, key hasil farm otomatis dimasukkan ke SQLite 9Router (`/var/lib/9router/db/data.sqlite`):

- Node dicari berdasarkan **baseUrl** (bukan nama) — node yang sudah ada dipakai ulang, tidak bikin duplikat
- Prefix default: `HrbrFarm` (TokenHarbor), `mstrlfarm` (Mistral), `DahlFarm` (Dahl)
- Key yang sudah ada di-skip; run kedua idempoten (aman diulang)

## File hasil

| Provider | File |
|----------|------|
| TokenHarbor | `account.json` (email, password, API key) |
| Mistral | `/root/mistral_keys.txt` |
| Dahl | `/root/dahl_keys.txt` |

File kredensial dan proxy (`tools/.capsolver_key`, `tools/proxies.txt`, `account.json`) tidak di-commit ke repo.

## Termux (Android)

```bash
pkg update -y && pkg install -y python git curl
git clone https://github.com/zal-m10/universal-farm
cd universal-farm
python -m venv .venv
.venv/bin/pip install requests rich playwright
```

> **Batasan Termux:** Chromium Playwright tidak jalan di Android, jadi **Farm TokenHarbor (browser) tidak bisa di Termux** — pakai VPS untuk itu. **Farm Mistral dan Dahl (murni HTTP) jalan normal di Termux.**

Lalu:

```bash
.venv/bin/python -m tools.tokenharbor.farm_tui
```

## Troubleshooting

**`farm: command not found`** — installer menaruhnya di `~/.local/bin`; tambahkan ke PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

**`ERR_PROXY_CONNECTION_FAILED`** — cek format proxy: harus `user:pass@host:port` (pakai `@`, bukan `:` sebelum host).

**"You're doing that a bit fast — take a breath and try again"** — rate limit signup TokenHarbor (server-side, bukan IP/email). Berhenti total beberapa jam, lalu coba 1 akun dengan delay panjang (misal 1800 detik).

**Email verifikasi tidak masuk (Temp Mail)** — coba pakai Tempik (instance sendiri) yang pengirimannya lebih konsisten.

**`bash: tools/.capsolver_key: No such file or directory`** — perintah dijalankan di luar folder repo. `cd universal-farm` dulu.

## Perbedaan dari upstream

- Signup TokenHarbor via **browser Chromium sungguhan** (bukan HTTP-only) — Turnstile lolos verifikasi native
- Login via Supabase password-grant langsung (fallback saat Server Action 500)
- Perbaikan multipart `_build_multipart_body` (field `0` = `["$K1"]`)
- TUI multi-provider: TokenHarbor, Mistral, Dahl
- Auto-inject 9Router berbasis baseUrl + notifikasi Telegram
- Dukungan Temp Mail (tempmail.lol) sebagai alternatif Tempik
- Capsolver opsional (ON/OFF)

## Lisensi

MIT
