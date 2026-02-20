"""
VAPI Assistant Setup — Aria
============================
Creates and configures the Aria voice scheduling agent on VAPI.

Stack:
  Brain:        Claude Opus 4.6 (Anthropic)
  Voice:        Sarah — ElevenLabs Turbo v2.5
  Transcriber:  Scribe v1 (ElevenLabs)

Usage:
    python setup_vapi_assistant.py          # Create new
    python setup_vapi_assistant.py update   # Update existing
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

VAPI_API_KEY = os.getenv("VAPI_API_KEY")
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")

VAPI_BASE_URL = "https://api.vapi.ai"

# ──────────────────────────────────────────────
# Aria — The Scheduling Agent
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are Aria, a professional and warm voice scheduling assistant. You have a calm, confident presence — like a great executive assistant who genuinely enjoys helping people organize their time.

YOUR IDENTITY:
- Your name is Aria
- You work as a scheduling assistant
- You're polished but human — not robotic, not overly bubbly
- You speak in concise, natural sentences appropriate for voice conversation
- You occasionally use phrases like "Perfect", "Got it", "Sounds great", "Absolutely"

CORE TASK:
Help callers schedule meetings by collecting:
1. Their name
2. Preferred date and time
3. (Optional) Meeting title
4. (Optional) Duration

CONVERSATION FLOW:

Step 1 — Greeting & Name:
- You introduce yourself and ask for their name
- If the transcription seems garbled or unusual, politely ask them to spell it: "Could you spell that for me?"
- Users may have names from any culture — Indian names like "Sai Teja", "Priya", "Arjun" are common
- Once you have the name, use it naturally throughout the conversation

Step 2 — Date & Time:
- Ask when they'd like to schedule
- Accept natural language: "next Tuesday afternoon", "tomorrow at 3", "in two days around noon"
- If vague (e.g., "sometime next week"), help them narrow down: "Any particular day next week? And would morning or afternoon work better?"
- If they give a date but no time, ask for the time
- If they give a time but no date, ask for the date
- ALWAYS confirm timezone: "Just to confirm, that's [time] Eastern time, correct?"

Step 3 — Meeting Title & Duration:
- Ask if they'd like to name the meeting
- If they decline, suggest: "No problem, I'll call it 'Meeting with [name]'"
- For duration, use smart defaults based on the title:
  * "Quick sync", "check-in", "standup", "catch up" → suggest 15 minutes
  * "Meeting", "discussion", "review" → suggest 30 minutes  
  * "Workshop", "kickoff", "planning", "brainstorm", "deep dive" → suggest 60 minutes
  * If unclear, default to 30 minutes
- Confirm the duration: "I'll set that for [X] minutes — does that work?"

Step 4 — Availability Check:
- BEFORE confirming, call check_availability to verify the slot is open
- If available: proceed to confirmation
- If conflict exists: "I see you already have [event name] at that time. How about [suggest 1 hour later]? Or I can check what slots are open if you'd prefer."
- If user asks what's available, call get_available_slots to offer 3 open time slots

Step 5 — Confirmation:
- Read back ALL details clearly: "Let me confirm — [Name], [Title], [Date] at [Time] [Timezone], for [Duration]. Shall I book it?"
- Wait for explicit confirmation ("yes", "correct", "book it", "go ahead")
- If they want to change something ("actually make it Friday", "change the time to 4"), update naturally without restarting
- ONLY call schedule_event AFTER they confirm

Step 6 — Post-Booking:
- Confirm success: "You're all set! [Title] is on your calendar for [Date] at [Time]."
- Ask if they need anything else
- If they want to schedule another meeting, go back to Step 2

IMPORTANT RULES:
- NEVER schedule without explicit user confirmation
- NEVER skip the timezone confirmation
- If the user mentions a date in the past, gently correct: "That date has already passed. Did you mean [next occurrence]?"
- If the calendar API has an error, say: "Give me just a moment..." and retry once. If it fails again: "I'm having a small technical hiccup. Could we try a different time?"
- Keep responses SHORT — 1-2 sentences max. This is a voice call, not an email.
- Don't repeat information the user already gave you
- If the user says goodbye or "that's all", end gracefully: "Great talking with you, [Name]! Have a wonderful day."

PERSONALITY:
- Warm but efficient — respect the caller's time
- Confident, not uncertain — don't say "um", "I think", "maybe"
- Slightly personable — "That's a great time for a meeting" is fine
- Professional — no slang, no emojis in speech
- Adaptive — match the caller's energy (if they're rushed, be concise; if they're chatty, be a touch warmer)
"""

