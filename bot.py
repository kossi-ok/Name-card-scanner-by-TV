import io
import csv
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from database import (
    init_db,
    add_contact,
    update_contact,
    find_duplicate_contact,
    get_user_contacts,
    count_user_contacts,
    search_contacts,
    get_contact_by_id,
    delete_contact,
    get_all_contacts_for_export
)
from card_scanner import scan_card_image, get_model_name
from vcard_utils import generate_vcard

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Persistent Interactive Keyboard Menu
MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🗂️ View Contacts"), KeyboardButton("🔍 Search Contact")],
        [KeyboardButton("📊 Export CSV"), KeyboardButton("🤖 AI Model")],
        [KeyboardButton("❓ Help")]
    ],
    resize_keyboard=True
)

async def post_init(application):
    """Configures the persistent Telegram [/] Menu button for all users."""
    commands = [
        BotCommand("start", "Start bot & show menu"),
        BotCommand("menu", "Open interactive menu"),
        BotCommand("contacts", "View saved contacts"),
        BotCommand("search", "Search contacts by name or company"),
        BotCommand("export", "Download CSV spreadsheet"),
        BotCommand("model", "View active AI model"),
        BotCommand("help", "Instructions & help")
    ]
    await application.bot.set_my_commands(commands)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"👋 **Hi {user_name}! Welcome to your AI Business Card Directory.**\n\n"
        "📸 **How to use:**\n"
        "Just snap a photo of any business card and send it to me.\n"
        "Gemini AI will read all contact details, check for duplicates, save it to your private directory, "
        "and send you a 1-tap contact card (`.vcf`) for your phone!\n\n"
        "🗂️ **Quick Actions:**\n"
        "Use the menu buttons below or click the `[/] Menu` button anytime.\n\n"
        "🔒 *Your data is private to your Telegram account.*"
    )
    await update.message.reply_markdown(welcome_text, reply_markup=MAIN_MENU_KEYBOARD)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opens the interactive main menu."""
    menu_text = (
        "🗂️ **Business Card Directory Menu**\n\n"
        "Choose an action from the keyboard below, or send a photo of any business card to scan:"
    )
    await update.message.reply_markdown(menu_text, reply_markup=MAIN_MENU_KEYBOARD)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "💡 **Card Scanner Bot Help**\n\n"
        "1. **Scan a card:** Take or upload a clear photo of any business card.\n"
        "2. **Duplicate Detection:** If a contact already exists (matching email, phone, or name), you can update it or save as new.\n"
        "3. **1-Tap Save:** The bot replies with a `.vcf` file you can tap to add to Apple or Google Contacts.\n"
        "4. **Search:** Tap '🔍 Search Contact' or type `/search <name or company>`.\n"
        "5. **Export:** Tap '📊 Export CSV' or type `/export` to download a spreadsheet.\n"
        "6. **Delete:** Click the '🗑️ Delete' button on any card message or use `/delete <id>`."
    )
    await update.message.reply_markdown(help_text, reply_markup=MAIN_MENU_KEYBOARD)

async def send_vcf_card(chat, contact_dict: dict):
    """Generates and sends a vCard (.vcf) document to the user."""
    vcard_content = generate_vcard(contact_dict)
    name = contact_dict.get("full_name") or "Contact"
    vcf_file = io.BytesIO(vcard_content.encode("utf-8"))
    vcf_file.name = f"{name.replace(' ', '_')}.vcf"

    await chat.send_document(
        document=InputFile(vcf_file, filename=vcf_file.name),
        caption=f"📲 Tap file to save **{name}** to your phone's contacts!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes uploaded business card photo with duplicate detection."""
    user_id = update.effective_user.id
    status_msg = await update.message.reply_text(f"🔍 Scanning business card with Gemini ({get_model_name()})...")

    try:
        # Download highest resolution image
        photo = update.message.photo[-1]
        file_obj = await photo.get_file()
        image_bytes = await file_obj.download_as_bytearray()

        # Run extraction through Gemini
        card = scan_card_image(bytes(image_bytes))
        contact_dict = card.model_dump()

        phones_str = ", ".join(card.phones) if card.phones else "N/A"
        emails_str = ", ".join(card.emails) if card.emails else "N/A"

        # Check for duplicates
        dup, match_reason = find_duplicate_contact(user_id, contact_dict)
        if dup:
            # Store pending card in user session for resolution
            context.user_data["pending_card"] = contact_dict

            dup_text = (
                f"⚠️ **Duplicate Contact Found!** ({match_reason})\n\n"
                f"📂 **Existing Contact in Directory:** [#{dup['id']}]\n"
                f"👤 **Name:** {dup['full_name']}\n"
                f"💼 **Title:** {dup['job_title'] or 'N/A'}\n"
                f"🏢 **Company:** {dup['company'] or 'N/A'}\n"
                f"📞 **Phone:** {dup['phones'] or 'N/A'}\n"
                f"✉️ **Email:** {dup['emails'] or 'N/A'}\n\n"
                f"🆕 **Newly Scanned Card:**\n"
                f"👤 **Name:** {card.full_name}\n"
                f"💼 **Title:** {card.job_title or 'N/A'}\n"
                f"🏢 **Company:** {card.company or 'N/A'}\n"
                f"📞 **Phone:** {phones_str}\n"
                f"✉️ **Email:** {emails_str}\n\n"
                f"Would you like to update the existing contact or save as a new entry?"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Update Existing Contact", callback_data=f"dup_upd_{dup['id']}")],
                [InlineKeyboardButton("➕ Save as New Entry", callback_data="dup_new")],
                [InlineKeyboardButton("❌ Cancel", callback_data="dup_cancel")]
            ])

            await status_msg.delete()
            await update.message.reply_markdown(dup_text, reply_markup=keyboard)
            return

        # No duplicate: save directly
        contact_id = add_contact(user_id, contact_dict)

        details = (
            f"✅ **Business Card Saved!** [#{contact_id}]\n\n"
            f"👤 **Name:** {card.full_name}\n"
            f"💼 **Title:** {card.job_title or 'N/A'}\n"
            f"🏢 **Company:** {card.company or 'N/A'}\n"
            f"📞 **Phone:** {phones_str}\n"
            f"✉️ **Email:** {emails_str}\n"
            f"🌐 **Website:** {card.website or 'N/A'}\n"
            f"📍 **Address:** {card.address or 'N/A'}"
        )
        if card.notes:
            details += f"\n📝 **Notes:** {card.notes}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Delete Contact", callback_data=f"del_{contact_id}")]
        ])

        await status_msg.delete()
        await update.message.reply_markdown(details, reply_markup=keyboard)

        # Send .vcf file
        await send_vcf_card(update.effective_chat, contact_dict)

    except Exception as e:
        logger.error(f"Error processing card: {e}", exc_info=True)
        await status_msg.edit_text(
            f"⚠️ Could not extract card details: {str(e)}\n"
            "Please ensure the image is clear and well-lit."
        )

