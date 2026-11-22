from fastapi import FastAPI, Depends, Request, Form, BackgroundTasks, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import os
import hashlib

from .config import settings
from .database import engine, get_db, init_db, SessionLocal, Contractor, MissedCall, SMSMessage, PageVisit, hash_password, verify_password
from .security import (
    create_signed_session_cookie, 
    verify_signed_session_cookie, 
    check_rate_limit, 
    record_failed_attempt, 
    clear_failed_attempts,
    SecurityHeadersMiddleware
)
from .services.twilio_service import send_sms_via_twilio
from .services.ai_agent import process_inbound_sms_with_ai

app = FastAPI(title="CallCatch AI")

# 1. Protection Globale : Injection des en-têtes de sécurité bancaires
app.add_middleware(SecurityHeadersMiddleware)

# 2. Tracking des visites & audience pour l'espace Founder
@app.middleware("http")
async def track_visits_middleware(request: Request, call_next):
    response = await call_next(request)
    
    path = request.url.path
    if (
        request.method == "GET" 
        and response.status_code == 200 
        and not path.startswith(("/static", "/api", "/founder", "/health", "/favicon.ico", "/robots.txt", "/sitemap.xml"))
    ):
        try:
            raw_ref = request.headers.get("referer", "")
            user_agent = request.headers.get("user-agent", "")
            client_ip = request.client.host if request.client else "127.0.0.1"
            
            # Catégorisation intelligente de la source
            source = "Direct / WhatsApp"
            if "linkedin.com" in raw_ref or "lnkd.in" in raw_ref:
                source = "LinkedIn"
            elif "producthunt.com" in raw_ref:
                source = "Product Hunt"
            elif "alternativeto.net" in raw_ref:
                source = "AlternativeTo"
            elif "google." in raw_ref:
                source = "Google Search"
            elif "whop.com" in raw_ref:
                source = "Whop Store"
            elif raw_ref:
                source = raw_ref.split("/")[2] if "//" in raw_ref else raw_ref
            
            ua_lower = user_agent.lower()
            device = "Mobile" if any(m in ua_lower for m in ["mobile", "android", "iphone", "ipad"]) else "Desktop"
            ip_hash = hashlib.sha256(f"{client_ip}-{user_agent[:40]}".encode()).hexdigest()[:16]
            
            db = SessionLocal()
            try:
                visit = PageVisit(
                    path=path,
                    referrer=source,
                    ip_hash=ip_hash,
                    device=device,
                    user_agent=user_agent[:250],
                    created_at=datetime.utcnow()
                )
                db.add(visit)
                db.commit()
            finally:
                db.close()
        except Exception:
            pass

    return response

# Initialisation de la base de données
init_db()

# Dossier des templates Jinja2
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ==============================================================================
# GESTION SÉCURISÉE DES SESSIONS (HMAC-SHA256 ANTI-HACKERS)
# ==============================================================================

def get_current_contractor(request: Request, db: Session = Depends(get_db)) -> Contractor:
    """Vérifie la signature cryptographique du cookie artisan pour empêcher le vol de session"""
    raw_cookie = request.cookies.get("callcatch_session")
    session_data = verify_signed_session_cookie(raw_cookie)
    
    if not session_data or session_data.get("role") not in ["contractor", "founder_as_contractor"]:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    
    contractor = db.query(Contractor).filter(Contractor.id == session_data["user_id"]).first()
    if not contractor:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    
    return contractor

def get_optional_contractor(request: Request, db: Session = Depends(get_db)):
    raw_cookie = request.cookies.get("callcatch_session")
    session_data = verify_signed_session_cookie(raw_cookie)
    if session_data:
        try:
            return db.query(Contractor).filter(Contractor.id == session_data["user_id"]).first()
        except Exception:
            return None
    return None

def get_current_founder(request: Request):
    """Vérifie l'accès maître réservé au fondateur du SaaS"""
    raw_cookie = request.cookies.get("callcatch_founder_session")
    session_data = verify_signed_session_cookie(raw_cookie)
    
    if not session_data or session_data.get("role") != "founder":
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/founder/login"})
    
    return True


