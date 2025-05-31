# Mikrotik Hotspot Voucher Generator

MikroTik-Python untuk manajemen dan pembuatan voucher hotspot Mikrotik melalui Telegram.

## Fitur

- Konfigurasi melalui web interface
- Terintegrasi dengan API Mikrotik dengan dukungan SSL
- Bot Telegram untuk manajemen voucher hotspot
- Pembuatan username/password secara acak atau custom
- Pengaturan batas waktu penggunaan voucher
- Melihat daftar voucher yang telah dibuat
- Melihat detail penggunaan voucher (status, uptime, download/upload)
- Monitoring status koneksi Mikrotik melalui Telegram
- Logging untuk memudahkan troubleshooting
- **Sistem Reseller** untuk penjualan voucher melalui bot
- **Sinkronisasi Paket** antara Mikrotik dan aplikasi

## Persyaratan

- Python 3.7+
- RouterOS v6.43+
- Akses API Mikrotik
- Bot Telegram

## Instalasi

1. Clone repositori ini:
   ```
   git clone 
   cd mipy-telegram-bill
   ```

2. Instal dependensi:
   ```
   pip install -r requirements.txt
   ```

3. Jalankan aplikasi lengkap (web + bot telegram):
   ```
   python run.py
   ```

4. Buka browser dan akses `http://localhost:5000`

5. Isi konfigurasi yang diperlukan:
   - IP Mikrotik
   - Port API Mikrotik (default: 8728, untuk API-SSL: 8729)
   - Opsi SSL (aktifkan jika menggunakan API-SSL)
   - Username Mikrotik
   - Password Mikrotik
   - Token Bot Telegram
   - Chat ID Telegram

6. Simpan konfigurasi dan test koneksi

## Penggunaan Bot Telegram

- Kirim `/start` ke bot untuk memulai
- Kirim `/voucher` untuk membuat voucher baru
- Kirim `/list` untuk melihat daftar 10 voucher terakhir
- Kirim `/status` untuk melihat status koneksi dan informasi Mikrotik
- Kirim `/detail` untuk melihat detail penggunaan voucher tertentu
- Kirim `/active` untuk melihat daftar user yang sedang aktif
- Kirim `/saldo` untuk memeriksa saldo (khusus reseller)

### Pembuatan Voucher

Ikuti petunjuk bot untuk mengisi informasi voucher:
- Pilih profile hotspot
- Pilih tipe username (random atau custom)
- Pilih tipe password (random, sama dengan username, atau custom)
- Masukkan batas waktu (contoh: 1h, 1d, none untuk tanpa batas)
- Masukkan komentar (opsional)

### Detail Penggunaan

Dengan perintah `/detail` Anda dapat melihat informasi lengkap tentang voucher:
- Status aktif atau nonaktif
- Limit waktu dan waktu yang telah digunakan
- Status koneksi (online/offline)
- Jika online: IP address, waktu tersisa, penggunaan data (download/upload)

## Fitur Reseller

Aplikasi ini dilengkapi dengan sistem reseller yang memungkinkan:

1. **Manajemen Reseller melalui Web Interface**:
   - Tambah, edit, dan hapus reseller
   - Atur saldo reseller
   - Aktifkan/nonaktifkan akun reseller
   - Test koneksi dengan reseller

2. **Penjualan Voucher oleh Reseller**:
   - Reseller dapat menjual voucher melalui bot Telegram
   - Saldo reseller otomatis berkurang sesuai harga paket
   - Reseller dapat memeriksa saldo dengan perintah `/saldo`

3. **Pengaturan Harga Paket**:
   - Admin dapat mengatur harga setiap paket/profil hotspot
   - Reseller hanya dapat menjual paket yang memiliki harga

4. **Perintah Admin untuk Reseller**:
   - `/checkreseller <chat_id>` - Memeriksa informasi reseller
   - `/checkreseller all` - Melihat semua reseller
   - `/addsaldo <chat_id> <jumlah>` - Menambah saldo reseller

## Sinkronisasi Paket

Aplikasi menyediakan fitur sinkronisasi paket/profil hotspot antara Mikrotik dan aplikasi:

1. **Sinkronisasi Otomatis**:
   - Profil hotspot di Mikrotik dapat disinkronkan dengan aplikasi
   - Harga dan pengaturan profil tetap tersimpan saat sinkronisasi

2. **Pengaturan Profil**:
   - Tetapkan harga untuk setiap profil hotspot
   - Tentukan durasi dan kuota untuk setiap profil (opsional)
   - Profil yang tidak diberi harga tidak akan muncul di menu reseller

3. **Cara Sinkronisasi**:
   - Buka halaman web interface
   - Klik tombol "Sinkronisasi Profil" di bagian pengaturan profil
   - Periksa dan perbarui harga profil yang telah disinkronkan

## Cara Mendapatkan Token Bot Telegram

1. Buka Telegram dan cari @BotFather
2. Kirim perintah `/newbot` dan ikuti instruksi
3. Salin token yang diberikan dan tempel di konfigurasi aplikasi

## Cara Mendapatkan Chat ID Telegram

1. Mulai chat dengan bot @userinfobot di Telegram
2. Bot akan mengirimkan ID Anda, salin dan tempel di konfigurasi aplikasi

## Troubleshooting

- Pastikan API Mikrotik diaktifkan di RouterOS (IP > Services > API)
- Jika menggunakan SSL, aktifkan API-SSL di RouterOS
- Pastikan port API tidak diblokir oleh firewall
- Pastikan token bot Telegram valid dan bot sudah dimulai dengan `/start`
- Periksa file log (app.log dan telegram_bot.log) untuk informasi error

## Keamanan

- Aplikasi menyimpan password dalam plaintext di file config.json
- Untuk keamanan lebih, pasang aplikasi di server lokal (tidak mengekspos ke internet)
- Gunakan API-SSL jika memungkinkan untuk koneksi terenkripsi ke Mikrotik

## Suported by
### Saputra Budi