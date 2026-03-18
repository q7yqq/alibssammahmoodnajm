import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# -------------------- الإعدادات --------------------
TOKEN = "8231332192:AAEyJ-HbMROSl6mO_ypG4fdIxAKwsv2bTds"
ADMIN_ID = 7863628255
CHANNEL_USERNAME = "@DD86DD"
MAX_DAILY_ADS = 10
DATA_FILE = "bot_data.json"  # لتخزين الإحصائيات بشكل دائم

# حالات المحادثة
PHOTO, DETAILS = range(2)

# تهيئة التسجيل (logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------- هيكل بيانات الإحصائيات --------------------
class Stats:
    def __init__(self):
        self.total_ads = 0
        self.deleted_ads = 0
        self.unique_users = set()
        self.daily_ads = 0
        self.last_reset_day = datetime.now().date().isoformat()

    def to_dict(self):
        return {
            "total_ads": self.total_ads,
            "deleted_ads": self.deleted_ads,
            "unique_users": list(self.unique_users),
            "daily_ads": self.daily_ads,
            "last_reset_day": self.last_reset_day,
        }

    @classmethod
    def from_dict(cls, data):
        stats = cls()
        stats.total_ads = data.get("total_ads", 0)
        stats.deleted_ads = data.get("deleted_ads", 0)
        stats.unique_users = set(data.get("unique_users", []))
        stats.daily_ads = data.get("daily_ads", 0)
        stats.last_reset_day = data.get("last_reset_day", datetime.now().date().isoformat())
        return stats

# -------------------- دوال تخزين واسترجاع الإحصائيات --------------------
def load_stats() -> Stats:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Stats.from_dict(data)
        except Exception as e:
            logger.error(f"خطأ في تحميل الإحصائيات: {e}")
            return Stats()
    return Stats()

def save_stats(stats: Stats):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ الإحصائيات: {e}")

def reset_daily_if_needed(stats: Stats):
    today = datetime.now().date().isoformat()
    if stats.last_reset_day != today:
        stats.daily_ads = 0
        stats.last_reset_day = today
        save_stats(stats)

# -------------------- بداية المحادثة --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id

    stats = load_stats()
    reset_daily_if_needed(stats)

    if user_id not in stats.unique_users:
        stats.unique_users.add(user_id)
        save_stats(stats)

    if stats.daily_ads >= MAX_DAILY_ADS:
        await update.message.reply_text(
            f"عذراً، لقد وصلنا اليوم إلى الحد الأقصى من الإعلانات ({MAX_DAILY_ADS}).\n"
            "يرجى المحاولة غداً."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "مرحباً! لنبدأ عملية الإعلان.\n"
        "الرجاء إرسال الصور (صورة واحدة أو مجموعة صور).\n"
        "بعد الانتهاء من إرسال الصور، اكتب كلمة (تم) للمتابعة."
    )

    context.user_data["photos"] = []
    context.user_data["temp_photos"] = []  # للمجموعات
    context.user_data["media_group_id"] = None
    return PHOTO

# -------------------- استقبال الصور --------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    message = update.message
    photos = message.photo

    if not photos:
        if message.text and message.text.strip().lower() == "تم":
            photos_list = context.user_data.get("photos", [])
            temp_photos = context.user_data.get("temp_photos", [])
            if photos_list or temp_photos:
                await update.message.reply_text(
                    "تم استلام الصور.\n"
                    "الآن أرسل مواصفات الحساب ووسيلة التواصل في رسالة واحدة."
                )
                return DETAILS
            else:
                await update.message.reply_text("لم ترسل أي صور بعد. أرسل الصور أولاً ثم اكتب (تم).")
                return PHOTO
        else:
            await update.message.reply_text("الرجاء إرسال صور صالحة أو اكتب (تم) للمتابعة.")
            return PHOTO

    best_photo = photos[-1]
    file_id = best_photo.file_id
    media_group_id = message.media_group_id

    if media_group_id:
        if context.user_data.get("media_group_id") != media_group_id:
            context.user_data["media_group_id"] = media_group_id
            context.user_data["temp_photos"] = [file_id]
        else:
            context.user_data["temp_photos"].append(file_id)
    else:
        context.user_data.setdefault("photos", []).append(file_id)
        await update.message.reply_text("تم استلام الصورة. يمكنك إرسال المزيد أو اكتب (تم) للمتابعة.")

    return PHOTO

