# 📇 AI Business Card Scanner Telegram Bot

An AI-powered Telegram bot built with **Google Gemini API (Free Tier)** that lets you and your users snap photos of business cards to automatically extract and manage a private directory of contacts.

---

## ✨ Features

- **Multi-Tenant (Per-User Isolation)**: Anyone can use the bot. Each user has their own private database of contacts linked to their unique Telegram account ID.
- **Gemini Free-Tier Vision & Structured Extraction**: Accurately extracts Full Name, Job Title, Company, Phone Numbers, Email Addresses, Website, Physical Address, and Social Handles / Notes.
- **📲 1-Tap Phonebook Import (`.vcf` file)**: Every time a card is scanned, the bot sends back a standard vCard file. Tapping it adds the contact directly to your Apple or Android Contacts list!
- **📊 CSV Export**: Users can run `/export` at any time to download their full directory as a spreadsheet.
- **🔎 Instant Search**: Find any contact by name, company, or email with `/search <query>`.

---

## 🚀 Quick Setup Guide

### Step 1: Get Your Free API Keys

1. **Telegram Bot Token**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, give it a name and username (e.g. `MyCardScannerBot`).
   - Copy the HTTP API token provided.

2. **Gemini API Key (Free)**:
   - Go to [Google AI Studio](https://aistudio.google.com/).
   - Click **Get API key** and create a key (Free Tier).

---

### Step 2: Configure Environment Variables

In this directory, copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in your tokens:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
GEMINI_API_KEY=AIzaSy...your_gemini_api_key_here
```

---

### Step 3: Run the Bot

```bash
python bot.py
```

---

## 📱 Bot Commands

| Command | Description |
| :--- | :--- |
| **Send a Photo** | Takes a photo of any business card, extracts data, saves it, and sends back a `.vcf` file. |
| `/contacts` | Shows your recent saved contacts. |
| `/search <query>` | Search your personal contacts by name or company. |
| `/export` | Generates and sends a downloadable `.csv` file with all your contacts. |
| `/help` | Displays help and instructions. |

---

## 📁 Project Architecture

- **`bot.py`**: Telegram bot handlers, command routing, and interactive message generation.
- **`card_scanner.py`**: Gemini 3.1 Flash-Lite multimodal vision pipeline with Pydantic structured output.
- **`database.py`**: SQLite multi-tenant storage isolating each user's contacts by their Telegram ID.
- **`vcard_utils.py`**: vCard 3.0 generator for 1-tap phonebook saving.
