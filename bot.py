import sqlite3
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ============ غيّر هذول ============
TOKEN = "8616606756:AAH4xDHV0h6aCBNTDmMKmNfQ0HiqYCQGTFAا"
RESTAURANT_CHAT_ID = 7544266937   # آيدي حسابك (المطعم)
ADMIN_ID = 7544266937             # نفس آيدي حسابك
# ===================================

# ---------- قاعدة البيانات ----------
def init_db():
    conn = sqlite3.connect("restaurant.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY, category TEXT, name TEXT,
        price INTEGER, available INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT,
        phone TEXT, address TEXT, items TEXT, total INTEGER,
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()

def get_menu():
    conn = sqlite3.connect("restaurant.db")
    rows = conn.execute(
        "SELECT id, category, name, price FROM menu WHERE available=1"
    ).fetchall()
    conn.close()
    return rows

def get_item(iid):
    conn = sqlite3.connect("restaurant.db")
    row = conn.execute(
        "SELECT id, name, price FROM menu WHERE id=?", (iid,)
    ).fetchone()
    conn.close()
    return row

def save_order(name, phone, address, items, total):
    conn = sqlite3.connect("restaurant.db")
    cur = conn.execute(
        """INSERT INTO orders (customer_name, phone, address, items, total)
           VALUES (?,?,?,?,?)""",
        (name, phone, address, json.dumps(items, ensure_ascii=False), total)
    )
    oid = cur.lastrowid
    conn.commit()
    conn.close()
    return oid

def add_menu_item(category, name, price):
    conn = sqlite3.connect("restaurant.db")
    conn.execute(
        "INSERT INTO menu (category, name, price) VALUES (?,?,?)",
        (category, name, price)
    )
    conn.commit()
    conn.close()

# ---------- أوامر الزبون ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "أهلاً بك في مطعمنا 🍔\n"
        "اكتب /menu لعرض المنيو"
    )

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = get_menu()
    if not items:
        await update.message.reply_text("المنيو فارغ حالياً، تواصل مع المطعم.")
        return

    # تجميع حسب القسم
    categories = {}
    for iid, cat, name, price in items:
        categories.setdefault(cat, []).append((iid, name, price))

    keyboard = []
    for cat, prods in categories.items():
        keyboard.append([InlineKeyboardButton(f"── {cat} ──", callback_data="none")])
        for iid, name, price in prods:
            keyboard.append([InlineKeyboardButton(
                f"{name} — {price} د.ع",
                callback_data=f"add_{iid}"
            )])
    keyboard.append([InlineKeyboardButton("🛒 عرض السلة", callback_data="cart")])

    await update.message.reply_text(
        "اختر من المنيو:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "none":
        return

    cart = ctx.user_data.setdefault("cart", {})

    if data.startswith("add_"):
        iid = int(data.split("_")[1])
        cart[iid] = cart.get(iid, 0) + 1
        await q.message.reply_text(f"✅ تمت الإضافة (الكمية: {cart[iid]})")

    elif data == "cart":
        if not cart:
            await q.message.reply_text("السلة فاضية 🛒")
            return
        text = "🛒 سلتك:\n"
        total = 0
        for iid, qty in cart.items():
            item = get_item(iid)
            if item:
                _, name, price = item
                text += f"- {name} × {qty} = {price * qty} د.ع\n"
                total += price * qty
        text += f"\n💰 المجموع: {total} د.ع"
        kb = [
            [InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm")],
            [InlineKeyboardButton("🗑 تفريغ السلة", callback_data="clear")],
        ]
        await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "clear":
        ctx.user_data["cart"] = {}
        await q.message.reply_text("🗑 تم تفريغ السلة")

    elif data == "confirm":
        if not cart:
            await q.message.reply_text("السلة فاضية")
            return
        ctx.user_data["step"] = "name"
        await q.message.reply_text("📝 اكتب اسمك:")

# ---------- استقبال بيانات الزبون ----------
async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("step")
    if not step:
        return

    text = update.message.text

    if step == "name":
        ctx.user_data["name"] = text
        ctx.user_data["step"] = "phone"
        await update.message.reply_text("📞 اكتب رقم هاتفك:")

    elif step == "phone":
        ctx.user_data["phone"] = text
        ctx.user_data["step"] = "address"
        await update.message.reply_text("📍 اكتب عنوان التوصيل:")

    elif step == "address":
        ctx.user_data["address"] = text
        cart = ctx.user_data.get("cart", {})
        lines = []
        total = 0
        for iid, qty in cart.items():
            item = get_item(iid)
            if item:
                _, name, price = item
                lines.append(f"{name} × {qty} = {price * qty}")
                total += price * qty

        oid = save_order(
            ctx.user_data["name"],
            ctx.user_data["phone"],
            ctx.user_data["address"],
            lines,
            total
        )

        # إشعار المطعم
        msg = (
            f"🔔 طلب جديد #{oid}\n"
            f"👤 {ctx.user_data['name']}\n"
            f"📞 {ctx.user_data['phone']}\n"
            f"📍 {ctx.user_data['address']}\n"
            f"🍽 " + "\n".join(lines) + f"\n"
            f"💰 المجموع: {total} د.ع"
        )
        try:
            await ctx.bot.send_message(RESTAURANT_CHAT_ID, msg)
        except Exception as e:
            print("فشل إرسال إشعار للمطعم:", e)

        await update.message.reply_text(
            f"✅ تم استلام طلبك رقم #{oid}\n"
            f"سنتواصل معك قريباً للتأكيد."
        )
        ctx.user_data.clear()

# ---------- أوامر الأدمن ----------
async def add_item(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # الصيغة: /additem قسم | اسم | سعر
    args = " ".join(ctx.args)
    parts = [p.strip() for p in args.split("|")]
    if len(parts) != 3:
        await update.message.reply_text(
            "الصيغة الصحيحة:\n"
            "/additem برغر | برغر دجاج | 5000"
        )
        return
    category, name, price = parts
    try:
        price = int(price)
    except ValueError:
        await update.message.reply_text("السعر لازم يكون رقم")
        return
    add_menu_item(category, name, price)
    await update.message.reply_text(f"✅ أضيف: {name} — {price} د.ع")

async def orders_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("restaurant.db")
    rows = conn.execute(
        "SELECT id, customer_name, phone, total, status FROM orders ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("ما في طلبات بعد")
        return
    text = "📋 آخر 10 طلبات:\n\n"
    for oid, name, phone, total, status in rows:
        text += f"#{oid} | {name} | {phone} | {total} د.ع | {status}\n"
    await update.message.reply_text(text)

# ---------- تشغيل ----------
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("additem", add_item))
    app.add_handler(CommandHandler("orders", orders_list))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ البوت شغّال...")
    app.run_polling()

if __name__ == "__main__":
    main()