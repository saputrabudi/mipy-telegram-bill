import os
import json
import logging
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import random
import string
from dotenv import load_dotenv
import librouteros
import ssl
import socket
from datetime import datetime
import qrcode
from PIL import Image, ImageDraw, ImageFont
import io

# Set up logging
logging.basicConfig(
    filename='telegram_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables jika ada
load_dotenv()

# States untuk conversation handler
PROFILE = 0
USERNAME_TYPE = 1
USERNAME = 2
PASSWORD = 3
COMMENT = 4

# States untuk detail handler
DETAIL_USERNAME = 0

# Load config dari file
def load_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            logger.info("Konfigurasi berhasil dimuat dari config.json")
            return config
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Config file tidak ditemukan atau tidak valid: {e}")
        return None

def connect_to_mikrotik(config):
    """Fungsi untuk terhubung ke API Mikrotik"""
    try:
        # Validasi konfigurasi
        if not config or not config.get('IP_MIKROTIK') or not config.get('USERNAME_MIKROTIK'):
            logger.error("Konfigurasi Mikrotik tidak lengkap")
            return None
            
        # Cek koneksi dasar ke host/port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((config['IP_MIKROTIK'], int(config['PORT_API_MIKROTIK'])))
        sock.close()
        
        if result != 0:
            logger.error(f"Port {config['PORT_API_MIKROTIK']} pada {config['IP_MIKROTIK']} tertutup atau tidak dapat dijangkau")
            return None
            
        # Persiapkan argumen koneksi
        kwargs = {
            'host': config['IP_MIKROTIK'],
            'port': int(config['PORT_API_MIKROTIK']),
            'username': config['USERNAME_MIKROTIK'],
            'password': config['PASSWORD_MIKROTIK']
        }
        
        # Konfigurasi SSL jika digunakan
        if config.get('USE_SSL', False):
            logger.info("Menggunakan koneksi SSL untuk API Mikrotik")
            
            # Inisialisasi context SSL
            ctx = ssl.create_default_context()
            
            # Konfigurasi verifikasi SSL
            if not config.get('VERIFY_SSL', True):
                logger.warning("Verifikasi SSL dinonaktifkan")
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            
            # Buat fungsi wrapper khusus yang menyediakan server_hostname
            def ssl_wrapper(sock):
                return ctx.wrap_socket(sock, server_hostname=config['IP_MIKROTIK'])
            
            # Tambahkan wrapper ke argumen
            kwargs['ssl_wrapper'] = ssl_wrapper
        
        # Koneksi ke Mikrotik dengan argumen yang telah disiapkan
        api = librouteros.connect(**kwargs)
        
        logger.info(f"Berhasil terhubung ke Mikrotik API {config['IP_MIKROTIK']}:{config['PORT_API_MIKROTIK']}")
        return api
    except socket.gaierror:
        logger.error(f"Nama host tidak dapat diselesaikan: {config['IP_MIKROTIK']}")
        return None
    except socket.timeout:
        logger.error(f"Koneksi timeout ke {config['IP_MIKROTIK']}:{config['PORT_API_MIKROTIK']}")
        return None
    except librouteros.exceptions.AuthenticationError:
        logger.error("Login gagal: username/password salah")
        return None
    except librouteros.exceptions.ConnectionClosed as e:
        logger.error(f"Error koneksi ke Mikrotik: {e}. Pastikan API service aktif.")
        return None
    except ValueError as e:
        logger.error(f"Error SSL konfigurasi: {e}")
        return None
    except TypeError as e:
        logger.error(f"Error SSL wrapper: {e}")
        return None
    except Exception as e:
        logger.error(f"Error connecting to Mikrotik: {e}")
        return None

def get_hotspot_profiles(api):
    """Mendapatkan daftar profile hotspot dari Mikrotik"""
    try:
        if not api:
            logger.error("Tidak dapat mengambil profile hotspot: API tidak terhubung")
            return []
            
        profiles = api.path('ip/hotspot/user/profile')
        profiles_list = [profile.get('name') for profile in profiles]
        logger.info(f"Berhasil mendapatkan {len(profiles_list)} profile hotspot")
        return profiles_list
    except Exception as e:
        logger.error(f"Error getting hotspot profiles: {e}")
        return []

def generate_random_string(length):
    """Generate random string untuk username/password"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def start(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} ({user.first_name}) memulai bot")
    
    # Cek apakah user adalah reseller
    config = load_config()
    is_reseller_user, reseller_data = is_reseller(chat_id, config)
    
    welcome_message = f'Selamat datang {user.first_name} di Bot Mikrotik Hotspot Voucher Generator!\n'
    welcome_message += 'Gunakan /voucher untuk membuat voucher hotspot baru.\n'
    welcome_message += 'Gunakan /list untuk melihat daftar voucher yang ada.\n'
    welcome_message += 'Gunakan /active untuk melihat daftar user yang sedang aktif.\n'
    welcome_message += 'Gunakan /status untuk melihat status koneksi ke Mikrotik.\n'
    welcome_message += 'Gunakan /detail untuk melihat detail penggunaan voucher.'
    
    if is_reseller_user:
        welcome_message += f'\n\nAnda terdaftar sebagai reseller.\nGunakan /saldo untuk memeriksa saldo Anda.'
    
    # Cek apakah user adalah admin
    admin_chat_id = config.get('TELEGRAM_CHAT_ID')
    if str(chat_id) == str(admin_chat_id):
        welcome_message += f'\n\nPerintah admin:\n'
        welcome_message += '/checkreseller <chat_id> - Memeriksa informasi reseller\n'
        welcome_message += '/checkreseller all - Melihat semua reseller\n'
        welcome_message += '/addsaldo <chat_id> <jumlah> - Menambah saldo reseller'
    
    update.message.reply_text(welcome_message)

def check_balance(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /saldo"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} memeriksa saldo")
    
    config = load_config()
    is_reseller_user, reseller_data = is_reseller(chat_id, config)
    
    if is_reseller_user:
        # Format saldo dengan pemisah ribuan
        balance = "{:,}".format(reseller_data['balance'])
        update.message.reply_text(
            f"💰 Informasi Saldo Reseller\n\n"
            f"Nama: {reseller_data['name']}\n"
            f"Chat ID: {reseller_data['chat_id']}\n"
            f"Saldo: Rp {balance}\n"
            f"Status: {'Aktif' if reseller_data['status'] == 'active' else 'Nonaktif'}"
        )
    else:
        update.message.reply_text("❌ Anda bukan reseller terdaftar.")

def cancel(update: Update, context: CallbackContext) -> int:
    """Handler untuk membatalkan operasi"""
    user = update.effective_user
    logger.info(f"User {user.id} membatalkan operasi")
    update.message.reply_text('Operasi dibatalkan.')
    return ConversationHandler.END

def status(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /status, memeriksa status koneksi Mikrotik"""
    config = load_config()
    if not config:
        update.message.reply_text('❌ Konfigurasi tidak ditemukan. Silakan atur melalui web interface.')
        return
    
    user = update.effective_user
    logger.info(f"User {user.id} memeriksa status koneksi")
    
    update.message.reply_text('🔄 Memeriksa koneksi ke Mikrotik...')
    
    try:
        api = connect_to_mikrotik(config)
        if not api:
            update.message.reply_text('❌ Gagal terhubung ke Mikrotik. Periksa konfigurasi dan pastikan API aktif.')
            return
            
        # Ambil informasi sistem
        system_info = list(api.path('/system/resource'))
        if system_info:
            info = system_info[0]
            uptime = info.get('uptime', 'unknown')
            version = info.get('version', 'unknown')
            cpu_load = info.get('cpu-load', '0')
            free_memory = info.get('free-memory', '0')
            
            message = (
                f"✅ Terhubung ke Mikrotik\n\n"
                f"🖥️ IP: {config['IP_MIKROTIK']}\n"
                f"🔄 Versi: {version}\n"
                f"⏱️ Uptime: {uptime}\n"
                f"📊 CPU: {cpu_load}%\n"
                f"🧠 Free Memory: {int(free_memory)/1024/1024:.2f} MB"
            )
            update.message.reply_text(message)
        else:
            update.message.reply_text('✅ Terhubung ke Mikrotik, tetapi tidak dapat mengambil informasi sistem.')
            
        api.close()
    except Exception as e:
        logger.error(f"Error memeriksa status: {e}")
        update.message.reply_text(f'❌ Error saat memeriksa status Mikrotik: {str(e)}')

def detail_start(update: Update, context: CallbackContext) -> int:
    """Handler untuk command /detail"""
    config = load_config()
    if not config:
        update.message.reply_text('❌ Konfigurasi tidak ditemukan. Silakan atur melalui web interface.')
        return ConversationHandler.END
    
    user = update.effective_user
    logger.info(f"User {user.id} memulai melihat detail voucher")
    
    # Cek koneksi ke Mikrotik terlebih dahulu
    api = connect_to_mikrotik(config)
    if not api:
        update.message.reply_text('❌ Gagal terhubung ke Mikrotik. Periksa konfigurasi dan pastikan API aktif.')
        return ConversationHandler.END
    
    # Tutup koneksi setelah cek
    api.close()
    
    # Minta username voucher yang ingin dilihat detailnya
    update.message.reply_text(
        'Masukkan username voucher yang ingin dilihat detailnya:',
    )
    return DETAIL_USERNAME

def detail_get_username(update: Update, context: CallbackContext) -> int:
    """Handler untuk menerima username voucher yang akan dilihat detailnya"""
    username = update.message.text.strip()
    user = update.effective_user
    logger.info(f"User {user.id} melihat detail voucher untuk username: {username}")
    
    config = load_config()
    if not config:
        update.message.reply_text('❌ Konfigurasi tidak ditemukan.')
        return ConversationHandler.END
    
    update.message.reply_text(f'🔍 Mencari detail untuk username: {username}...')
    
    try:
        # Coba terhubung ke Mikrotik
        api = connect_to_mikrotik(config)
        if not api:
            update.message.reply_text('❌ Gagal terhubung ke Mikrotik.')
            return ConversationHandler.END
        
        # Cari user hotspot berdasarkan username
        try:
            users = api.path('ip/hotspot/user').select('name', 'profile', 'limit-uptime', 'uptime', 'disabled', 'comment', '.id')
            user_found = False
            user_data = None
            
            for u in users:
                if u.get('name') == username:
                    user_found = True
                    user_data = u
                    break
            
            if not user_found:
                api.close()
                update.message.reply_text(f'❌ Username "{username}" tidak ditemukan di daftar user hotspot.')
                return ConversationHandler.END
            
            # Ambil data tambahan dari active users jika ada
            active_data = None
            try:
                active_users = api.path('ip/hotspot/active').select('user', 'uptime', 'session-time-left', 'address', 'bytes-in', 'bytes-out')
                for active in active_users:
                    if active.get('user') == username:
                        active_data = active
                        break
            except Exception as e:
                logger.error(f"Error mengambil data active users: {e}")
            
            # Format pesan
            message = f"📋 Detail Voucher: {username}\n\n"
            message += f"👤 Username: {user_data.get('name', 'N/A')}\n"
            message += f"🔑 Profile: {user_data.get('profile', 'N/A')}\n"
            
            # Status aktif/nonaktif
            is_disabled = user_data.get('disabled', 'false') == 'true'
            message += f"🔴 Status: {'Dinonaktifkan' if is_disabled else 'Aktif'}\n"
            
            # Limit waktu dan penggunaan waktu
            limit_uptime = user_data.get('limit-uptime', 'Tidak ada')
            uptime = user_data.get('uptime', '0s')
            message += f"⏱️ Limit Waktu: {limit_uptime}\n"
            message += f"⌛ Waktu Terpakai: {uptime}\n"
            
            # Tambahkan data dari active user jika tersedia
            if active_data:
                message += f"\n📲 Status Koneksi: ONLINE\n"
                message += f"🕐 Sesi Waktu Tersisa: {active_data.get('session-time-left', 'N/A')}\n"
                message += f"🖥️ IP Address: {active_data.get('address', 'N/A')}\n"
                
                # Format penggunaan data
                bytes_in = int(active_data.get('bytes-in', '0'))
                bytes_out = int(active_data.get('bytes-out', '0'))
                download = format_bytes(bytes_in)
                upload = format_bytes(bytes_out)
                total = format_bytes(bytes_in + bytes_out)
                
                message += f"📥 Download: {download}\n"
                message += f"📤 Upload: {upload}\n"
                message += f"📊 Total Penggunaan: {total}\n"
            else:
                message += f"\n📲 Status Koneksi: OFFLINE\n"
            
            # Tambahkan komentar jika ada
            comment = user_data.get('comment')
            if comment:
                message += f"\n📝 Komentar: {comment}\n"
            
            # Tambahkan ID untuk keperluan admin
            message += f"\n🔢 ID: {user_data.get('.id', 'N/A')}"
            
            api.close()
            update.message.reply_text(message)
            
        except Exception as e:
            api.close()
            logger.error(f"Error mencari user: {e}")
            update.message.reply_text(f'❌ Error saat mencari user: {str(e)}')
    
    except Exception as e:
        logger.error(f"Error saat melihat detail voucher: {e}")
        update.message.reply_text(f'❌ Error: {str(e)}')
    
    return ConversationHandler.END

def format_bytes(size):
    """Format bytes menjadi ukuran yang readable"""
    power = 2**10
    n = 0
    power_labels = {0: '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

def is_reseller(chat_id, config):
    """Cek apakah user adalah reseller"""
    resellers = config.get('RESELLERS', [])
    for reseller in resellers:
        if str(reseller['chat_id']) == str(chat_id) and reseller['status'] == 'active':
            return True, reseller
    return False, None

def get_profile_price(profile_name, config):
    """Mendapatkan harga profil"""
    profile_data = config.get('PROFILE_PRICES', {}).get(profile_name, {})
    if isinstance(profile_data, dict):
        return profile_data.get('price', 0)
    return profile_data if isinstance(profile_data, (int, float)) else 0

def get_profile_settings(profile_name, config):
    """Mendapatkan pengaturan profil (harga, durasi, kuota)"""
    profile_data = config.get('PROFILE_PRICES', {}).get(profile_name, {})
    if isinstance(profile_data, dict):
        return {
            'price': profile_data.get('price', 0),
            'duration': profile_data.get('duration'),
            'quota': profile_data.get('quota')
        }
    return {
        'price': profile_data if isinstance(profile_data, (int, float)) else 0,
        'duration': None,
        'quota': None
    }

def update_reseller_balance(chat_id, amount, config):
    """Update saldo reseller"""
    try:
        resellers = config.get('RESELLERS', [])
        updated = False
        
        for reseller in resellers:
            if str(reseller['chat_id']) == str(chat_id):
                # Pastikan saldo tidak menjadi negatif
                if reseller['balance'] < amount:
                    logger.error(f"Saldo tidak cukup: {reseller['balance']} < {amount}")
                    return False
                
                # Kurangi saldo
                reseller['balance'] = reseller['balance'] - amount
                updated = True
                logger.info(f"Saldo reseller {chat_id} berhasil dikurangi {amount}")
                break
        
        if not updated:
            logger.error(f"Reseller dengan chat_id {chat_id} tidak ditemukan")
            return False
        
        # Simpan perubahan ke file
        with open('config.json', 'w') as f:
            json.dump(config, f)
        
        return True
    except Exception as e:
        logger.error(f"Error saat update saldo reseller: {e}")
        return False

def voucher(update: Update, context: CallbackContext) -> int:
    """Handler untuk command /voucher"""
    config = load_config()
    if not config:
        update.message.reply_text('❌ Konfigurasi tidak ditemukan. Silakan atur melalui web interface.')
        return ConversationHandler.END
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} memulai pembuatan voucher")
    
    # Cek apakah user adalah reseller
    is_reseller_user, reseller_data = is_reseller(chat_id, config)
    if is_reseller_user:
        context.user_data['is_reseller'] = True
        context.user_data['reseller_data'] = reseller_data
        update.message.reply_text(f'💰 Saldo Anda: Rp {reseller_data["balance"]:,}')
    else:
        context.user_data['is_reseller'] = False
    
    update.message.reply_text('🔄 Menghubungkan ke Mikrotik...')
    
    api = connect_to_mikrotik(config)
    if not api:
        update.message.reply_text('❌ Gagal terhubung ke Mikrotik. Periksa konfigurasi dan pastikan API aktif.')
        return ConversationHandler.END
    
    profiles = get_hotspot_profiles(api)
    api.close()
    
    if not profiles:
        update.message.reply_text('❌ Tidak ada profile hotspot yang ditemukan. Pastikan konfigurasi hotspot sudah dibuat di Mikrotik.')
        return ConversationHandler.END
    
    # Filter profil berdasarkan yang memiliki harga (untuk reseller)
    if context.user_data['is_reseller']:
        profiles = [p for p in profiles if get_profile_price(p, config) > 0]
        if not profiles:
            update.message.reply_text('❌ Tidak ada profil hotspot yang tersedia untuk reseller.')
            return ConversationHandler.END
    
    keyboard = []
    for profile in profiles:
        price = get_profile_price(profile, config)
        label = f"{profile} - Rp {price:,}" if context.user_data['is_reseller'] else profile
        keyboard.append([InlineKeyboardButton(label, callback_data=f'profile_{profile}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Pilih profile hotspot:', reply_markup=reply_markup)
    return PROFILE

def profile_callback(update: Update, context: CallbackContext) -> int:
    """Handler untuk callback pilihan profile"""
    query = update.callback_query
    query.answer()
    
    profile = query.data.replace('profile_', '')
    context.user_data['profile'] = profile
    logger.info(f"User memilih profile: {profile}")
    
    # Jika user adalah reseller, cek saldo
    if context.user_data.get('is_reseller'):
        config = load_config()
        profile_settings = get_profile_settings(profile, config)
        price = profile_settings['price']
        
        if price > context.user_data['reseller_data']['balance']:
            query.edit_message_text(
                f"❌ Saldo tidak mencukupi!\n"
                f"Harga voucher: Rp {price:,}\n"
                f"Saldo Anda: Rp {context.user_data['reseller_data']['balance']:,}"
            )
            return ConversationHandler.END
        
        context.user_data['voucher_price'] = price
        context.user_data['profile_settings'] = profile_settings
    
    keyboard = [
        [InlineKeyboardButton("Random", callback_data='username_random')],
        [InlineKeyboardButton("Custom", callback_data='username_custom')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(text=f"Profile: {profile}\nPilih tipe username:", reply_markup=reply_markup)
    return USERNAME_TYPE

def username_type_callback(update: Update, context: CallbackContext) -> int:
    """Handler untuk callback tipe username"""
    query = update.callback_query
    query.answer()
    
    username_type = query.data.replace('username_', '')
    context.user_data['username_type'] = username_type
    logger.info(f"User memilih tipe username: {username_type}")
    
    if username_type == 'random':
        # Generate random username
        username = generate_random_string(8)
        context.user_data['username'] = username
        logger.info(f"Generated random username: {username}")
        
        # Langsung ke pilihan password
        keyboard = [
            [InlineKeyboardButton("Random", callback_data='password_random')],
            [InlineKeyboardButton("Sama dengan username", callback_data='password_same')],
            [InlineKeyboardButton("Custom", callback_data='password_custom')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            text=f"Profile: {context.user_data['profile']}\nUsername: {username}\nPilih tipe password:",
            reply_markup=reply_markup
        )
        return PASSWORD
    else:
        query.edit_message_text(text="Masukkan username yang diinginkan:")
        return USERNAME

def username_input(update: Update, context: CallbackContext) -> int:
    """Handler untuk input username custom"""
    username = update.message.text
    context.user_data['username'] = username
    logger.info(f"User memasukkan username custom: {username}")
    
    keyboard = [
        [InlineKeyboardButton("Random", callback_data='password_random')],
        [InlineKeyboardButton("Sama dengan username", callback_data='password_same')],
        [InlineKeyboardButton("Custom", callback_data='password_custom')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"Profile: {context.user_data['profile']}\nUsername: {username}\nPilih tipe password:",
        reply_markup=reply_markup
    )
    return PASSWORD

def password_callback(update: Update, context: CallbackContext) -> int:
    """Handler untuk callback tipe password"""
    query = update.callback_query
    query.answer()
    
    password_type = query.data.replace('password_', '')
    logger.info(f"User memilih tipe password: {password_type}")
    
    if password_type == 'random':
        # Generate random password
        password = generate_random_string(8)
        context.user_data['password'] = password
        logger.info(f"Generated random password: {password}")
        
        # Langsung buat voucher
        return create_voucher_with_timestamp(update, context)
    elif password_type == 'same':
        # Gunakan username sebagai password
        password = context.user_data['username']
        context.user_data['password'] = password
        logger.info(f"Menggunakan username sebagai password: {password}")
        
        # Langsung buat voucher
        return create_voucher_with_timestamp(update, context)
    else:
        # Custom password
        query.edit_message_text(text="Masukkan password yang diinginkan:")
        return PASSWORD

def password_input(update: Update, context: CallbackContext) -> int:
    """Handler untuk input password custom"""
    password = update.message.text
    context.user_data['password'] = password
    logger.info(f"User memasukkan password custom")
    
    # Langsung buat voucher
    return create_voucher_with_timestamp(update, context)

def generate_voucher_image(voucher_data):
    """Fungsi untuk generate gambar voucher dengan QR code"""
    try:
        # Data untuk QR code
        qr_data = f"Username: {voucher_data['username']}\nPassword: {voucher_data['password']}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Buat gambar QR code
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Buat gambar voucher
        width, height = 600, 400
        image = Image.new('RGB', (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        
        # Coba load font, jika gagal gunakan default
        try:
            title_font = ImageFont.truetype("arial.ttf", 24)
            normal_font = ImageFont.truetype("arial.ttf", 18)
        except:
            # Jika font tidak tersedia, gunakan default
            title_font = ImageFont.load_default()
            normal_font = ImageFont.load_default()
            
        # Tambahkan judul
        draw.text((width//2, 30), "VOUCHER HOTSPOT", fill=(0, 0, 0), font=title_font, anchor="mm")
        
        # Tambahkan informasi voucher
        y_position = 80
        draw.text((20, y_position), f"Profile: {voucher_data['profile']}", fill=(0, 0, 0), font=normal_font)
        y_position += 30
        draw.text((20, y_position), f"Username: {voucher_data['username']}", fill=(0, 0, 0), font=normal_font)
        y_position += 30
        draw.text((20, y_position), f"Password: {voucher_data['password']}", fill=(0, 0, 0), font=normal_font)
        y_position += 30
        
        # Tambahkan durasi jika ada
        if voucher_data.get('duration'):
            draw.text((20, y_position), f"Durasi: {voucher_data['duration']}", fill=(0, 0, 0), font=normal_font)
            y_position += 30
            
        # Tambahkan kuota jika ada
        if voucher_data.get('quota'):
            draw.text((20, y_position), f"Kuota: {voucher_data['quota']}", fill=(0, 0, 0), font=normal_font)
            y_position += 30
        
        # Tambahkan timestamp
        draw.text((20, y_position), voucher_data.get('comment', ''), fill=(0, 0, 0), font=normal_font)
        
        # Tempel QR code ke gambar utama
        qr_img_resized = qr_img.resize((150, 150))
        image.paste(qr_img_resized, (width - 180, height - 180))
        
        # Konversi ke BytesIO untuk dikirim via Telegram
        bio = io.BytesIO()
        bio.name = 'voucher.png'
        image.save(bio, 'PNG')
        bio.seek(0)
        
        return bio
    except Exception as e:
        logger.error(f"Error generating voucher image: {e}")
        return None

def send_admin_notification(context, message):
    """Kirim notifikasi ke admin Telegram"""
    try:
        config = load_config()
        admin_chat_id = config.get('TELEGRAM_CHAT_ID')
        if not admin_chat_id:
            logger.error("Admin chat ID tidak ditemukan")
            return False
            
        context.bot.send_message(
            chat_id=admin_chat_id,
            text=message
        )
        logger.info(f"Notifikasi berhasil dikirim ke admin")
        return True
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke admin: {e}")
        return False

def create_voucher_with_timestamp(update: Update, context: CallbackContext) -> int:
    """Fungsi untuk membuat voucher dengan timestamp sebagai komentar"""
    # Generate timestamp untuk komentar
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context.user_data['comment'] = f"Dibuat: {timestamp}"
    
    update.effective_message.reply_text("🔄 Membuat voucher...")
    
    # Buat voucher
    result = create_voucher(context.user_data)
    
    if result[0]:
        # Jika user adalah reseller dan voucher berhasil dibuat, kurangi saldo
        if context.user_data.get('is_reseller'):
            config = load_config()
            price = context.user_data.get('voucher_price', 0)
            chat_id = update.effective_chat.id
            reseller_name = context.user_data.get('reseller_data', {}).get('name', 'Unknown')
            
            # Log info saldo sebelum dikurangi
            for reseller in config.get('RESELLERS', []):
                if str(reseller['chat_id']) == str(chat_id):
                    logger.info(f"Saldo reseller sebelum: Rp {reseller['balance']}")
            
            if update_reseller_balance(chat_id, price, config):
                # Ambil saldo terbaru
                _, updated_reseller = is_reseller(chat_id, load_config())
                if updated_reseller:
                    balance = updated_reseller['balance']
                    logger.info(f"Saldo reseller setelah: Rp {balance}")
                else:
                    balance = "tidak diketahui"
                    logger.error("Gagal mendapatkan saldo terbaru")
                
                profile_settings = get_profile_settings(context.user_data['profile'], config)
                
                # Buat informasi voucher untuk ditampilkan
                voucher_info = {
                    'profile': context.user_data['profile'],
                    'username': context.user_data['username'],
                    'password': context.user_data['password'],
                    'duration': profile_settings['duration'] if profile_settings['duration'] else None,
                    'quota': profile_settings['quota'] if profile_settings['quota'] else None,
                    'comment': context.user_data['comment']
                }
                
                # Kirim notifikasi ke admin
                admin_message = (
                    f"ℹ️ Voucher baru dibuat oleh reseller!\n\n"
                    f"Reseller: {reseller_name} ({chat_id})\n"
                    f"Profile: {voucher_info['profile']}\n"
                    f"Username: {voucher_info['username']}\n"
                    f"Password: {voucher_info['password']}\n"
                    f"Harga: Rp {price:,}\n"
                    f"Saldo reseller: Rp {balance:,}"
                )
                send_admin_notification(context, admin_message)
                
                # Generate voucher image
                voucher_image = generate_voucher_image(voucher_info)
                
                # Kirim gambar voucher
                if voucher_image:
                    update.effective_message.reply_photo(
                        photo=voucher_image,
                        caption=f"✅ Voucher berhasil dibuat!\n\n"
                                f"Profile: {voucher_info['profile']}\n"
                                f"Username: {voucher_info['username']}\n"
                                f"Password: {voucher_info['password']}\n"
                                f"Durasi: {voucher_info['duration'] if voucher_info['duration'] else 'Tidak ada'}\n"
                                f"Kuota: {voucher_info['quota'] if voucher_info['quota'] else 'Tidak ada'}\n"
                                f"📅 {voucher_info['comment']}\n\n"
                                f"💰 Saldo berkurang: Rp {price:,}\n"
                                f"💳 Sisa saldo: Rp {balance:,}"
                    )
                else:
                    # Jika gagal generate gambar, kirim pesan text
                    update.effective_message.reply_text(
                        f"✅ Voucher berhasil dibuat!\n\n"
                        f"Profile: {voucher_info['profile']}\n"
                        f"Username: {voucher_info['username']}\n"
                        f"Password: {voucher_info['password']}\n"
                        f"Durasi: {voucher_info['duration'] if voucher_info['duration'] else 'Tidak ada'}\n"
                        f"Kuota: {voucher_info['quota'] if voucher_info['quota'] else 'Tidak ada'}\n"
                        f"📅 {voucher_info['comment']}\n\n"
                        f"💰 Saldo berkurang: Rp {price:,}\n"
                        f"💳 Sisa saldo: Rp {balance:,}"
                    )
            else:
                update.effective_message.reply_text("⚠️ Voucher berhasil dibuat tetapi gagal memperbarui saldo!")
        else:
            # Pesan normal untuk admin
            config = load_config()
            profile_settings = get_profile_settings(context.user_data['profile'], config)
            
            # Buat informasi voucher untuk ditampilkan
            voucher_info = {
                'profile': context.user_data['profile'],
                'username': context.user_data['username'],
                'password': context.user_data['password'],
                'duration': profile_settings['duration'] if profile_settings['duration'] else None,
                'quota': profile_settings['quota'] if profile_settings['quota'] else None,
                'comment': context.user_data['comment']
            }
            
            # Generate voucher image
            voucher_image = generate_voucher_image(voucher_info)
            
            # Kirim gambar voucher
            if voucher_image:
                update.effective_message.reply_photo(
                    photo=voucher_image,
                    caption=f"✅ Voucher berhasil dibuat!\n\n"
                            f"Profile: {voucher_info['profile']}\n"
                            f"Username: {voucher_info['username']}\n"
                            f"Password: {voucher_info['password']}\n"
                            f"Durasi: {voucher_info['duration'] if voucher_info['duration'] else 'Tidak ada'}\n"
                            f"Kuota: {voucher_info['quota'] if voucher_info['quota'] else 'Tidak ada'}\n"
                            f"📅 {voucher_info['comment']}"
                )
            else:
                # Jika gagal generate gambar, kirim pesan text
                update.effective_message.reply_text(
                    f"✅ Voucher berhasil dibuat!\n\n"
                    f"Profile: {voucher_info['profile']}\n"
                    f"Username: {voucher_info['username']}\n"
                    f"Password: {voucher_info['password']}\n"
                    f"Durasi: {voucher_info['duration'] if voucher_info['duration'] else 'Tidak ada'}\n"
                    f"Kuota: {voucher_info['quota'] if voucher_info['quota'] else 'Tidak ada'}\n"
                    f"📅 {voucher_info['comment']}"
                )
    else:
        # Gagal
        update.effective_message.reply_text(f"❌ Gagal membuat voucher: {result[1]}")
    
    return ConversationHandler.END

def create_voucher(user_data):
    """Fungsi untuk membuat voucher di Mikrotik Hotspot"""
    config = load_config()
    if not config:
        return False, "Konfigurasi tidak ditemukan"
    
    logger.info(f"Membuat voucher untuk username: {user_data['username']}")
    
    try:
        api = connect_to_mikrotik(config)
        if not api:
            return False, "Tidak dapat terhubung ke Mikrotik. Periksa konfigurasi dan pastikan API aktif."
        
        # Ambil pengaturan profil dari konfigurasi
        profile_settings = get_profile_settings(user_data['profile'], config)
        
        params = {
            'name': user_data['username'],
            'password': user_data['password'],
            'profile': user_data['profile'],
        }
        
        # Gunakan durasi dari konfigurasi profil
        if profile_settings['duration']:
            params['limit-uptime'] = profile_settings['duration']
        
        # Tambahkan kuota jika ada
        if profile_settings['quota'] and profile_settings['quota'].lower() != 'none':
            params['limit-bytes-total'] = convert_quota_to_bytes(profile_settings['quota'])
        
        if user_data.get('comment'):
            params['comment'] = user_data['comment']
        
        # Tambahkan user hotspot baru
        api.path('ip/hotspot/user').add(**params)
        
        api.close()
        logger.info(f"Voucher berhasil dibuat untuk username: {user_data['username']}")
        return True, "Voucher berhasil dibuat"
    except librouteros.exceptions.ConnectionClosed as e:
        logger.error(f"Error koneksi saat membuat voucher: {e}")
        return False, f"Error koneksi: {str(e)}"
    except Exception as e:
        logger.error(f"Error creating voucher: {e}")
        return False, str(e)

def convert_quota_to_bytes(quota_str):
    """Konversi string kuota ke bytes"""
    quota_str = quota_str.upper()
    multipliers = {
        'K': 1024,
        'M': 1024 * 1024,
        'G': 1024 * 1024 * 1024
    }
    
    number = float(''.join(filter(lambda x: x.isdigit() or x == '.', quota_str)))
    unit = ''.join(filter(lambda x: x.isalpha(), quota_str))
    
    if unit in multipliers:
        return int(number * multipliers[unit])
    return int(number)

def list_vouchers(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /list"""
    config = load_config()
    if not config:
        update.message.reply_text('❌ Konfigurasi tidak ditemukan. Silakan atur melalui web interface.')
        return
    
    user = update.effective_user
    logger.info(f"User {user.id} meminta daftar voucher")
    
    update.message.reply_text('🔄 Mengambil daftar voucher...')
    
    api = connect_to_mikrotik(config)
    if not api:
        update.message.reply_text('❌ Gagal terhubung ke Mikrotik. Periksa konfigurasi dan pastikan API aktif.')
        return
    
    try:
        users = api.path('ip/hotspot/user')
        user_list = list(users)
        api.close()
        
        if not user_list:
            update.message.reply_text('ℹ️ Tidak ada user hotspot yang ditemukan.')
            return
        
        # Batasi daftar ke 10 user terakhir
        last_users = user_list[-10:] if len(user_list) > 10 else user_list
        
        message = "📋 Daftar 10 User Hotspot Terakhir:\n\n"
        for user in last_users:
            message += f"👤 Username: {user.get('name', 'N/A')}\n"
            message += f"🔑 Profile: {user.get('profile', 'N/A')}\n"
            message += f"⏱️ Limit: {user.get('limit-uptime', 'Tidak ada')}\n"
            message += f"📝 Komentar: {user.get('comment', 'Tidak ada')}\n"
            message += "----------------------\n"
        
        update.message.reply_text(message)
        logger.info(f"Berhasil menampilkan {len(last_users)} voucher")
    except Exception as e:
        logger.error(f"Error saat mengambil daftar user: {e}")
        update.message.reply_text(f'❌ Gagal mendapatkan daftar user: {str(e)}')

def active_users(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /active"""
    config = load_config()
    if not config:
        update.message.reply_text('❌ Konfigurasi tidak ditemukan. Silakan atur melalui web interface.')
        return
    
    user = update.effective_user
    logger.info(f"User {user.id} meminta daftar user aktif")
    
    update.message.reply_text('🔄 Mengambil daftar user aktif...')
    
    api = connect_to_mikrotik(config)
    if not api:
        update.message.reply_text('❌ Gagal terhubung ke Mikrotik. Periksa konfigurasi dan pastikan API aktif.')
        return
    
    try:
        active = api.path('ip/hotspot/active')
        active_list = list(active)
        api.close()
        
        if not active_list:
            update.message.reply_text('ℹ️ Tidak ada user hotspot yang sedang aktif.')
            return
        
        message = f"📋 Daftar User Hotspot Aktif ({len(active_list)} user):\n\n"
        for user in active_list:
            message += f"👤 Username: {user.get('user', 'N/A')}\n"
            message += f"🖥️ IP Address: {user.get('address', 'N/A')}\n"
            message += f"⏱️ Uptime: {user.get('uptime', 'N/A')}\n"
            
            # Format penggunaan data
            bytes_in = int(user.get('bytes-in', '0'))
            bytes_out = int(user.get('bytes-out', '0'))
            download = format_bytes(bytes_in)
            upload = format_bytes(bytes_out)
            
            message += f"📥 Download: {download}\n"
            message += f"📤 Upload: {upload}\n"
            message += "----------------------\n"
        
        update.message.reply_text(message)
        logger.info(f"Berhasil menampilkan {len(active_list)} user aktif")
    except Exception as e:
        logger.error(f"Error saat mengambil daftar user aktif: {e}")
        update.message.reply_text(f'❌ Gagal mendapatkan daftar user aktif: {str(e)}')

def admin_check_reseller(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /checkreseller untuk admin"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info(f"User {user.id} mencoba akses perintah admin checkreseller")
    
    # Cek apakah user adalah admin
    config = load_config()
    admin_chat_id = config.get('TELEGRAM_CHAT_ID')
    
    if str(chat_id) != str(admin_chat_id):
        update.message.reply_text("❌ Anda tidak memiliki izin untuk mengakses perintah ini.")
        return
    
    # Jika tidak ada argumen, tampilkan cara penggunaan
    if not context.args:
        update.message.reply_text(
            "ℹ️ Cara penggunaan:\n"
            "/checkreseller <chat_id> - Untuk memeriksa saldo reseller\n"
            "/checkreseller all - Untuk melihat semua reseller"
        )
        return
    
    # Ambil data reseller
    resellers = config.get('RESELLERS', [])
    if not resellers:
        update.message.reply_text("ℹ️ Tidak ada reseller yang terdaftar.")
        return
    
    # Jika argumen adalah 'all', tampilkan semua reseller
    if context.args[0].lower() == 'all':
        message = "📋 Daftar Semua Reseller:\n\n"
        for i, reseller in enumerate(resellers, 1):
            message += f"{i}. Nama: {reseller.get('name', 'N/A')}\n"
            message += f"   Chat ID: {reseller.get('chat_id', 'N/A')}\n"
            message += f"   Saldo: Rp {reseller.get('balance', 0):,}\n"
            message += f"   Status: {'Aktif' if reseller.get('status') == 'active' else 'Nonaktif'}\n\n"
        
        update.message.reply_text(message)
        return
    
    # Cari reseller berdasarkan chat_id
    target_chat_id = context.args[0]
    for reseller in resellers:
        if str(reseller.get('chat_id', '')) == str(target_chat_id):
            message = f"💰 Informasi Reseller:\n\n"
            message += f"Nama: {reseller.get('name', 'N/A')}\n"
            message += f"Chat ID: {reseller.get('chat_id', 'N/A')}\n"
            message += f"Saldo: Rp {reseller.get('balance', 0):,}\n"
            message += f"Status: {'Aktif' if reseller.get('status') == 'active' else 'Nonaktif'}"
            
            update.message.reply_text(message)
            return
    
    # Jika reseller tidak ditemukan
    update.message.reply_text(f"❌ Reseller dengan chat ID {target_chat_id} tidak ditemukan.")

def admin_add_balance(update: Update, context: CallbackContext) -> None:
    """Handler untuk command /addsaldo untuk admin"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info(f"User {user.id} mencoba akses perintah admin addsaldo")
    
    # Cek apakah user adalah admin
    config = load_config()
    admin_chat_id = config.get('TELEGRAM_CHAT_ID')
    
    if str(chat_id) != str(admin_chat_id):
        update.message.reply_text("❌ Anda tidak memiliki izin untuk mengakses perintah ini.")
        return
    
    # Jika argumen tidak lengkap, tampilkan cara penggunaan
    if len(context.args) < 2:
        update.message.reply_text(
            "ℹ️ Cara penggunaan:\n"
            "/addsaldo <chat_id> <jumlah> - Untuk menambah saldo reseller\n\n"
            "Contoh: /addsaldo 123456789 50000"
        )
        return
    
    try:
        # Parse argumen
        target_chat_id = context.args[0]
        amount = int(context.args[1])
        
        if amount <= 0:
            update.message.reply_text("❌ Jumlah saldo harus lebih dari 0.")
            return
        
        # Ambil data reseller
        resellers = config.get('RESELLERS', [])
        if not resellers:
            update.message.reply_text("ℹ️ Tidak ada reseller yang terdaftar.")
            return
        
        # Cari dan update reseller
        reseller_found = False
        for reseller in resellers:
            if str(reseller.get('chat_id', '')) == str(target_chat_id):
                # Simpan data awal untuk log
                old_balance = reseller.get('balance', 0)
                # Tambah saldo
                reseller['balance'] = old_balance + amount
                reseller_found = True
                
                # Simpan perubahan ke file
                with open('config.json', 'w') as f:
                    json.dump(config, f)
                
                # Kirim pesan ke admin
                update.message.reply_text(
                    f"✅ Berhasil menambah saldo reseller!\n\n"
                    f"Nama: {reseller.get('name', 'N/A')}\n"
                    f"Chat ID: {target_chat_id}\n"
                    f"Saldo lama: Rp {old_balance:,}\n"
                    f"Saldo baru: Rp {reseller['balance']:,}\n"
                    f"Ditambahkan: Rp {amount:,}"
                )
                
                # Kirim notifikasi ke reseller
                try:
                    context.bot.send_message(
                        chat_id=target_chat_id,
                        text=f"💰 Saldo Anda telah ditambahkan!\n\n"
                             f"Saldo lama: Rp {old_balance:,}\n"
                             f"Saldo baru: Rp {reseller['balance']:,}\n"
                             f"Ditambahkan: Rp {amount:,}"
                    )
                    logger.info(f"Notifikasi penambahan saldo berhasil dikirim ke reseller {reseller['name']}")
                except Exception as e:
                    logger.error(f"Gagal mengirim notifikasi ke reseller: {e}")
                    update.message.reply_text(
                        "⚠️ Saldo berhasil ditambahkan, tetapi gagal mengirim notifikasi ke reseller."
                    )
                
                break
        
        if not reseller_found:
            update.message.reply_text(f"❌ Reseller dengan chat ID {target_chat_id} tidak ditemukan.")
    
    except ValueError:
        update.message.reply_text("❌ Jumlah saldo harus berupa angka.")
    except Exception as e:
        logger.error(f"Error saat menambah saldo: {e}")
        update.message.reply_text(f"❌ Terjadi kesalahan: {str(e)}")

def main():
    """Fungsi utama untuk menjalankan bot"""
    # Periksa file konfigurasi
    config = load_config()
    if not config:
        logger.error("Config file tidak ditemukan. Buat konfigurasi melalui web interface terlebih dahulu.")
        print("ERROR: Config file tidak ditemukan. Buat konfigurasi melalui web interface terlebih dahulu.")
        return
    
    # Periksa token Telegram
    token = config.get('TELEGRAM_TOKEN')
    if not token:
        logger.error("Token Telegram tidak ditemukan di konfigurasi")
        print("ERROR: Token Telegram tidak ditemukan di konfigurasi")
        return
    
    try:
        logger.info(f"Memulai bot dengan token: {token[:5]}...{token[-5:]}")
        updater = Updater(token)
        dispatcher = updater.dispatcher
        
        # Menambahkan handlers
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("list", list_vouchers))
        dispatcher.add_handler(CommandHandler("status", status))
        dispatcher.add_handler(CommandHandler("active", active_users))
        dispatcher.add_handler(CommandHandler("saldo", check_balance))
        
        # Handlers untuk admin
        dispatcher.add_handler(CommandHandler("checkreseller", admin_check_reseller))
        dispatcher.add_handler(CommandHandler("addsaldo", admin_add_balance))
        
        # Conversation handler untuk pembuatan voucher
        voucher_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('voucher', voucher)],
            states={
                PROFILE: [CallbackQueryHandler(profile_callback, pattern='^profile_')],
                USERNAME_TYPE: [CallbackQueryHandler(username_type_callback, pattern='^username_')],
                USERNAME: [MessageHandler(Filters.text & ~Filters.command, username_input)],
                PASSWORD: [
                    CallbackQueryHandler(password_callback, pattern='^password_'),
                    MessageHandler(Filters.text & ~Filters.command, password_input)
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        dispatcher.add_handler(voucher_conv_handler)
        
        # Conversation handler untuk detail voucher
        detail_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('detail', detail_start)],
            states={
                DETAIL_USERNAME: [MessageHandler(Filters.text & ~Filters.command, detail_get_username)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        dispatcher.add_handler(detail_conv_handler)
        
        # Memulai polling
        logger.info("Bot started polling")
        print("Bot Telegram sudah berjalan!")
        updater.start_polling()
        updater.idle()
    except telegram.error.InvalidToken:
        logger.error("Token Telegram tidak valid")
        print("ERROR: Token Telegram tidak valid")
    except telegram.error.Unauthorized:
        logger.error("Token Telegram tidak sah atau sudah dicabut")
        print("ERROR: Token Telegram tidak sah atau sudah dicabut")
    except Exception as e:
        logger.error(f"Error saat menjalankan bot: {e}")
        print(f"ERROR: Terjadi kesalahan saat menjalankan bot: {e}")

if __name__ == '__main__':
    # Pastikan folder log ada
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'telegram_bot.log')
    if not os.path.exists(log_file):
        open(log_file, 'w').close()
        print(f"Membuat file log: {log_file}")
    
    main() 