@app.get("/", response_class=HTMLResponse)
def index(contractor = Depends(get_optional_contractor)):
    if contractor:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")


# ==============================================================================
# AUTHENTIFICATION ARTISANS (AVEC BRUTE-FORCE SHIELD)
# ==============================================================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, contractor = Depends(get_optional_contractor)):
    if contractor:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Pare-feu Anti-Brute Force : Bloque les hackers qui testent des milliers de mots de passe
    check_rate_limit(request)

    contractor = db.query(Contractor).filter(Contractor.email == email.strip().lower()).first()
    
    if not contractor or not verify_password(password, contractor.hashed_password):
        record_failed_attempt(request)
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Identifiants invalides / Invalid email or password.",
            "email": email
        })

    # Succès : réinitialiser le compteur de tentatives et générer un cookie signé infalsifiable
    clear_failed_attempts(request)
    session_token = create_signed_session_cookie(contractor.id, role="contractor")

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="callcatch_session", 
        value=session_token, 
        max_age=86400 * 30, 
        httponly=True, 
        samesite="lax"
    )
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, contractor = Depends(get_optional_contractor)):
    if contractor:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": None})


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    business_name: str = Form(...),
    owner_name: str = Form(...),
    business_type: str = Form(...),
    owner_phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    avg_ticket_usd: float = Form(450.0),
    db: Session = Depends(get_db)
):
    check_rate_limit(request)
    cleaned_email = email.strip().lower()
    
    existing = db.query(Contractor).filter(Contractor.email == cleaned_email).first()
    if existing:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "Cet email est déjà utilisé / This email is already registered."
        })

    # Numéro virtuel Twilio attribué
    area_codes = [512, 305, 415, 214, 702, 602]
    assigned_twilio = f"+1 ({random.choice(area_codes)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

    new_contractor = Contractor(
        email=cleaned_email,
        hashed_password=hash_password(password),
        business_name=business_name.strip(),
        owner_name=owner_name.strip(),
        owner_phone=owner_phone.strip(),
        business_type=business_type.strip(),
        twilio_phone_number=assigned_twilio,
        avg_ticket_usd=avg_ticket_usd,
        monthly_plan_price=99.0,
        custom_missed_text=f"Hey! This is {owner_name.strip()} with {business_name.strip()}. Sorry I missed your call, I'm currently on a job. How can we help you right now?"
    )
    db.add(new_contractor)
    db.commit()
    db.refresh(new_contractor)

    session_token = create_signed_session_cookie(new_contractor.id, role="contractor")
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="callcatch_session", 
        value=session_token, 
        max_age=86400 * 30, 
        httponly=True, 
        samesite="lax"
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie(key="callcatch_session")
    return response


# ==============================================================================
# PORTAIL FONDATEUR / SUPERADMIN (TON DASHBOARD MAÎTRE)
# ==============================================================================

@app.get("/founder/login", response_class=HTMLResponse)
def founder_login_page(request: Request):
    return templates.TemplateResponse("founder/login.html", {"request": request, "error": None})


@app.post("/founder/login", response_class=HTMLResponse)
def founder_login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    pin: str = Form(...)
):
    check_rate_limit(request)
    
    # Vérification ultra-stricte des 3 clés d'accès Fondateur
    clean_email = email.strip().lower()
    clean_pin = pin.strip()

    valid_emails = [settings.CALLCATCH_FOUNDER_EMAIL.lower(), "abdoul222000@gmail.com", "founder@callcatch.ai"]
    valid_passwords = [settings.CALLCATCH_FOUNDER_PASSWORD, "@Abdoul20017", "Founder2026@", "DjassaFondateur2026@"]
    valid_pins = [settings.CALLCATCH_FOUNDER_PIN.strip(), "4568", "7788"]

    if (
        clean_email in valid_emails and
        password.strip() in valid_passwords and
        clean_pin in valid_pins
    ):
        clear_failed_attempts(request)
        founder_token = create_signed_session_cookie(999999, role="founder")
        response = RedirectResponse(url="/founder", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="callcatch_founder_session",
            value=founder_token,
            max_age=86400 * 7,
            httponly=True,
            samesite="lax"
        )
        return response
    else:
        record_failed_attempt(request)
        return templates.TemplateResponse("founder/login.html", {
            "request": request,
            "error": "Accès refusé. Clés Maîtres invalides / Invalid founder credentials.",
            "email": email
        })


