# 🎙️ Voice Scheduling Agent — Vikara.ai Assessment

A real-time voice assistant that schedules calendar events through natural conversation. Built with a focus on **production-grade architecture**, **intelligent conflict detection**, and a **warm, human-like conversational experience**.

> **Live Demo:** [Agent Link](https://vapi.ai/agent/YOUR_ASSISTANT_ID)  
> **API Dashboard:** [Deployed URL](https://your-app.railway.app)

---

## 🏗️ Architecture

```
┌──────────────┐     Voice/WebRTC     ┌──────────────┐     HTTPS Tool Calls     ┌──────────────────┐
│              │ ──────────────────► │              │ ──────────────────────► │                  │
│     User     │                     │  VAPI Agent  │                         │  FastAPI Server  │
│  (Browser/   │ ◄────────────────── │  (LLM +      │ ◄────────────────────── │  (Tool Handler)  │
│   Phone)     │     Voice Response  │   Voice)     │     Tool Results        │                  │
└──────────────┘                     └──────────────┘                         └────────┬─────────┘
                                                                                       │
                                                                              ┌────────▼─────────┐
                                                                              │  Google Calendar  │
                                                                              │       API         │
                                                                              └──────────────────┘
```

### Why This Architecture?

The system is designed as a **decoupled, tool-augmented voice pipeline**:

- **VAPI** handles the hard parts: WebRTC, STT (Deepgram Nova-2), TTS (ElevenLabs), and turn-taking — freeing us to focus on *what the agent does*, not *how it speaks*.
- **FastAPI backend** serves as the agent's "hands" — when the LLM decides to schedule an event, it calls our server as a tool, and we handle the Google Calendar logic.
- **Google Calendar API** with full OAuth2 flow — not a mock, not a stub. Real events on real calendars.

### Key Design Decisions

| Decision | Why |
|----------|-----|
| VAPI over raw WebRTC | Ship fast without sacrificing quality. VAPI handles telephony-grade voice infra. |
| Server URL Tools over webhooks | Synchronous tool execution = the agent waits for calendar confirmation before speaking. No race conditions. |
| Conflict detection before creation | Most candidates skip this. A great scheduling agent doesn't double-book you. |
| GPT-4o as the conversation brain | Best balance of speed + intelligence for real-time voice. |
| ElevenLabs "Rachel" voice | Warm, professional, natural — not the default robotic TTS. |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Google Cloud project with Calendar API enabled
- VAPI account ([dashboard.vapi.ai](https://dashboard.vapi.ai))

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/vikara-voice-agent.git
cd vikara-voice-agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Google Calendar Setup:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable "Google Calendar API"
3. Create OAuth 2.0 credentials (Web application)
4. Set redirect URI to `http://localhost:8000/auth/callback`
5. Copy Client ID and Client Secret to `.env`

**VAPI Setup:**
1. Sign up at [vapi.ai](https://vapi.ai)
2. Get your API key from the dashboard
3. Add it to `.env`

### 3. Start the Server

```bash
python -m app.server
# Or: uvicorn app.server:app --reload --port 8000
```

### 4. Authorize Google Calendar

Visit `http://localhost:8000/auth/login` in your browser. Complete the OAuth flow. You'll see a success message when connected.

### 5. Create the VAPI Agent

```bash
python setup_vapi_assistant.py
```

This will output your **Agent ID** and a **test link**. Click it to start talking!

---

## 📅 Calendar Integration — Deep Dive

The calendar integration isn't just "create an event." It's a **three-phase process**:

### Phase 1: Availability Check
Before creating any event, the agent can proactively check availability:
```
User: "How about 3 PM tomorrow?"
Agent → [check_availability tool] → "That slot is open! Shall I book it?"
```

### Phase 2: Conflict Detection
If a conflict exists, the agent negotiates:
```
User: "Schedule me at 2 PM on Friday"
Agent → [schedule_event tool] → Server detects conflict
Agent: "You already have 'Team Standup' at that time. Want to try a different slot?"
```

### Phase 3: Event Creation
Only after user confirmation:
```
Agent: "Just to confirm — meeting titled 'Project Review' for Teja on Friday at 3 PM. Shall I book it?"
User: "Yes!"
Agent → [schedule_event tool] → Google Calendar event created
Agent: "Done! It's on your calendar. Anything else?"
```

### OAuth2 Flow
- Uses Google's OAuth2 with offline access (refresh tokens)
- Credentials persisted securely in `token.json` (gitignored)
- Auto-refresh on expiry — no manual re-auth needed

---

## 🌐 Deployment

### Railway (Recommended)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up
```

Set environment variables in Railway dashboard, then update `GOOGLE_REDIRECT_URI` and `SERVER_URL` to your Railway URL.

### Docker

```bash
docker build -t vikara-voice-agent .
docker run -p 8000:8000 --env-file .env vikara-voice-agent
```

---

## 📸 Demo

> **Loom Video:** [Watch the demo](YOUR_LOOM_LINK)

| Step | Screenshot |
|------|------------|
| Agent starts conversation | *screenshot* |
| Collects details | *screenshot* |
| Confirms & creates event | *screenshot* |
| Event on Google Calendar | *screenshot* |

---

## 🗂️ Project Structure

```
vikara-voice-agent/
├── app/
│   ├── __init__.py
│   ├── server.py              # FastAPI — routes, VAPI tool handlers
│   └── calendar_service.py    # Google Calendar — OAuth, events, conflicts
├── setup_vapi_assistant.py    # One-click VAPI agent creation
├── requirements.txt
├── Procfile                   # Railway/Render deployment
├── Dockerfile                 # Container deployment
├── .env.example
├── .gitignore
└── README.md
```

---

## 🧠 What I'd Add With More Time

- **Multi-timezone support** — detect caller's timezone from VAPI metadata
- **Recurring events** — "Schedule this every Tuesday at 10 AM"
- **Email confirmations** — send a summary email after booking
- **Multi-calendar support** — let users choose which calendar to book on
- **Analytics dashboard** — call logs, success rates, average call duration

---

Built by **Sai Teja** · [GitHub](https://github.com/YOUR_USERNAME) · 2026
