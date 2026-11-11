import os
import subprocess
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- कॉन्फ़िगरेशन (Rolex सर की डिटेल्स) ---
TOKEN = "9082673454:AAFW-CL_qPZ3ZB-ntPDKhJRJuN-M5HDjsPI"
ADMIN_ID = 7985785104  # आपकी Admin / Chat ID
CHANNEL_LINK = "https://t.me/venomus_9"
BASE_DIR = "/home/ubuntu/hosted_bots"
BASE_URL = "https://yourdomain.com/venomus"  # लिंक में 'venomus' नाम जोड़ दिया गया है

bot = telebot.TeleBot(TOKEN)
os.makedirs(BASE_DIR, exist_ok=True)

pending_approvals = {}  # {request_id: {data}}
user_activity = {}      # {chat_id: {"username": ..., "uploads": count, "files": []}}
active_hosts = {}       # {hosting_name: {chat_id, file_path, type}}

# 1. सुरक्षा जाँच (Malicious Code Detection)
def security_scan(file_path, file_ext):
    if file_ext != '.py':
        return True, "Safe"
    
    dangerous_keywords = [
        "shutil.rmtree", "os.remove", "os.system('rm", "subprocess.call('rm", 
        "eval(", "exec(", "bot.delete_message", "requests.get('http://malicious"
    ]
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            for keyword in dangerous_keywords:
                if keyword in content:
                    return False, f"⚠️ सुरक्षा चेतावनी: कोड में खतरनाक कमांड मिली ({keyword})!"
    except Exception as e:
        return False, f"फाइल रीड करने में त्रुटि: {str(e)}"
        
    return True, "Safe"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id not in user_activity:
        user_activity[chat_id] = {
            "name": message.from_user.first_name, 
            "username": message.from_user.username or "No Username",
            "uploads": 0, 
            "files": []
        }
    
    welcome_text = (
        f"नमस्ते Rolex सर के ऑफिशियल होस्टिंग बोट में आपका स्वागत है! 🚀\n\n"
        f"यहाँ आप अपनी Python, HTML, JS या requirements.txt फाइल भेज सकते हैं।\n"
        f"📌 हमारे चैनल से जुड़े रहें: {CHANNEL_LINK}\n\n"
        f"*नोट:* सभी फाइलें ओनर (Rolex सर / venomus) द्वारा अप्रूव होने के बाद ही लाइव या रन होंगी।"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# 2. एडमिन पैनल कमांड
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ यह कमांड केवल ओनर (Rolex सर) के लिए है!")
        return
        
    total_users = len(user_activity)
    total_hosts = len(active_hosts)
    
    report = f"👑 **Admin Dashboard (venomus / Rolex Sir)** 👑\n\n"
    report += f"👥 कुल एक्टिव यूजर्स: `{total_users}`\n"
    report += f"🚀 कुल रनिंग होस्टिंग्स: `{total_hosts}`\n\n"
    report += "📋 **यूजर्स की गतिविधि:**\n"
    
    for uid, info in user_activity.items():
        report += f"• ID: `{uid}` | Name: {info['name']} (@{info['username']}) | Uploads: {info['uploads']}\n"
        
    bot.reply_to(message, report, parse_mode="Markdown")

# 3. फाइल हैंडलिंग
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    chat_id = message.chat.id
    
    if chat_id not in user_activity:
        user_activity[chat_id] = {
            "name": message.from_user.first_name, 
            "username": message.from_user.username or "No Username",
            "uploads": 0, 
            "files": []
        }
        
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    file_name = message.document.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    temp_path = os.path.join(BASE_DIR, f"temp_{chat_id}_{file_name}")
    with open(temp_path, 'wb') as new_file:
        new_file.write(downloaded_file)
        
    # सिक्योरिटी स्कैन
    is_safe, msg = security_scan(temp_path, file_ext)
    if not is_safe:
        os.remove(temp_path)
        bot.reply_to(message, f"❌ **फाइल ऑटोमैटिकली रिजेक्ट हो गई!**\n{msg}")
        return
        
    bot.reply_to(message, f"✅ फाइल मिल गई (`{file_name}`).\nअब कृपया इस प्रोजेक्ट के लिए एक **यूनिक नाम (Hosting Name)** दर्ज करें:")
    bot.register_next_step_handler(message, ask_project_name, temp_path, file_name, file_ext)

def ask_project_name(message, temp_path, file_name, file_ext):
    chat_id = message.chat.id
    hosting_name = message.text.strip().replace(" ", "_")
    
    project_dir = os.path.join(BASE_DIR, hosting_name)
    if os.path.exists(project_dir):
        bot.reply_to(message, "⚠️ इस नाम से पहले ही फोल्डर मौजूद है। कृपया दूसरा नाम भेजें:")
        bot.register_next_step_handler(message, ask_project_name, temp_path, file_name, file_ext)
        return
        
    os.makedirs(project_dir, exist_ok=True)
    final_path = os.path.join(project_dir, file_name)
    os.rename(temp_path, final_path)
    
    req_id = f"{chat_id}_{hosting_name}"
    pending_approvals[req_id] = {
        "chat_id": chat_id,
        "hosting_name": hosting_name,
        "file_path": final_path,
        "file_name": file_name,
        "file_ext": file_ext,
        "project_dir": project_dir
    }
    
    bot.reply_to(message, "⏳ आपकी फाइल ओनर (Rolex सर / venomus) के पास अप्रूवल के लिए भेज दी गई है। अप्रूव होते ही यह लाइव/रन हो जाएगी!")
    
    # एडमिन को अप्रूवल नोटिफिकेशन भेजें
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{req_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{req_id}")
    )
    
    admin_msg = (
        f"🔔 **नई होस्टिंग रिक्वेस्ट आई है!**\n\n"
        f"👤 यूजर ID: `{chat_id}`\n"
        f"👤 नाम: {message.from_user.first_name} (@{message.from_user.username})\n"
        f"🏷️ प्रोजेक्ट नाम: `{hosting_name}`\n"
        f"📁 फाइल नाम: `{file_name}`\n"
        f"⚙️ टाइप: `{file_ext}`"
    )
    bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup, parse_mode="Markdown")