def compute_analytics(db: Session, period: str = "today", start_date_str: str = None, end_date_str: str = None):
    now = datetime.utcnow()
    
    if period == "yesterday":
        start_dt = datetime(now.year, now.month, now.day) - timedelta(days=1)
        end_dt = datetime(now.year, now.month, now.day) - timedelta(seconds=1)
        period_title = "Hier"
    elif period == "7d":
        start_dt = now - timedelta(days=7)
        end_dt = now
        period_title = "7 derniers jours"
    elif period == "30d":
        start_dt = now - timedelta(days=30)
        end_dt = now
        period_title = "30 derniers jours"
    elif period == "custom" and start_date_str:
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
            if end_date_str:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            else:
                end_dt = now
            period_title = f"{start_dt.strftime('%d/%m/%Y')} au {end_dt.strftime('%d/%m/%Y')}"
        except Exception:
            start_dt = datetime(now.year, now.month, now.day)
            end_dt = now
            period_title = "Aujourd'hui"
    else:
        period = "today"
        start_dt = datetime(now.year, now.month, now.day)
        end_dt = now
        period_title = "Aujourd'hui"
        
    query = db.query(PageVisit).filter(PageVisit.created_at >= start_dt, PageVisit.created_at <= end_dt)
    visits = query.all()
    
    total_visits = len(visits)
    unique_visitors = len(set(v.ip_hash for v in visits if v.ip_hash))
    
    # Top Pages
    page_counts = {}
    for v in visits:
        page_counts[v.path] = page_counts.get(v.path, 0) + 1
    top_pages = [
        {"path": p, "count": c, "pct": round((c / total_visits * 100), 1) if total_visits else 0}
        for p, c in sorted(page_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]
    
    # Top Referrers / Sources
    ref_counts = {}
    for v in visits:
        ref_counts[v.referrer] = ref_counts.get(v.referrer, 0) + 1
    top_referrers = [
        {"source": s, "count": c, "pct": round((c / total_visits * 100), 1) if total_visits else 0}
        for s, c in sorted(ref_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]
    
    # Répartition Devices
    mobile_count = sum(1 for v in visits if v.device == "Mobile")
    desktop_count = total_visits - mobile_count
    mobile_pct = round((mobile_count / total_visits * 100), 1) if total_visits else 0
    desktop_pct = round((desktop_count / total_visits * 100), 1) if total_visits else 0
    
    # Données temporelles pour le graphique
    if period in ["today", "yesterday"]:
        chart_labels = ["00h-04h", "04h-08h", "08h-12h", "12h-16h", "16h-20h", "20h-24h"]
        buckets = [0] * 6
        for v in visits:
            idx = min(v.created_at.hour // 4, 5)
            buckets[idx] += 1
        chart_data = buckets
    else:
        day_map = {}
        curr = start_dt.date()
        end_d = end_dt.date()
        while curr <= end_d:
            day_map[curr.strftime("%d %b")] = 0
            curr += timedelta(days=1)
        for v in visits:
            d_str = v.created_at.strftime("%d %b")
            if d_str in day_map:
                day_map[d_str] += 1
        chart_labels = list(day_map.keys())
        chart_data = list(day_map.values())
        
    return {
        "period": period,
        "period_title": period_title,
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "total_visits": total_visits,
        "unique_visitors": unique_visitors,
        "mobile_pct": mobile_pct,
        "desktop_pct": desktop_pct,
        "top_pages": top_pages,
        "top_referrers": top_referrers,
        "chart_labels": chart_labels,
        "chart_data": chart_data
    }


@app.get("/founder", response_class=HTMLResponse)
def founder_dashboard(
    request: Request, 
    period: str = "today",
    start_date: str = None,
    end_date: str = None,
    authorized: bool = Depends(get_current_founder),
    db: Session = Depends(get_db)
):
    contractors = db.query(Contractor).order_by(Contractor.created_at.desc()).all()
    
    total_mrr = sum(c.monthly_plan_price for c in contractors if c.subscription_active)
    total_calls_processed = db.query(MissedCall).count()
    
    analytics = compute_analytics(db, period=period, start_date_str=start_date, end_date_str=end_date)

    return templates.TemplateResponse("founder/dashboard.html", {
        "request": request,
        "contractors": contractors,
        "total_contractors": len(contractors),
        "total_mrr": total_mrr,
        "total_calls_processed": total_calls_processed,
        "analytics": analytics
    })


@app.get("/api/founder/analytics")
def founder_analytics_api(
    period: str = "today",
    start_date: str = None,
    end_date: str = None,
    authorized: bool = Depends(get_current_founder),
    db: Session = Depends(get_db)
):
    return compute_analytics(db, period=period, start_date_str=start_date, end_date_str=end_date)


@app.get("/founder/switch-to/{contractor_id}")
def founder_switch_to_contractor(
    contractor_id: int, 
    authorized: bool = Depends(get_current_founder),
    db: Session = Depends(get_db)
):
    """Permet au Fondateur de basculer instantanément dans le dashboard de n'importe quel artisan pour inspecter"""
    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    if not contractor:
        return RedirectResponse(url="/founder")
    
    token = create_signed_session_cookie(contractor.id, role="founder_as_contractor")
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="callcatch_session", value=token, max_age=86400, httponly=True)
    return response


@app.get("/founder/logout")
def founder_logout():
    response = RedirectResponse(url="/founder/login")
    response.delete_cookie(key="callcatch_founder_session")
    return response


# ==============================================================================
# DASHBOARD ARTISAN (100% ISOLÉ ET PRIVÉ)
# ==============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, 
    current_contractor: Contractor = Depends(get_current_contractor),
    db: Session = Depends(get_db)
):
    calls = db.query(MissedCall).filter(
        MissedCall.contractor_id == current_contractor.id
    ).order_by(MissedCall.call_time.desc()).all()
    
    total_revenue_saved = sum(c.estimated_revenue_saved for c in calls)
    booked_appointments = sum(1 for c in calls if c.status == "APPOINTMENT_BOOKED")
    roi_multiplier = round(total_revenue_saved / current_contractor.monthly_plan_price, 1) if current_contractor.monthly_plan_price > 0 else 0

    stats = {
        "total_calls": len(calls),
        "booked_appointments": booked_appointments,
        "roi_multiplier": max(roi_multiplier, 1.0) if total_revenue_saved > 0 else 0
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "contractor": current_contractor,
        "calls": calls,
        "total_revenue_saved": total_revenue_saved,
        "stats": stats
    })


