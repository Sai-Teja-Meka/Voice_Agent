"""
VAPI Assistant Setup
====================
Creates and configures the voice scheduling agent on VAPI.
Run this once to set up your assistant, then use the returned 
assistant ID in your VAPI dashboard or web widget.

Usage:
    python setup_vapi_assistant.py
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
# Assistant Configuration
# ──────────────────────────────────────────────

ASSISTANT_CONFIG = {
    "name": "Vikara Scheduling Assistant",
    
    # ── The Persona ──
    # Not just a scheduler — a warm, efficient presence.
    "firstMessage": "Hey there! I'm your scheduling assistant. I'd love to help you set up a meeting. Could you start by telling me your name?",
    
    "model": {
        "provider": "openai",
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": """You are a friendly, efficient voice scheduling assistant built for Vikara.ai. Your personality is warm but concise — think of a great executive assistant who respects people's time.

Your job is to schedule meetings by collecting:
1. The caller's name
2. Their preferred date and time
3. Optionally, a meeting title

CONVERSATION FLOW:
- Greet the user warmly and ask for their name
- Once you have their name, ask for their preferred date and time
- Optionally ask if they'd like to give the meeting a title (suggest a default like "Meeting with [name]" if they decline)
- Confirm ALL details back to the user before scheduling
- ONLY call the schedule_event tool AFTER the user confirms the details
- After scheduling, let them know it's confirmed and ask if they need anything else

IMPORTANT RULES:
- Always confirm details before creating the event
- If the user gives a vague time like "tomorrow afternoon", ask for a specific time
- If there's a scheduling conflict, politely suggest trying another time
- Keep responses brief and natural — you're on a voice call, not writing an essay
- Default meeting duration is 30 minutes unless the user specifies otherwise
- Be conversational, not robotic. Use the caller's name occasionally.
- If the user wants to schedule multiple meetings, handle them one at a time

PERSONALITY NOTES:
- You're helpful but not overly enthusiastic
- You speak clearly and at a natural pace
- You occasionally use phrases like "Perfect", "Got it", "Sounds good"
- You don't say "um" or "uh" — you're polished but human"""
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "schedule_event",
                    "description": "Create a calendar event after the user confirms the meeting details. Call this ONLY after confirming name, date, time, and title with the user.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name of the person scheduling the meeting"
                            },
                            "date": {
                                "type": "string",
                                "description": "The date for the meeting (e.g., '2026-02-20', 'tomorrow', 'next Monday', 'February 20th')"
                            },
                            "time": {
                                "type": "string",
                                "description": "The time for the meeting (e.g., '3:00 PM', '15:00', '10 AM')"
                            },
                            "title": {
                                "type": "string",
                                "description": "The title/subject of the meeting. Defaults to 'Meeting with [name]' if not specified."
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration of the meeting in minutes. Defaults to 30."
                            }
                        },
                        "required": ["name", "date", "time"]
                    }
                },
                "server": {
                    "url": f"{SERVER_URL}/api/tool/schedule-event"
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_availability",
                    "description": "Check if a specific date and time slot is available on the calendar. Use this before scheduling if you want to verify availability.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "The date to check (e.g., '2026-02-20', 'tomorrow')"
                            },
                            "time": {
                                "type": "string",
                                "description": "The time to check (e.g., '3:00 PM')"
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
                    "url": f"{SERVER_URL}/api/tool/check-availability"
                }
            }
        ]
    },
    
    # ── Voice Configuration ──
    "voice": {
    "provider": "openai",
    "model": "gpt-4o-mini-tts",
    "voiceId": "alloy"
},
    
    # ── Transcriber ──
    "transcriber": {
    "provider": "deepgram",
    "model": "nova-2",
    "language": "en",
    "keywords": ["SaiTeja:5", "Teja:5"],
    },
    
    # ── Call Settings ──
    "endCallMessage": "Thanks for scheduling with me! Have a great day. Goodbye!",
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 300,  # 5 min max call
    
    # ── Server Events (webhook) ──
    "serverUrl": f"{SERVER_URL}/api/webhook/vapi",
}


def create_assistant():
    """Create the VAPI assistant and return its ID."""
    if not VAPI_API_KEY:
        print("❌ VAPI_API_KEY not set in .env")
        print("   Get your API key from https://dashboard.vapi.ai")
        return None

    print("🔧 Creating VAPI Assistant...")
    print(f"   Server URL: {SERVER_URL}")
    
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
        print(f"\n✅ Assistant created successfully!")
        print(f"   Assistant ID: {assistant_id}")
        print(f"\n📞 Test your agent:")
        print(f"   Web:   https://vapi.ai/agent/{assistant_id}")
        print(f"   Dashboard: https://dashboard.vapi.ai")
        
        # Save assistant ID to .env
        env_path = ".env"
        with open(env_path, "a") as f:
            f.write(f"\nVAPI_ASSISTANT_ID={assistant_id}\n")
        print(f"\n   Assistant ID saved to .env")
        
        return assistant_id
    else:
        print(f"❌ Failed to create assistant: {response.status_code}")
        print(f"   Response: {response.text}")
        return None


def update_assistant(assistant_id: str):
    """Update an existing assistant with the current config."""
    if not VAPI_API_KEY:
        print("❌ VAPI_API_KEY not set")
        return False

    print(f"🔧 Updating assistant {assistant_id}...")
    
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
        print("✅ Assistant updated!")
        return True
    else:
        print(f"❌ Update failed: {response.status_code} — {response.text}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        # Update existing assistant
        assistant_id = os.getenv("VAPI_ASSISTANT_ID")
        if assistant_id:
            update_assistant(assistant_id)
        else:
            print("No VAPI_ASSISTANT_ID found in .env. Creating new one...")
            create_assistant()
    else:
        create_assistant()