async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles taps on the interactive reply keyboard buttons."""
    text = update.message.text
    if text == "🗂️ View Contacts":
        await contacts_command(update, context)
    elif text == "🔍 Search Contact":
        await update.message.reply_markdown(
            "🔍 **Search Directory**\n\n"
            "To search, type `/search <name or company>`\n"
            "*Example:* `/search Google` or `/search John`"
        )
    elif text == "📊 Export CSV":
        await export_command(update, context)
    elif text == "🤖 AI Model":
        await model_command(update, context)
    elif text == "❓ Help":
        await help_command(update, context)

PAGE_SIZE = 5

def render_contacts_view(user_id: int, page: int = 1):
    """Generates paginated contacts text and navigation keyboard."""
    total = count_user_contacts(user_id)
    if total == 0:
        return "📭 Your contact directory is empty. Send me a business card photo to get started!", None

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PAGE_SIZE

    contacts = get_user_contacts(user_id, limit=PAGE_SIZE, offset=offset)

    start_idx = offset + 1
    end_idx = min(offset + len(contacts), total)
    text = f"🗂️ **Your Directory ({total} contact{'s' if total != 1 else ''}):**\n"
    text += f"*Showing {start_idx}–{end_idx} of {total}*\n\n"

    for i, c in enumerate(contacts, start=start_idx):
        company_tag = f" ({c['company']})" if c['company'] else ""
        title_tag = f" - {c['job_title']}" if c['job_title'] else ""
        phones = f"\n   📞 {c['phones']}" if c['phones'] else ""
        emails = f" | ✉️ {c['emails']}" if c['emails'] else ""
        text += f"**{i}. {c['full_name']}**{company_tag}{title_tag}{phones}{emails}\n\n"

    text += "💡 *Use `/search <name>` to find someone, or `/export` to download CSV.*"

    keyboard = None
    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"page_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page + 1}"))
        keyboard = InlineKeyboardMarkup([nav_buttons])

    return text, keyboard

async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists saved contacts for this user with pagination."""
    user_id = update.effective_user.id
    text, keyboard = render_contacts_view(user_id, page=1)
    await update.message.reply_markdown(text, reply_markup=keyboard)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search user's contacts."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: `/search <name or company>`\nExample: `/search John`")
        return

    query = " ".join(context.args)
    results = search_contacts(user_id, query)

    if not results:
        await update.message.reply_text(f"🔍 No contacts found matching '{query}'.")
        return

    text = f"🔍 **Search results for '{query}' ({len(results)} found):**\n\n"
    for c in results:
        text += (
            f"👤 **{c['full_name']}** [#{c['id']}]\n"
            f"🏢 {c['company'] or 'N/A'} | 💼 {c['job_title'] or 'N/A'}\n"
            f"📞 {c['phones'] or 'N/A'} | ✉️ {c['emails'] or 'N/A'}\n\n"
        )
    await update.message.reply_markdown(text)

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exports user's contacts into a downloadable CSV spreadsheet."""
    user_id = update.effective_user.id
    contacts = get_all_contacts_for_export(user_id)

    if not contacts:
        await update.message.reply_text("📭 You don't have any contacts to export yet.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Full Name", "Job Title", "Company", "Phones", "Emails", "Website", "Address", "Notes", "Date Added"])

    for c in contacts:
        writer.writerow([
            c["id"],
            c["full_name"],
            c["job_title"],
            c["company"],
            c["phones"],
            c["emails"],
            c["website"],
            c["address"],
            c["notes"],
            c["created_at"]
        ])

    csv_bytes = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    csv_bytes.name = "my_contacts_directory.csv"

    await update.message.reply_document(
        document=InputFile(csv_bytes, filename="my_contacts_directory.csv"),
        caption=f"📊 Here is your exported directory ({len(contacts)} contacts)."
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline button clicks such as delete or duplicate resolution."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data.startswith("del_"):
        contact_id = int(data.split("_")[1])
        success = delete_contact(user_id, contact_id)
        if success:
            await query.edit_message_text(f"🗑️ Contact #{contact_id} was deleted from your directory.")
        else:
            await query.edit_message_text("⚠️ Could not delete contact (already deleted or unauthorized).")

    elif data.startswith("dup_upd_"):
        contact_id = int(data.split("_")[2])
        pending_card = context.user_data.pop("pending_card", None)
        if not pending_card:
            await query.edit_message_text("⚠️ Card session expired. Please re-send the business card photo.")
            return

        success = update_contact(user_id, contact_id, pending_card)
        if success:
            await query.edit_message_text(
                f"✅ **Contact #{contact_id} updated successfully!**\n\n"
                f"👤 **Name:** {pending_card.get('full_name')}\n"
                f"💼 **Title:** {pending_card.get('job_title') or 'N/A'}\n"
                f"🏢 **Company:** {pending_card.get('company') or 'N/A'}\n"
                f"📞 **Phone:** {', '.join(pending_card.get('phones', [])) if isinstance(pending_card.get('phones'), list) else pending_card.get('phones') or 'N/A'}\n"
                f"✉️ **Email:** {', '.join(pending_card.get('emails', [])) if isinstance(pending_card.get('emails'), list) else pending_card.get('emails') or 'N/A'}"
            )
            await send_vcf_card(query.message.chat, pending_card)
        else:
            await query.edit_message_text("⚠️ Failed to update contact. Please try again.")

    elif data == "dup_new":
        pending_card = context.user_data.pop("pending_card", None)
        if not pending_card:
            await query.edit_message_text("⚠️ Card session expired. Please re-send the business card photo.")
            return

        contact_id = add_contact(user_id, pending_card)
        await query.edit_message_text(
            f"✅ **Saved as a new entry!** [#{contact_id}]\n\n"
            f"👤 **Name:** {pending_card.get('full_name')}\n"
            f"🏢 **Company:** {pending_card.get('company') or 'N/A'}"
        )
        await send_vcf_card(query.message.chat, pending_card)

    elif data == "dup_cancel":
        context.user_data.pop("pending_card", None)
        await query.edit_message_text("❌ Cancelled. No changes were made.")

    elif data.startswith("page_"):
        target_page = int(data.split("_")[1])
        text, keyboard = render_contacts_view(user_id, page=target_page)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    elif data == "noop":
        pass

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is healthy and running!")

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Health server could not bind to port {port}: {e}")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays active Gemini model."""
    await update.message.reply_markdown(f"🤖 **Current AI Model:** `{get_model_name()}`")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        print("❌ Error: TELEGRAM_BOT_TOKEN is not set in .env")
        return

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key or gemini_key == "your_gemini_api_key_here":
        print("❌ Error: GEMINI_API_KEY is not set in .env")
        return

    # Initialize the database
    init_db()

    # Start lightweight health-check server for cloud hosting (Render/Koyeb)
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Build Telegram application with post_init to register commands in Telegram UI
    app = ApplicationBuilder().token(token).post_init(post_init).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("contacts", contacts_command))
    app.add_handler(CommandHandler("list", contacts_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print(f"🚀 Business Card Scanner Telegram Bot is running! [Model: {get_model_name()}]")
    app.run_polling()

if __name__ == "__main__":
    main()