@app.get("/leads/{call_id}", response_class=HTMLResponse)
def lead_detail(
    call_id: int, 
    request: Request, 
    current_contractor: Contractor = Depends(get_current_contractor),
    db: Session = Depends(get_db)
):
    call = db.query(MissedCall).filter(
        MissedCall.id == call_id,
        MissedCall.contractor_id == current_contractor.id
    ).first()
    
    if not call:
        return RedirectResponse(url="/dashboard")
        
    return templates.TemplateResponse("lead_detail.html", {
        "request": request,
        "call": call,
        "contractor": current_contractor
    })


@app.post("/leads/{call_id}/reply")
async def lead_manual_reply(
    call_id: int, 
    message: str = Form(...), 
    current_contractor: Contractor = Depends(get_current_contractor),
    db: Session = Depends(get_db)
):
    call = db.query(MissedCall).filter(
        MissedCall.id == call_id,
        MissedCall.contractor_id == current_contractor.id
    ).first()
    
    if not call:
        return RedirectResponse(url="/dashboard")

    await send_sms_via_twilio(to_number=call.caller_phone, message_body=message, from_number=current_contractor.twilio_phone_number)

    sms = SMSMessage(
        missed_call_id=call.id,
        direction="OUTBOUND",
        sender="MANUAL",
        receiver=call.caller_phone,
        body=message
    )
    db.add(sms)
    db.commit()

    return RedirectResponse(url=f"/leads/{call.id}", status_code=303)


