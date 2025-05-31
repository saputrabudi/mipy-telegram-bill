import os

# Baca file asli
with open('telegram_bot.py', 'r', encoding='utf-8') as file:
    content = file.read()

# Cari bagian kode yang error dan perbaiki
# 1. Menghapus bagian kode yang bermasalah
content = content.replace("""            # Kirim notifikasi ke admin
            admin_message = (
                f"ℹ️ Voucher baru dibuat oleh reseller!\\n\\n"
                f"Reseller: {reseller_name} ({chat_id})\\n"
                f"Profile: {voucher_info['profile']}\\n"
                f"Username: {voucher_info['username']}\\n"
                f"Password: {voucher_info['password']}\\n"
                f"Harga: Rp {price:,}\\n"
                f"Saldo reseller: Rp {balance:,}"
            )
            send_admin_notification(context, admin_message)""", "")

# Simpan ke file baru
with open('telegram_bot_fixed.py', 'w', encoding='utf-8') as file:
    file.write(content)

print("File telegram_bot_fixed.py telah dibuat dengan perbaikan") 