# -------------------- استقبال التفاصيل --------------------
async def details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    details_text = update.message.text
    if not details_text:
        await update.message.reply_text("الرجاء إرسال النص المطلوب.")
        return DETAILS

    context.user_data["details"] = details_text

    stats = load_stats()
    reset_daily_if_needed(stats)
    if stats.daily_ads >= MAX_DAILY_ADS:
        await update.message.reply_text("للأسف، تم تجاوز الحد اليومي للإعلانات.")
        return ConversationHandler.END

    photos = context.user_data.get("photos", [])
    temp_photos = context.user_data.get("temp_photos", [])
    all_photos = photos + temp_photos

    if not all_photos:
        await update.message.reply_text("لم يتم استقبال أي صور. أعد المحاولة من /start")
        return ConversationHandler.END

    caption = (
        f"المواصفات: {details_text}\n"
        f"المزاد يبدأ (1$)\n"
        f"الرجاء بدون تكلم\n"
        f"اذكر نوع العمله\n"
        f"من بوت الاعلانات (@on1dwlarbot)"
    )

    try:
        if len(all_photos) == 1:
            sent_message = await context.bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=all_photos[0],
                caption=caption
            )
            message_id = sent_message.message_id
        else:
            media_group = []
            for i, file_id in enumerate(all_photos):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=file_id, caption=caption))
                else:
                    media_group.append(InputMediaPhoto(media=file_id))
            sent_messages = await context.bot.send_media_group(
                chat_id=CHANNEL_USERNAME,
                media=media_group
            )
            message_id = sent_messages[0].message_id
    except Exception as e:
        logger.error(f"فشل إرسال الإعلان إلى القناة: {e}")
        await update.message.reply_text("حدث خطأ أثناء النشر. الرجاء المحاولة لاحقاً.")
        return ConversationHandler.END

    stats.total_ads += 1
    stats.daily_ads += 1
    save_stats(stats)

    await update.message.reply_text(
        f"✅ تم نشر إعلانك بنجاح في القناة.\n"
        f"سيتم حذفه تلقائياً بعد 24 ساعة.\n"
        f"الإعلانات المتبقية اليوم: {MAX_DAILY_ADS - stats.daily_ads}"
    )

    context.job_queue.run_once(
        delete_ad_job,
        when=timedelta(hours=24),
        data={"chat_id": CHANNEL_USERNAME, "message_id": message_id},
        name=f"delete_{message_id}"
    )

    context.user_data.clear()
    return ConversationHandler.END

# -------------------- وظيفة الحذف المؤجلة --------------------
async def delete_ad_job(context: CallbackContext):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        stats = load_stats()
        stats.deleted_ads += 1
        save_stats(stats)
        logger.info(f"تم حذف الرسالة {message_id} من {chat_id}")
    except Exception as e:
        logger.error(f"فشل حذف الرسالة {message_id}: {e}")

# -------------------- لوحة الإحصائيات (للأدمن) --------------------
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("هذا الأمر مخصص للمشرف فقط.")
        return

    stats = load_stats()
    reset_daily_if_needed(stats)

    text = (
        f"📊 **إحصائيات البوت**\n"
        f"• إجمالي الإعلانات المنشورة: {stats.total_ads}\n"
        f"• الإعلانات المحذوفة: {stats.deleted_ads}\n"
        f"• عدد المستخدمين الفريدين: {len(stats.unique_users)}\n"
        f"• إعلانات اليوم: {stats.daily_ads} / {MAX_DAILY_ADS}\n"
        f"• آخر تحديث يومي: {stats.last_reset_day}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# -------------------- إلغاء المحادثة --------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم إلغاء العملية.")
    context.user_data.clear()
    return ConversationHandler.END

# -------------------- الدالة الرئيسية --------------------
def main() -> None:
    """تشغيل البوت."""
    # بناء التطبيق
    application = Application.builder().token(TOKEN).build()

    # إضافة معالج المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHOTO: [
                MessageHandler(filters.PHOTO, photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, photo_handler),
            ],
            DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, details_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("stats", stats_command))

    # تشغيل البوت (يستمر في الاستماع)
    application.run_polling()

if __name__ == "__main__":
    main()
