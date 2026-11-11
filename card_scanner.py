import os
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class ContactCard(BaseModel):
    full_name: str = Field(description="Full name of the person on the card")
    job_title: Optional[str] = Field(default="", description="Job title, designation, or professional role")
    company: Optional[str] = Field(default="", description="Company, organization, or brand name")
    phones: List[str] = Field(default_factory=list, description="All phone numbers found (mobile, office, fax)")
    emails: List[str] = Field(default_factory=list, description="All email addresses found")
    website: Optional[str] = Field(default="", description="Website URL or domain")
    address: Optional[str] = Field(default="", description="Physical street, city, state, or office address")
    notes: Optional[str] = Field(default="", description="Any slogans, department info, or social handles like LinkedIn/Twitter")

def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)

def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

def scan_card_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> ContactCard:
    """
    Sends business card image to Gemini free tier with structured output schema.
    """
    client = get_gemini_client()
    model_name = get_model_name()
    
    prompt = (
        "You are an expert OCR and business card information extractor. "
        "Analyze this business card image carefully and extract all contact details into the specified JSON format. "
        "If a field is not present or cannot be deciphered, leave it empty."
    )
    
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ContactCard,
            temperature=0.1
        )
    )
    
    return ContactCard.model_validate_json(response.text)