ASSISTANT_CONFIG = {
    "name": "Aria — Voice Scheduling Assistant",

    "firstMessage": "Hi there! I'm Aria, your scheduling assistant. I'd love to help you set up a meeting. What's your name?",

    # ── Brain: Claude Opus 4.6 ──
    "model": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "schedule_event",
                    "description": "Create a calendar event. Call ONLY after the user explicitly confirms all details (name, date, time, title, duration). Never call this without confirmation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The caller's name"
                            },
                            "date": {
                                "type": "string",
                                "description": "Meeting date in natural language or ISO format (e.g., 'tomorrow', 'next Monday', '2026-02-21', 'March 5th')"
                            },
                            "time": {
                                "type": "string",
                                "description": "Meeting time (e.g., '3:00 PM', '15:00', '10 AM', 'noon')"
                            },
                            "title": {
                                "type": "string",
                                "description": "Meeting title. Defaults to 'Meeting with [name]' if not provided."
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Meeting duration in minutes. Use smart defaults: 15 for quick syncs, 30 for standard meetings, 60 for workshops/kickoffs."
                            },
                            "timezone": {
                                "type": "string",
                                "description": "Timezone confirmed with the user (e.g., 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'America/Denver'). Default: America/New_York"
                            }
                        },
                        "required": ["name", "date", "time"]
                    }
                },
                "server": {
                    "url": f"{SERVER_URL}/tools/api/v1/schedule-event"
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_availability",
                    "description": "Check if a specific time slot is available on the calendar. Always call this BEFORE scheduling to verify availability and avoid conflicts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "The date to check"
                            },
                            "time": {
                                "type": "string",
                                "description": "The time to check"
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration to check in minutes. Defaults to 30."
                            }
                        },
                        "required": ["date", "time"]
                    }
                },
                "server": {
                    "url": f"{SERVER_URL}/tools/api/v1/check-availability"
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_available_slots",
                    "description": "Get available time slots for a given date. Call this when the user asks 'what's available?' or when you need to suggest alternative times after a conflict.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "The date to find available slots for"
                            },
                            "preferred_period": {
                                "type": "string",
                                "description": "Preferred time of day: 'morning' (9AM-12PM), 'afternoon' (12PM-5PM), 'evening' (5PM-8PM), or 'any'. Defaults to 'any'."
                            }
                        },
                        "required": ["date"]
                    }
                },
                "server": {
                    "url": f"{SERVER_URL}/tools/api/v1/available-slots"
                }
            }
        ]
    },

    # ── Voice: Sarah — ElevenLabs Turbo v2.5 ──
    "voice": {
        "provider": "11labs",
        "voiceId": "EXAVITQu4vr4xnSDxMaL",
        "model": "eleven_turbo_v2_5",
        "stability": 0.55,
        "similarityBoost": 0.75,
        "optimizeStreamingLatency": 4,
    },

    # ── Transcriber: Scribe v1 ──
    "transcriber": {
        "provider": "talkscribe",
        "model": "scribe-v1",
        "language": "en",
    },

    # ── Call Settings ──
    "firstMessageMode": "assistant-speaks-first",
    "endCallMessage": "It was great helping you today! Have a wonderful day. Goodbye!",
    "silenceTimeoutSeconds": 45,
    "maxDurationSeconds": 600,
    "responseDelaySeconds": 0.4,
    "backgroundSound": "off",

    # ── Server Events ──
    "serverUrl": f"{SERVER_URL}/api/webhook/vapi",
}


def create_assistant():
    """Create the VAPI assistant and return its ID."""
    if not VAPI_API_KEY:
        print("❌ VAPI_API_KEY not set in .env")
        print("   Get your API key from https://dashboard.vapi.ai")
        return None

    print("🔧 Creating Aria...")
    print(f"   Server URL: {SERVER_URL}")
    print(f"   Model: Claude Opus 4.6")
    print(f"   Voice: Sarah (ElevenLabs Turbo v2.5)")
    print(f"   Transcriber: Scribe v1")

    response = httpx.post(
        f"{VAPI_BASE_URL}/assistant",
        headers={
            "Authorization": f"Bearer {VAPI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=ASSISTANT_CONFIG,
        timeout=30,
    )

    if response.status_code == 201:
        data = response.json()
        assistant_id = data["id"]
        print(f"\n✅ Aria is live!")
        print(f"   Assistant ID: {assistant_id}")
        print(f"\n📞 Test: https://dashboard.vapi.ai")

        env_path = ".env"
        with open(env_path, "a") as f:
            f.write(f"\nVAPI_ASSISTANT_ID={assistant_id}\n")
        print(f"   Assistant ID saved to .env")

        return assistant_id
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"   {response.text}")
        return None


def update_assistant(assistant_id: str):
    """Update an existing assistant."""
    if not VAPI_API_KEY:
        print("❌ VAPI_API_KEY not set")
        return False

    print(f"🔧 Updating Aria ({assistant_id})...")

    response = httpx.patch(
        f"{VAPI_BASE_URL}/assistant/{assistant_id}",
        headers={
            "Authorization": f"Bearer {VAPI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=ASSISTANT_CONFIG,
        timeout=30,
    )

    if response.status_code == 200:
        print("✅ Aria updated!")
        return True
    else:
        print(f"❌ Update failed: {response.status_code} — {response.text}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "update":
        assistant_id = os.getenv("VAPI_ASSISTANT_ID")
        if assistant_id:
            update_assistant(assistant_id)
        else:
            print("No VAPI_ASSISTANT_ID found. Creating new...")
            create_assistant()
    else:
        create_assistant()
