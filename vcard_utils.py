from typing import Dict, Any

def generate_vcard(contact: Dict[str, Any]) -> str:
    """
    Generates a standard vCard (.vcf) formatted string from a contact dict.
    Allows 1-tap save into iOS Contacts and Android Google Contacts.
    """
    name = contact.get("full_name") or "Contact"
    title = contact.get("job_title") or ""
    company = contact.get("company") or ""
    website = contact.get("website") or ""
    address = contact.get("address") or ""
    notes = contact.get("notes") or ""

    phones = contact.get("phones")
    if isinstance(phones, str):
        phone_list = [p.strip() for p in phones.split(",") if p.strip()]
    elif isinstance(phones, list):
        phone_list = phones
    else:
        phone_list = []

    emails = contact.get("emails")
    if isinstance(emails, str):
        email_list = [e.strip() for e in emails.split(",") if e.strip()]
    elif isinstance(emails, list):
        email_list = emails
    else:
        email_list = []

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{name}",
        f"N:;{name};;;"
    ]

    if company:
        lines.append(f"ORG:{company}")
    if title:
        lines.append(f"TITLE:{title}")

    for phone in phone_list:
        lines.append(f"TEL;TYPE=WORK,VOICE:{phone}")

    for email in email_list:
        lines.append(f"EMAIL;TYPE=PREF,INTERNET:{email}")

    if website:
        lines.append(f"URL:{website}")

    if address:
        lines.append(f"ADR;TYPE=WORK:;;{address};;;;")

    if notes:
        lines.append(f"NOTE:{notes}")

    lines.append("END:VCARD\n")
    return "\n".join(lines)
