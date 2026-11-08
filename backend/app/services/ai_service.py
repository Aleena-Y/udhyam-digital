"""
AI Service: Ollama LLM integration for the AI Business Advisor.
LLM is used ONLY for language understanding, intent extraction and explanation.
All business rules (eligibility, pricing, KYC) are enforced deterministically.
"""
import httpx
import json
import logging
from typing import List, Optional, AsyncGenerator
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Accel Business Advisor — a friendly, helpful assistant for small and medium business owners in India.

Your role is to:
1. Understand the customer's business (type, size, locations, needs) through conversation
2. Help them discover Accel Business products that fit their needs
3. Explain products in simple, clear language
4. Answer questions about connectivity, cloud services, and security

STRICT RULES — you must NEVER:
- Quote specific prices (the system shows real prices)
- Make eligibility decisions (the system enforces catalogue rules)
- Claim to process payments or verify documents
- Claim to be integrated with any real telecom system
- Make up business names, GSTINs, or any registry data

Always be warm, respectful and use simple language. If the customer writes in their preferred language, respond in that language.

When you identify business profile information from the conversation (city, employees, sites, segment type), 
include a JSON block at the end of your response like:
{"profile_update": {"city": "...", "employee_count": 5, "num_sites": 1, "segment": "micro|prof|multi|mfg"}}
Only include fields you are confident about from the conversation.

Available product categories: Connectivity, Communication, Cloud & Productivity, Security, IoT & Physical
Available segments: micro (1-10 employees, single site retail/services), prof (professional offices), 
multi (multi-site businesses), mfg (manufacturers)
"""


async def stream_chat(
    messages: List[dict],
    language: str = "English",
    business_context: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream chat response from Ollama.
    messages: list of {role: 'user'|'assistant', content: str}
    """
    system = SYSTEM_PROMPT
    if language and language.lower() != "english":
        system += f"\n\nIMPORTANT: The customer prefers {language}. Please respond in {language} primarily, but you may use English for technical product names."
    
    if business_context:
        ctx_parts = []
        if business_context.get("city"):
            ctx_parts.append(f"City: {business_context['city']} (Tier {business_context.get('city_tier', 2)})")
        if business_context.get("employee_count"):
            ctx_parts.append(f"Employees: {business_context['employee_count']}")
        if business_context.get("num_sites"):
            ctx_parts.append(f"Sites: {business_context['num_sites']}")
        if business_context.get("has_gstin"):
            ctx_parts.append("Has active GSTIN: Yes")
        if business_context.get("segment"):
            ctx_parts.append(f"Segment: {business_context['segment']}")
        if ctx_parts:
            system += "\n\nCurrent known business profile:\n" + "\n".join(ctx_parts)

    payload = {
        "model": settings.OLLAMA_MODEL,
        "system": system,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_ctx": 4096,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if content := data.get("message", {}).get("content", ""):
                                yield content
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
    except httpx.ConnectError:
        yield "⚠️ AI service is currently unavailable. Please check that Ollama is running. You can still browse products and get quotes manually."
    except httpx.TimeoutException:
        yield "⚠️ AI response timed out. Please try again."
    except Exception as e:
        logger.error(f"AI service error: {e}")
        yield "⚠️ An error occurred with the AI service. Please try again."


async def chat_complete(
    messages: List[dict],
    language: str = "English",
    business_context: Optional[dict] = None,
) -> str:
    """Non-streaming chat completion."""
    system = SYSTEM_PROMPT
    if language and language.lower() != "english":
        system += f"\n\nIMPORTANT: The customer prefers {language}. Please respond in {language}."
    
    if business_context:
        ctx_parts = []
        for key, label in [
            ("city", "City"), ("employee_count", "Employees"),
            ("num_sites", "Sites"), ("segment", "Segment")
        ]:
            if business_context.get(key):
                ctx_parts.append(f"{label}: {business_context[key]}")
        if ctx_parts:
            system += "\n\nBusiness profile:\n" + "\n".join(ctx_parts)

    payload = {
        "model": settings.OLLAMA_MODEL,
        "system": system,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 4096}
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
    except Exception as e:
        logger.error(f"AI service error: {e}")
        return "AI service unavailable. Please try again."


def extract_profile_update(ai_response: str) -> Optional[dict]:
    """Extract profile_update JSON block from AI response if present."""
    try:
        import re
        match = re.search(r'\{"profile_update":\s*(\{[^}]+\})\}', ai_response)
        if match:
            return json.loads('{"profile_update":' + match.group(1) + '}').get("profile_update")
    except Exception:
        pass
    return None


async def check_ollama_health() -> dict:
    """Check if Ollama is running and the model is available."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                model_available = any(settings.OLLAMA_MODEL in m for m in models)
                return {
                    "status": "online",
                    "model_available": model_available,
                    "available_models": models,
                    "configured_model": settings.OLLAMA_MODEL,
                }
    except Exception:
        pass
    return {
        "status": "offline",
        "model_available": False,
        "available_models": [],
        "configured_model": settings.OLLAMA_MODEL,
    }