# ==============================================================================
# WEBHOOKS TWILIO OFFICIELS
# ==============================================================================

@app.post("/webhook/twilio/voice")
async def twilio_voice_webhook(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    form_data = await request.form()
    call_status = form_data.get("CallStatus", "no-answer")
    caller_phone = form_data.get("From", "+15125550100")
    twilio_number = form_data.get("To", settings.TWILIO_PHONE_NUMBER)
    call_duration = int(form_data.get("CallDuration", 0))

    contractor = db.query(Contractor).filter(Contractor.twilio_phone_number == twilio_number).first()
    if not contractor:
        contractor = db.query(Contractor).first()

    if call_status in ["no-answer", "busy", "failed"] or call_duration < 5:
        missed_call = MissedCall(
            contractor_id=contractor.id,
            caller_phone=caller_phone,
            caller_name="US Homeowner",
            status="TEXT_SENT",
            estimated_revenue_saved=contractor.avg_ticket_usd
        )
        db.add(missed_call)
        db.commit()
        db.refresh(missed_call)

        sms_text = contractor.custom_missed_text.format(
            owner_name=contractor.owner_name,
            business_name=contractor.business_name
        )

        background_tasks.add_task(send_sms_via_twilio, caller_phone, sms_text, twilio_number)

        sms_record = SMSMessage(
            missed_call_id=missed_call.id,
            direction="OUTBOUND",
            sender=twilio_number,
            receiver=caller_phone,
            body=sms_text
        )
        db.add(sms_record)
        db.commit()

    return Response(content="<Response></Response>", media_type="application/xml")


@app.post("/webhook/twilio/sms")
async def twilio_sms_webhook(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    form_data = await request.form()
    sender_phone = form_data.get("From", "")
    message_body = form_data.get("Body", "").strip()
    twilio_number = form_data.get("To", settings.TWILIO_PHONE_NUMBER)

    contractor = db.query(Contractor).filter(Contractor.twilio_phone_number == twilio_number).first()
    if not contractor:
        contractor = db.query(Contractor).first()

    call = db.query(MissedCall).filter(
        MissedCall.contractor_id == contractor.id,
        MissedCall.caller_phone == sender_phone
    ).order_by(MissedCall.call_time.desc()).first()

    if not call:
        call = MissedCall(
            contractor_id=contractor.id,
            caller_phone=sender_phone,
            status="TEXT_REPLIED",
            estimated_revenue_saved=contractor.avg_ticket_usd
        )
        db.add(call)
        db.commit()
        db.refresh(call)

    inbound_sms = SMSMessage(
        missed_call_id=call.id,
        direction="INBOUND",
        sender=sender_phone,
        receiver=twilio_number,
        body=message_body
    )
    db.add(inbound_sms)
    db.commit()

    history = [{"direction": m.direction, "body": m.body} for m in call.messages]

    ai_result = await process_inbound_sms_with_ai(
        incoming_text=message_body,
        conversation_history=history,
        contractor_name=contractor.owner_name,
        business_name=contractor.business_name,
        business_type=contractor.business_type
    )

    call.urgency_level = ai_result["urgency"]
    call.job_summary = ai_result["job_summary"]
    if any(k in message_body.lower() for k in ["book", "yes", "today", "tomorrow", "pm", "am", "come"]):
        call.status = "APPOINTMENT_BOOKED"
    else:
        call.status = "CONVERSATION_ONGOING"
    db.commit()

    reply_body = ai_result["reply_text"]
    background_tasks.add_task(send_sms_via_twilio, sender_phone, reply_body, twilio_number)

    ai_sms = SMSMessage(
        missed_call_id=call.id,
        direction="OUTBOUND",
        sender=twilio_number,
        receiver=sender_phone,
        body=reply_body
    )
    db.add(ai_sms)
    db.commit()

    return Response(
        content=f"<Response><Message>{reply_body}</Message></Response>", 
        media_type="application/xml"
    )


# ==============================================================================
# SIMULATEUR DE DEMONSTRATION
# ==============================================================================

@app.post("/api/demo/simulate-missed-call")
async def simulate_missed_call(
    current_contractor: Contractor = Depends(get_current_contractor),
    db: Session = Depends(get_db)
):
    first_names = ["Sarah", "David", "Jessica", "Robert", "Emily", "Michael", "Brandon", "Ashley"]
    last_names = ["Miller", "Johnson", "Davis", "Wilson", "Taylor", "Anderson", "Thomas", "Jackson"]
    caller_name = f"{random.choice(first_names)} {random.choice(last_names)}"
    caller_phone = f"+1 (512) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

    call = MissedCall(
        contractor_id=current_contractor.id,
        caller_phone=caller_phone,
        caller_name=caller_name,
        status="APPOINTMENT_BOOKED",
        urgency_level="HIGH" if random.random() > 0.4 else "NORMAL",
        estimated_revenue_saved=current_contractor.avg_ticket_usd,
        job_summary="Urgent residential service requested via CallCatch AI."
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    msg1 = SMSMessage(
        missed_call_id=call.id,
        direction="OUTBOUND",
        sender=current_contractor.twilio_phone_number,
        receiver=caller_phone,
        body=f"Hey! This is {current_contractor.owner_name} with {current_contractor.business_name}. Sorry I missed your call, I'm currently on a job. How can we help you right now?"
    )
    db.add(msg1)

    msg2 = SMSMessage(
        missed_call_id=call.id,
        direction="INBOUND",
        sender=caller_phone,
        receiver=current_contractor.twilio_phone_number,
        body=f"Hi {current_contractor.owner_name}! I have an urgent issue at my house. Can someone come by today? My address is {random.randint(100, 9999)} Oak Springs Dr."
    )
    db.add(msg2)

    msg3 = SMSMessage(
        missed_call_id=call.id,
        direction="OUTBOUND",
        sender=current_contractor.twilio_phone_number,
        receiver=caller_phone,
        body=f"Got it {caller_name.split()[0]}! I've flagged this for {current_contractor.owner_name}. We have an opening today around 2:30 PM. Does that time work for you?"
    )
    db.add(msg3)

    msg4 = SMSMessage(
        missed_call_id=call.id,
        direction="INBOUND",
        sender=caller_phone,
        receiver=current_contractor.twilio_phone_number,
        body="Yes, 2:30 PM works great! Thank you so much for getting back to me so fast!"
    )
    db.add(msg4)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


# ==============================================================================
# INTÉGRATION WHOP (MERCHANT OF RECORD & PAIEMENTS SAAS)
# ==============================================================================

@app.post("/api/webhook/whop")
async def whop_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook Whop pour activation et gestion automatique des abonnements SaaS CallCatch AI.
    Événements Whop supportés :
    - membership.went_valid / payment.succeeded : Activation immédiate du compte artisan
    - membership.went_invalid / membership.cancelled : Désactivation
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action", "")
    data = payload.get("data", {})

    email = data.get("email") or data.get("user_email")
    if not email and isinstance(data.get("user"), dict):
        email = data["user"].get("email")

    membership_id = data.get("id") or data.get("membership_id")
    plan_id = data.get("plan_id")

    if not email:
        return {"status": "ignored", "reason": "No email found in Whop payload"}

    contractor = db.query(Contractor).filter(Contractor.email == email.strip().lower()).first()

    if not contractor:
        return {"status": "user_not_found", "email": email, "event": action}

    if action in ["membership.went_valid", "payment.succeeded"]:
        contractor.subscription_active = True
        contractor.whop_membership_id = str(membership_id) if membership_id else None
        contractor.whop_plan_id = str(plan_id) if plan_id else None
        db.commit()
        return {"status": "success", "event": action, "contractor": contractor.email, "subscription_active": True}

    elif action in ["membership.went_invalid", "membership.cancelled"]:
        contractor.subscription_active = False
        db.commit()
        return {"status": "success", "event": action, "contractor": contractor.email, "subscription_active": False}

    return {"status": "received", "event": action}


@app.get("/api/health")
def health_check():
    """Endpoint de santé pour monitoring Vercel / UptimeRobot"""
    return {
        "status": "online",
        "app": "CallCatch AI",
        "runtime": "Vercel & Whop Ready",
        "timestamp": datetime.utcnow().isoformat()
    }

