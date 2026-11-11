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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"👋 **Hi {user_name}! Welcome to your AI Business Card Directory.**\n\n"
        "📸 **How to use:**\n"
        "Just snap a photo of any business card and send it to me. "
        "Gemini AI will read all contact details, save it to your private directory, "
        "and send you a 1-tap contact card (`.vcf`) for your phone!\n\n"
        "🗂️ **Commands:**\n"
        "• `/contacts` - View your recent contacts\n"
        "• `/search <query>` - Find contacts by name or company\n"
        "• `/export` - Download all your contacts as CSV\n"
        "• `/help` - Show instructions\n\n"
        "🔒 *Your data is private to your Telegram account.*"
    )
    await update.message.reply_markdown(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "💡 **Card Scanner Bot Help**\n\n"
        "1. **Scan a card:** Take or upload a clear photo of any business card.\n"
        "2. **1-Tap Save:** The bot replies with a `.vcf` file you can tap to add to Apple or Google Contacts.\n"
        "3. **Search:** Use `/search Google` or `/search John` to find contacts.\n"
        "4. **Export:** Use `/export` to get a spreadsheet CSV of your whole directory.\n"
        "5. **Delete:** Click the '🗑️ Delete' button on any card message or use `/delete <id>`."
    )
    await update.message.reply_markdown(help_text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes uploaded business card photo."""
    user_id = update.effective_user.id
    status_msg = await update.message.reply_text(f"🔍 Scanning business card with Gemini ({get_model_name()})...")

    try:
        # Download highest resolution image
        photo = update.message.photo[-1]
        file_obj = await photo.get_file()
        image_bytes = await file_obj.download_as_bytearray()

        # Run extraction through Gemini
        card = scan_card_image(bytes(image_bytes))

        # Save to user's isolated directory in DB
        contact_dict = card.model_dump()
        contact_id = add_contact(user_id, contact_dict)

        # Build clean display message
        phones_str = ", ".join(card.phones) if card.phones else "N/A"
        emails_str = ", ".join(card.emails) if card.emails else "N/A"

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

        # Inline button to delete if mistake
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Delete Contact", callback_data=f"del_{contact_id}")]
        ])

        # Delete status message
        await status_msg.delete()

        # Reply with contact details
        await update.message.reply_markdown(details, reply_markup=keyboard)

        # Generate and send .vcf file for instant phonebook import
        vcard_content = generate_vcard({
            "full_name": card.full_name,
            "job_title": card.job_title,
            "company": card.company,
            "phones": card.phones,
            "emails": card.emails,
            "website": card.website,
            "address": card.address,
            "notes": card.notes
        })
        vcf_file = io.BytesIO(vcard_content.encode("utf-8"))
        vcf_file.name = f"{card.full_name.replace(' ', '_')}.vcf"

        await update.message.reply_document(
            document=InputFile(vcf_file, filename=vcf_file.name),
            caption=f"📲 Tap file to save **{card.full_name}** to your phone's contacts!"
        )

    except Exception as e:
        logger.error(f"Error processing card: {e}", exc_info=True)
        await status_msg.edit_text(
            f"⚠️ Could not extract card details: {str(e)}\n"
            "Please ensure the image is clear and well-lit."
        )

async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists saved contacts for this user."""
    user_id = update.effective_user.id
    contacts = get_user_contacts(user_id, limit=10)
    total = count_user_contacts(user_id)

    if not contacts:
        await update.message.reply_text("📭 Your contact directory is empty. Send me a business card photo to get started!")
        return

    text = f"🗂️ **Your Directory ({len(contacts)} of {total} contacts):**\n\n"
    for c in contacts:
        company_tag = f" ({c['company']})" if c['company'] else ""
        title_tag = f" - {c['job_title']}" if c['job_title'] else ""
        phones = f" | 📞 {c['phones']}" if c['phones'] else ""
        text += f"• **{c['full_name']}**{company_tag}{title_tag}{phones}\n"

    text += "\n💡 *Use `/search <query>` to find specific people, or `/export` to download CSV.*"
    await update.message.reply_markdown(text)

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

    # Create CSV in memory
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
    """Handles inline button clicks such as deleting a contact."""
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

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is healthy and running!")

    def log_message(self, format, *args):
        # Silence HTTP access logs to keep terminal clean
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

    # Build Telegram application
    app = ApplicationBuilder().token(token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("contacts", contacts_command))
    app.add_handler(CommandHandler("list", contacts_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print(f"🚀 Business Card Scanner Telegram Bot is running! [Model: {get_model_name()}]")
    app.run_polling()

if __name__ == "__main__":
    main()