# 4. एडमिन अप्रूवल कॉलबैक हैंडलर
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('reject_'))
def handle_approval(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "यह बटन सिर्फ ओनर के लिए है!", show_alert=True)
        return
        
    action, req_id = call.data.split('_', 1)
    
    if req_id not in pending_approvals:
        bot.answer_callback_query(call.id, "यह रिक्वेस्ट पहले ही प्रोसेस हो चुकी है या एक्सपायर हो गई है।")
        return
        
    data = pending_approvals[req_id]
    chat_id = data["chat_id"]
    hosting_name = data["hosting_name"]
    final_path = data["file_path"]
    file_ext = data["file_ext"]
    project_dir = data["project_dir"]
    
    if action == 'approve':
        user_activity[chat_id]["uploads"] += 1
        user_activity[chat_id]["files"].append(hosting_name)
        
        # अगर Python फाइल है
        if file_ext == '.py':
            try:
                req_txt = os.path.join(project_dir, "requirements.txt")
                if os.path.exists(req_txt):
                    subprocess.run(f"pip install -r {req_txt}", shell=True, check=True)
                    
                pm2_cmd = f"pm2 start {final_path} --name {hosting_name}"
                subprocess.run(pm2_cmd, shell=True, check=True)
                
                active_hosts[hosting_name] = {"chat_id": chat_id, "type": "Python Bot"}
                bot.send_message(chat_id, f"🎉 **बधाई हो!**\nRolex सर (venomus) ने आपके पायथन बोट (`{hosting_name}`) को **अप्रूव** कर दिया है और यह बैकग्राउंड में रन हो रहा है! 🚀\n📌 चैनल: {CHANNEL_LINK}")
            except Exception as e:
                bot.send_message(chat_id, f"❌ बोट रन करने में एरर आया: {str(e)}")
                
        # अगर HTML या वेब फाइल है (लिंक में venomus नाम के साथ)
        elif file_ext in ['.html', '.htm', '.js', '.css']:
            live_link = f"{BASE_URL}/{hosting_name}/{data['file_name']}"
            active_hosts[hosting_name] = {"chat_id": chat_id, "type": "Web Page"}
            bot.send_message(chat_id, f"🌐 **बधाई हो!**\nRolex सर (venomus) ने आपकी वेब फाइल (`{hosting_name}`) अप्रूव कर दी है!\n\n🔗 **लाइव लिंक (venomus):**\n{live_link}\n\n📌 चैनल: {CHANNEL_LINK}")
            
        bot.edit_message_text(f"✅ **Approved by venomus / Rolex Sir**\nProject: `{hosting_name}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    else: # Reject
        import shutil
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
            
        bot.send_message(chat_id, f"❌ क्षमा करें, Rolex सर (venomus) ने आपके प्रोजेक्ट (`{hosting_name}`) को **रिजेक्ट** कर दिया है।")
        bot.edit_message_text(f"❌ **Rejected by venomus / Rolex Sir**\nProject: `{hosting_name}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
    del pending_approvals[req_id]

bot.infinity_polling()
