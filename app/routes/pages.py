"""
Page & API Routes
==================
Landing page, health check, and bookings feed.
"""

import datetime

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.config import settings
from app.calendar_service import calendar_service
from app.database import get_recent_bookings

router = APIRouter(tags=["pages"])


@router.get("/")
async def landing_page():
    """Branded landing page with embedded VAPI widget."""
    assistant_id = settings.VAPI_ASSISTANT_ID
    vapi_public_key = settings.VAPI_PUBLIC_KEY
    cal_connected = calendar_service.is_authenticated
    cal_dot = "green" if cal_connected else "yellow"
    cal_text = "Connected" if cal_connected else "Not Connected"

    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aria — Voice Scheduling Assistant</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Inter', -apple-system, sans-serif;
                background: #050505;
                color: #e8e8e8;
                min-height: 100vh;
                overflow-x: hidden;
            }}
            .bg-gradient {{
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: 
                    radial-gradient(ellipse at 20% 50%, rgba(88, 28, 135, 0.15) 0%, transparent 50%),
                    radial-gradient(ellipse at 80% 20%, rgba(15, 82, 186, 0.1) 0%, transparent 50%),
                    radial-gradient(ellipse at 50% 80%, rgba(88, 28, 135, 0.08) 0%, transparent 50%);
                z-index: 0;
            }}
            .container {{
                position: relative; z-index: 1; max-width: 900px;
                margin: 0 auto; padding: 60px 24px; text-align: center;
            }}
            .logo {{
                font-size: 0.85rem; font-weight: 500; letter-spacing: 3px;
                text-transform: uppercase; color: #8b5cf6; margin-bottom: 24px;
            }}
            h1 {{
                font-size: 3.2rem; font-weight: 700; line-height: 1.1; margin-bottom: 16px;
                background: linear-gradient(135deg, #e8e8e8 0%, #a78bfa 50%, #7c3aed 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
            }}
            .subtitle {{
                font-size: 1.15rem; color: #9ca3af; max-width: 500px;
                margin: 0 auto 48px; line-height: 1.6;
            }}
            .call-section {{ margin: 40px 0 60px; }}
            .call-btn {{
                display: inline-flex; align-items: center; gap: 12px;
                padding: 18px 48px; background: linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%);
                color: white; border: none; border-radius: 60px; font-size: 1.1rem;
                font-weight: 600; cursor: pointer; transition: all 0.3s ease;
                box-shadow: 0 0 40px rgba(124, 58, 237, 0.3);
            }}
            .call-btn:hover {{ transform: translateY(-2px); box-shadow: 0 0 60px rgba(124, 58, 237, 0.5); }}
            .call-btn:active {{ transform: translateY(0); }}
            .call-section {{ position: relative; }}
            .call-btn {{ position: relative; overflow: visible; }}
            .call-btn .icon {{ font-size: 1.3rem; }}
            .call-btn.active::before,
            .call-btn.active::after {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                border-radius: 60px;
                border: 2px solid rgba(220, 38, 38, 0.4);
                pointer-events: none;
            }}
            .call-btn.active::before {{
                animation: ripple 1.5s ease-out infinite;
            }}
            .call-btn.active::after {{
                border-color: rgba(220, 38, 38, 0.3);
                animation: ripple 1.5s ease-out infinite 0.5s;
            }}
            @keyframes ripple {{
                0% {{ transform: scale(1); opacity: 1; }}
                100% {{ transform: scale(1.6); opacity: 0; }}
            }}
            .call-btn.active {{
                background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
                box-shadow: 0 0 40px rgba(220, 38, 38, 0.3);
                animation: pulse-red 2s infinite;
            }}
            @keyframes pulse-red {{
                0%, 100% {{ box-shadow: 0 0 40px rgba(220, 38, 38, 0.3); }}
                50% {{ box-shadow: 0 0 60px rgba(220, 38, 38, 0.5); }}
            }}
            .call-status {{ margin-top: 16px; font-size: 0.9rem; color: #6b7280; min-height: 24px; }}
            .features {{
                display: grid; grid-template-columns: repeat(3, 1fr);
                gap: 20px; margin: 0 0 60px; text-align: left;
            }}
            .feature {{
                padding: 24px; background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.06); border-radius: 16px;
                transition: border-color 0.3s;
            }}
            .feature:hover {{ border-color: rgba(124, 58, 237, 0.3); }}
            .feature .icon {{ font-size: 1.5rem; margin-bottom: 12px; }}
            .feature h3 {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 8px; }}
            .feature p {{ font-size: 0.85rem; color: #6b7280; line-height: 1.5; }}
            .bookings-section {{ text-align: left; margin-top: 60px; }}
            .bookings-section h2 {{ font-size: 1.3rem; font-weight: 600; margin-bottom: 20px; color: #d1d5db; }}
            .booking-list {{ display: flex; flex-direction: column; gap: 8px; }}
            .booking-item {{
                display: flex; justify-content: space-between; align-items: center;
                padding: 16px 20px; background: rgba(255,255,255,0.02);
                border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; font-size: 0.9rem;
            }}
            .booking-item .name {{ font-weight: 500; color: #e8e8e8; }}
            .booking-item .title {{ color: #8b5cf6; }}
            .booking-item .time {{ color: #6b7280; font-size: 0.85rem; }}
            .empty-state {{ padding: 40px; text-align: center; color: #4b5563; font-size: 0.9rem; }}
            .status-bar {{
                margin-top: 60px; padding: 16px 24px; background: rgba(255,255,255,0.02);
                border: 1px solid rgba(255,255,255,0.05); border-radius: 12px;
                display: flex; justify-content: center; gap: 32px;
                font-size: 0.85rem; color: #6b7280;
            }}
            .status-item {{ display: flex; align-items: center; gap: 8px; }}
            .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
            .status-dot.green {{ background: #22c55e; }}
            .status-dot.yellow {{ background: #eab308; }}
            .footer {{ margin-top: 48px; font-size: 0.8rem; color: #374151; }}
            .footer a {{ color: #6b7280; text-decoration: none; }}
            .footer a:hover {{ color: #8b5cf6; }}
            @media (max-width: 768px) {{
                h1 {{ font-size: 2.2rem; }}
                .features {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <div class="bg-gradient"></div>
        <div class="container">
            <div class="logo">Vikara.ai</div>
            <h1>Meet Aria</h1>
            <p class="subtitle">
                Your voice-powered scheduling assistant. Just speak naturally —
                Aria will find the perfect time and book it on your calendar.
            </p>
            <div class="call-section">
                <button id="callBtn" class="call-btn" onclick="toggleCall()">
                    <span class="icon">🎙️</span>
                    <span id="btnText">Talk to Aria</span>
                </button>
                <div id="callStatus" class="call-status"></div>
            </div>
            <div class="features">
                <div class="feature">
                    <div class="icon">🧠</div>
                    <h3>Natural Conversation</h3>
                    <p>Powered by Claude — understands "next Tuesday afternoon" or "sometime this week"</p>
                </div>
                <div class="feature">
                    <div class="icon">📅</div>
                    <h3>Smart Scheduling</h3>
                    <p>Checks your calendar for conflicts and suggests available slots automatically</p>
                </div>
                <div class="feature">
                    <div class="icon">⚡</div>
                    <h3>Instant Booking</h3>
                    <p>Creates real Google Calendar events with one conversation — no forms, no clicks</p>
                </div>
            </div>
            <div class="features" style="margin-top: 0;">
                <div class="feature" style="text-align: center;">
                    <div class="icon">👆</div>
                    <h3>1. Click</h3>
                    <p>Hit "Talk to Aria" and allow microphone access</p>
                </div>
                <div class="feature" style="text-align: center;">
                    <div class="icon">🗣️</div>
                    <h3>2. Speak</h3>
                    <p>Tell Aria your name, preferred date, time, and meeting title</p>
                </div>
                <div class="feature" style="text-align: center;">
                    <div class="icon">✅</div>
                    <h3>3. Booked</h3>
                    <p>Aria confirms details and creates the event on your Google Calendar</p>
                </div>
            </div>
            <div class="bookings-section">
                <h2>📋 Recent Bookings</h2>
                <div id="bookingsList" class="booking-list">
                    <div class="empty-state">No bookings yet — be the first to talk to Aria!</div>
                </div>
            </div>
            <div class="status-bar">
                <div class="status-item">
                    <span class="status-dot green"></span> API Online
                </div>
                <div class="status-item">
                    <span class="status-dot {cal_dot}"></span> Calendar {cal_text}
                </div>
                <div class="status-item">
                    <span class="status-dot green"></span> Claude Sonnet 4.5
                </div>
            </div>
            <div class="footer">
                <p>Built by Sai Teja ·
                    <a href="/docs">API Docs</a> ·
                    <a href="/health">Health</a> ·
                    <a href="/api/bookings">Bookings API</a>
                </p>
            </div>
        </div>

        <script type="module">
            import Vapi from "https://cdn.jsdelivr.net/npm/@vapi-ai/web@latest/+esm";

            const publicKey = "{vapi_public_key}";
            const assistantId = "{assistant_id}";
            let vapi = null;
            let isCallActive = false;

            if (publicKey && publicKey !== "") {{
                vapi = new Vapi.default(publicKey);

                vapi.on("call-start", () => {{
                    isCallActive = true;
                    document.getElementById("callBtn").classList.add("active");
                    document.getElementById("btnText").textContent = "End Call";
                    document.getElementById("callStatus").textContent = "Connected — speak naturally";
                }});

                vapi.on("call-end", () => {{
                    isCallActive = false;
                    document.getElementById("callBtn").classList.remove("active");
                    document.getElementById("btnText").textContent = "Talk to Aria";
                    document.getElementById("callStatus").textContent = "Call ended";
                    loadBookings();
                }});

                vapi.on("error", (e) => {{
                    console.error("VAPI Error:", e);
                    document.getElementById("callStatus").textContent = "Connection error — please try again";
                }});
            }}

            window.toggleCall = function() {{
                if (!vapi) {{
                    document.getElementById("callStatus").textContent = "Voice widget not configured — test via VAPI Dashboard";
                    return;
                }}
                if (isCallActive) {{
                    vapi.stop();
                }} else {{
                    document.getElementById("callStatus").textContent = "Connecting...";
                    vapi.start(assistantId);
                }}
            }};

            const dingSound = new Audio("data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1tZWF1dnV0eH16f4GAgYKDg4SEhYWGh4eIiImJiouMjI2Oj5CRkZKTlJWVlpeYmJmam5ydnZ6foKChoqOkpaanp6mqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/v/+/f38+/r5+Pf29fTz8vHw7+7t7Ovq6ejn5uXk4+Lh4N/e3dzb2tnY19bV1NPS0dDPzs3My8rJyMfGxcTDwsHAv769vLu6ubm4t7a1tLOysbCvrq2sq6qpqKempaSjoqGgn56dnJuamZiXlpWUk5KRkI+OjYyLiomIh4aFhIOCgYB/fn18e3p5eHd2dXRzcnFwb25tbGtqaWhnZmVkY2JhYF9eXVxbWllYV1ZVVFNSUVBPTk1MS0pJSEdGRURDQkFAPz49PDs6OTg3NjU0MzIxMC8uLSwrKikoJyYlJCMiISAfHh0cGxoZGBcWFRQTEhEQDw4NDAsKCQgHBgUEAwIBAA==");
            let previousBookingCount = 0;

            async function loadBookings() {{
                try {{
                    const res = await fetch("/api/bookings");
                    const data = await res.json();
                    const list = document.getElementById("bookingsList");
                    if (data.bookings && data.bookings.length > 0) {{
                        list.innerHTML = data.bookings.map(b => `
                            <div class="booking-item">
                                <span class="name">${{b.caller_name}}</span>
                                <span class="title">${{b.meeting_title || 'Meeting'}}</span>
                                <span class="time">${{b.scheduled_date}} at ${{b.scheduled_time}}</span>
                            </div>
                        `).join("");
                        if (previousBookingCount > 0 && data.bookings.length > previousBookingCount) {{
                            dingSound.play().catch(() => {{}});
                        }}
                        previousBookingCount = data.bookings.length;
                    }}
                }} catch(e) {{
                    console.error("Failed to load bookings:", e);
                }}
            }}

            loadBookings();
            setInterval(loadBookings, 15000);
        </script>
    </body>
    </html>
    """)


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": "Aria",
        "calendar_connected": calendar_service.is_authenticated,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get("/api/bookings")
async def api_bookings(limit: int = Query(default=20, le=100)):
    """Recent bookings feed for the dashboard."""
    bookings = get_recent_bookings(limit)
    return {"bookings": bookings, "count": len(bookings)}