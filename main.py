from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import sqlite3, os, uuid, shutil, zipfile, json, base64
from datetime import datetime, date, timedelta
from typing import Optional, List
from PIL import Image
import pillow_heif
from pdf2image import convert_from_path, pdfinfo_from_path
from passlib.context import CryptContext
from jose import JWTError, jwt

app = FastAPI(title='Study Helper Pro V1.2.7')
pillow_heif.register_heif_opener()

# Security & Auth
SECRET_KEY = "66Lennoxwyr_Pro_Secret" # In production, this should be an env var
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

DB_PATH = '/app/data/study_pro.db'
UPLOAD_DIR = '/app/static/uploads'
TEMP_DIR = '/tmp/study_helper_pro'
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app.mount('/static', StaticFiles(directory='/app/static'), name='static')
templates = Jinja2Templates(directory='/app/templates')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Users & Auth
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT "user",
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Original tables with user_id
    c.execute('''CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT NOT NULL, 
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        UNIQUE(name, user_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS papers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT NOT NULL, 
        subject_id INTEGER, 
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        subject_id INTEGER, 
        paper_id INTEGER, 
        user_id INTEGER,
        question_text TEXT, 
        question_type TEXT NOT NULL, 
        option_a TEXT, option_b TEXT, option_c TEXT, option_d TEXT, 
        correct_answer TEXT, 
        source TEXT, 
        wrong_count INTEGER DEFAULT 0, 
        is_difficult BOOLEAN DEFAULT 0, 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE, 
        FOREIGN KEY (paper_id) REFERENCES papers (id) ON DELETE SET NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS question_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        question_id INTEGER, 
        path TEXT NOT NULL, 
        image_type TEXT NOT NULL, 
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS study_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER,
        question_id INTEGER, 
        is_correct BOOLEAN, 
        studied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )''')

    # Paper Distribution (Assignments)
    c.execute('''CREATE TABLE IF NOT EXISTS paper_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER,
        user_id INTEGER,
        assigned_by INTEGER,
        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        UNIQUE(paper_id, user_id)
    )''')
    
    # Per-user Question Status (Fix for distributed papers)
    c.execute('''CREATE TABLE IF NOT EXISTS user_question_status (
        user_id INTEGER,
        question_id INTEGER,
        wrong_count INTEGER DEFAULT 0,
        is_difficult BOOLEAN DEFAULT 0,
        PRIMARY KEY (user_id, question_id),
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
    )''')
    
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('app_name', 'Study Helper Pro')")
    
    # Default Admin
    admin_hash = pwd_context.hash("admin123")
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", admin_hash, "admin"))
    
    # V1.3.4 Auto-Migration: Ensure history_wrong exists
    try:
        # Check if column exists to avoid error logging (though add column handles it gracefully usually)
        c.execute("SELECT history_wrong FROM user_question_status LIMIT 1")
    except sqlite3.OperationalError:
        print("V1.3.4: Adding history_wrong column...")
        try:
            c.execute("ALTER TABLE user_question_status ADD COLUMN history_wrong INTEGER DEFAULT 0")
            c.execute("UPDATE user_question_status SET history_wrong = 1 WHERE wrong_count > 0")
            print("V1.3.4: Migration Complete (Column Added & Backfilled)")
        except Exception as e:
            print(f"V1.3.4 Migration Failed: {e}")

    conn.commit()
    conn.close()

init_db()

# Auth Helpers
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token: return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: return None
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        return dict(user) if user else None
    except JWTError: return None

def auth_required(func):
    async def wrapper(*args, **kwargs):
        request = kwargs.get('request')
        user = await get_current_user(request)
        if not user: return RedirectResponse("/login", status_code=303)
        kwargs['user'] = user
        return await func(*args, **kwargs)
    return wrapper

def get_app_name():
    conn = get_db()
    res = conn.execute("SELECT value FROM config WHERE key='app_name'").fetchone()
    conn.close()
    return res[0] if res else "Study Helper Pro"

def get_question_data(conn, q_id, user_id=None):
    if user_id:
        q = conn.execute('''
            SELECT q.*, 
                   COALESCE(uqs.wrong_count, 0) as user_wrong_count,
                   COALESCE(uqs.history_wrong, 0) as user_history_wrong,
                   COALESCE(uqs.is_difficult, 0) as user_is_difficult,
                   uqs.user_id as uqs_user_id
            FROM questions q 
            LEFT JOIN paper_assignments pa ON q.paper_id = pa.paper_id AND pa.user_id = ?
            LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ?
            WHERE q.id = ? AND (q.user_id = ? OR pa.user_id = ?)
        ''', (user_id, user_id, q_id, user_id, user_id)).fetchone()
    else:
        q = conn.execute("SELECT * FROM questions WHERE id = ?", (q_id,)).fetchone()
    
    if not q: return None
    d = dict(q)
    # Overwrite with per-user stats if available
    if 'user_wrong_count' in d:
        d['wrong_count'] = d['user_wrong_count']
        d['history_wrong'] = d['user_history_wrong']
        d['is_difficult'] = d['user_is_difficult']
        d['has_record'] = d['uqs_user_id'] is not None
    
    d['q_imgs'] = [f"/static/uploads/{os.path.basename(r['path'])}" for r in conn.execute('SELECT path FROM question_images WHERE question_id = ? AND image_type = "question"', (q_id,)).fetchall()]
    d['a_imgs'] = [f"/static/uploads/{os.path.basename(r['path'])}" for r in conn.execute('SELECT path FROM question_images WHERE question_id = ? AND image_type = "answer"', (q_id,)).fetchall()]
    return d

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app_name": get_app_name()})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not user or not pwd_context.verify(password, user['password_hash']):
        return RedirectResponse("/login?error=invalid", status_code=303)
    token = create_access_token(data={"sub": username})
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.get("/", response_class=HTMLResponse)
@app.head("/", response_class=HTMLResponse)
async def index(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); c = conn.cursor()
    # Total count: owned + assigned
    total_q = c.execute('''
        SELECT COUNT(DISTINCT q.id) FROM questions q 
        LEFT JOIN paper_assignments pa ON q.paper_id = pa.paper_id AND pa.user_id = ?
        WHERE q.user_id = ? OR pa.user_id = ?
    ''', (user['id'], user['id'], user['id'])).fetchone()[0]
    
    today_q = c.execute("SELECT COUNT(*) FROM study_records WHERE user_id = ? AND date(studied_at) = date('now', 'localtime')", (user['id'],)).fetchone()[0]
    recs = c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as ok FROM study_records WHERE user_id = ?", (user['id'],)).fetchone()
    acc = round(recs['ok'] / recs['total'] * 100, 1) if recs['total'] and recs['total'] > 0 else 0
    
    # Subjects list: owned subjects OR subjects containing assigned papers
    subs = c.execute('''
        SELECT s.*, 
            (SELECT COUNT(DISTINCT q.id) FROM questions q 
             WHERE q.subject_id = s.id AND q.user_id = ?
            ) as q_count,
            (SELECT COUNT(DISTINCT uqs.question_id) 
             FROM user_question_status uqs 
             JOIN questions q ON uqs.question_id = q.id 
             WHERE q.subject_id = s.id AND uqs.user_id = ? AND uqs.wrong_count > 0
            ) as wrong_count
        FROM subjects s 
        WHERE s.user_id = ?
        ORDER BY s.name
    ''', (user['id'], user['id'], user['id'])).fetchall()
    
    distributed = c.execute('''SELECT p.*, s.name as s_name FROM paper_assignments pa 
                                JOIN papers p ON pa.paper_id = p.id 
                                JOIN subjects s ON p.subject_id = s.id
                                WHERE pa.user_id = ?''', (user['id'],)).fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "app_name": get_app_name(), "user": user, "subjects": [dict(s) for s in subs], "distributed": [dict(p) for p in distributed], "stats": {"total": total_q, "today": today_q, "accuracy": acc}})

@app.post("/subject/add")
async def add_subject(request: Request, name: str = Form(...)):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); conn.execute("INSERT OR IGNORE INTO subjects (name, user_id) VALUES (?, ?)", (name.strip(), user['id'])); conn.commit(); conn.close()
    return RedirectResponse("/", status_code=303)

@app.post("/subject/delete/{sid}")
async def delete_subject(request: Request, sid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); conn.execute("DELETE FROM subjects WHERE id = ? AND user_id = ?", (sid, user['id']))
    conn.commit(); conn.close()
    return RedirectResponse("/settings", status_code=303)

@app.get("/subject/{sid}", response_class=HTMLResponse)
async def subject_detail(request: Request, sid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    s = conn.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (sid, user['id'])).fetchone()
    if not s: conn.close(); raise HTTPException(404)
    # Filter: Pure Bank (Owned & No Paper) OR Active Errors (from any source)
    # V1.3.1 Logic + V1.3.3 Persistent Error
    # Show owned questions OR (paper questions IF they have wrong/difficult/history status)
    qs = conn.execute('''
        SELECT q.*, uqs.wrong_count, uqs.is_difficult, uqs.history_wrong 
        FROM questions q
        LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ?
        WHERE q.subject_id = ? 
        AND (
            (q.user_id = ? AND q.paper_id IS NULL) 
            OR 
            (uqs.wrong_count > 0 OR uqs.is_difficult = 1 OR uqs.history_wrong = 1)
        )
        ORDER BY q.created_at DESC
    ''', (user['id'], sid, user['id'])).fetchall()
    
    # V1.3.5: Calculate Stats
    stats = {
        "total": len(qs),
        "wrong": sum(1 for q in qs if q['wrong_count'] > 0 or q['history_wrong'] == 1),
        "difficult": sum(1 for q in qs if q['is_difficult'] == 1)
    }

    conn.close()
    return templates.TemplateResponse("subject.html", {"request": request, "app_name": get_app_name(), "user": user, "subject": dict(s), "questions": [dict(q) for q in qs], "stats": stats})

async def save_img(f: UploadFile) -> str:
    ext = os.path.splitext(f.filename)[1].lower(); uid = uuid.uuid4().hex; img_name = f"{uid}.webp"; tmp = f"/tmp/{uid}{ext}"
    with open(tmp, "wb") as out: shutil.copyfileobj(f.file, out)
    img = Image.open(tmp)
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except: pass
    if max(img.size) > 1800:
        ratio = 1800 / float(max(img.size))
        new_size = tuple([int(x * ratio) for x in img.size])
        img = img.resize(new_size, Image.LANCZOS)
    img.convert('RGB').save(os.path.join(UPLOAD_DIR, img_name), "WEBP", quality=80)
    os.remove(tmp)
    return img_name

@app.get("/subject/{sid}/add", response_class=HTMLResponse)
async def add_q_page(request: Request, sid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    s = conn.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (sid, user['id'])).fetchone()
    conn.close()
    if not s: raise HTTPException(404)
    return templates.TemplateResponse("add.html", {"request": request, "app_name": get_app_name(), "user": user, "subject": dict(s)})

@app.post("/subject/{sid}/add")
async def add_q(request: Request, sid: int, q_text: str = Form(...), q_type: str = Form(...), ans: str = Form(...), a: Optional[str] = Form(None), b: Optional[str] = Form(None), c: Optional[str] = Form(None), d: Optional[str] = Form(None), source: Optional[str] = Form(None), q_images: List[UploadFile] = File([]), a_images: List[UploadFile] = File([]), paper_id: Optional[int] = Form(None)):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (sid, paper_id, user['id'], q_text, q_type, ans, a, b, c, d, source))
    qid = cur.lastrowid
    for f in q_images:
        if f.filename:
            p = await save_img(f)
            cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, p, 'question'))
    for f in a_images:
        if f.filename:
            p = await save_img(f)
            cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, p, 'answer'))
    conn.commit(); conn.close()
    return RedirectResponse(f"/paper/{paper_id}" if paper_id else f"/subject/{sid}", status_code=303)

@app.get("/subject/{sid}/study")
async def study(request: Request, sid: int, mode: str = "normal", qtype: str = "all"):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    
    # Get subject name
    s = conn.execute("SELECT * FROM subjects WHERE id = ?", (sid,)).fetchone()
    if not s: conn.close(); raise HTTPException(404)

    # Base Query: Questions in this subject
    query = '''
        SELECT q.id FROM questions q 
        LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ?
        LEFT JOIN paper_assignments pa ON q.paper_id = pa.paper_id AND pa.user_id = ?
        WHERE q.subject_id = ? 
    '''
    params = [user['id'], user['id'], sid]
    
    # 1. Access Control: Must be Owned OR Assigned
    # (Simplified: if it's in the subject and accessed via this route, we filter by what user CAN see)
    # But wait, we need to respect the "Pure Bank" vs "Paper" distinction?
    # User wants:
    # 1. All Loop (全部普刷): All Accessable (Owned + Assigned)
    # 2. Error (错题): All Wrong
    # 3. Difficult (难点): All Difficult
    
    access_condition = " AND (q.user_id = ? OR pa.user_id = ?)"
    params.extend([user['id'], user['id']])
    query += access_condition
    
    # 2. Mode Filter
    if mode == "error": 
        # Error mode should probably focus on CURRENTLY wrong, but maybe user wants historical too?
        # User said "1.刷完的题没有错... 错会取消". 
        # If "Error Mode" is for drilling mistakes, it makes sense to drill CURRENT MISTAKES (`wrong_count > 0`).
        # If they want to review OLD mistakes, maybe we need another mode?
        # For now, keep "Error" = Current Wrong.
        # But wait, if "Error Mode" is "Review Mistakes", and I just did it right, it disappears from this list. That is correct behavior for "Drilling".
        # The user's complaint was about the "List View" (Paper/Subject list) losing the MARK.
        query += " AND uqs.wrong_count > 0"
    elif mode == "difficult": 
        query += " AND uqs.is_difficult = 1"
    elif mode == "all_loop":
        # V1.3.7 FIX: User explicitly wants "Start Study" in Subject to NOT include Paper questions.
        # "All Loop" now means "All Questions in this Subject's BANK".
        query += " AND q.paper_id IS NULL"
    else: 
        # Default/Normal/Pure
        query += " AND (q.user_id = ? AND q.paper_id IS NULL)"
        params.append(user['id'])

    # 3. Type Filter
    if qtype == "single":
        query += " AND q.question_type = 'objective'"
    elif qtype == "multi":
        query += " AND q.question_type = 'multi'"
    elif qtype == "fill":
        query += " AND q.question_type = 'fill'"
    elif qtype == "essay":
        query += " AND q.question_type = 'subjective'"
    # 'all' -> no filter

    # 'all' -> no filter

    try:
        ids = [r['id'] for r in conn.execute(query + " ORDER BY RANDOM()", params).fetchall()]
        questions = [get_question_data(conn, qid, user['id']) for qid in ids]
        # Filter None
        questions = [q for q in questions if q]
        
        conn.close()
        return templates.TemplateResponse("study.html", {"request": request, "app_name": get_app_name(), "user": user, "subject": dict(s), "questions": questions, "mode": mode, "qtype": qtype, "is_paper": False})
    except Exception as e:
        conn.close()
        return HTMLResponse(content=f"<h1>Error in Study Page</h1><pre>{e}</pre><p>Query: {query}</p><p>Params: {params}</p>", status_code=500)

@app.get("/question/{qid}", response_class=HTMLResponse)
async def single_question(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); d = get_question_data(conn, qid, user['id'])
    if not d: conn.close(); raise HTTPException(404)
    s = conn.execute("SELECT * FROM subjects WHERE id = ?", (d['subject_id'],)).fetchone()
    conn.close()
    return templates.TemplateResponse("study.html", {"request": request, "app_name": get_app_name(), "user": user, "subject": dict(s), "questions": [d], "single": True})

@app.get("/paper-entry", response_class=HTMLResponse)
async def paper_entry_home(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("paper_entry_home.html", {"request": request, "app_name": get_app_name(), "user": user})

@app.get("/slicer", response_class=HTMLResponse)
async def slicer_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall()
    papers = conn.execute("SELECT * FROM papers WHERE user_id = ? ORDER BY created_at DESC", (user['id'],)).fetchall()
    conn.close()
    return templates.TemplateResponse("slicer.html", {"request": request, "app_name": get_app_name(), "user": user, "subjects": [dict(s) for s in subs], "papers": [dict(p) for p in papers]})

@app.post("/api/slice-upload")
async def slice_upload(request: Request, file: Optional[UploadFile] = File(None), page: int = Form(1)):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    user_pdf = os.path.join(TEMP_DIR, f"pdf_{user['id']}.pdf")
    if file and file.filename:
        with open(user_pdf, "wb") as f: shutil.copyfileobj(file.file, f)
    if not os.path.exists(user_pdf): return JSONResponse({"error": "No file"}, status_code=400)
    info = pdfinfo_from_path(user_pdf)
    total = int(info.get('Pages', 1))
    imgs = convert_from_path(user_pdf, first_page=page, last_page=page)
    tmp_img = os.path.join(TEMP_DIR, f"p_{user['id']}_{page}.jpg")
    imgs[0].save(tmp_img, "JPEG")
    with open(tmp_img, "rb") as f: enc = base64.b64encode(f.read()).decode()
    os.remove(tmp_img); return {"img": f"data:image/jpeg;base64,{enc}", "total": total}

@app.post("/api/slice-save")
@app.post("/api/slice-save")
async def slice_save(
    request: Request,
    sid: int = Form(...),
    pid: Optional[int] = Form(None),
    text: str = Form(""),
    type: str = Form(...),
    ans: str = Form(""),
    a: Optional[str] = Form(None),
    b: Optional[str] = Form(None),
    c: Optional[str] = Form(None),
    d: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    rect: str = Form(...),
    canvas_w: int = Form(...),
    canvas_h: int = Form(...),
    page: int = Form(...),
    answer_image: Optional[UploadFile] = File(None)
):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    import json
    rect_dict = json.loads(rect)

    user_pdf = os.path.join(TEMP_DIR, f"pdf_{user['id']}.pdf")
    if not os.path.exists(user_pdf): return JSONResponse({"error": "No PDF"}, status_code=400)
    
    # Process Question Image (Slice)
    imgs = convert_from_path(user_pdf, first_page=page, last_page=page)
    img = imgs[0]
    rx = img.width / canvas_w; ry = img.height / canvas_h
    crop_rect = (rect_dict['left']*rx, rect_dict['top']*ry, (rect_dict['left']+rect_dict['width'])*rx, (rect_dict['top']+rect_dict['height'])*ry)
    cropped = img.crop(crop_rect)
    
    uid = uuid.uuid4().hex; q_img_name = f"{uid}.webp"
    cropped.convert('RGB').save(os.path.join(UPLOAD_DIR, q_img_name), "WEBP", quality=80)
    
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)', 
                (sid, pid, user['id'], text, type, ans, a, b, c, d, source))
    qid = cur.lastrowid
    cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, q_img_name, 'question'))
    
    # Process Answer Image (Upload)
    if answer_image and answer_image.filename:
        a_p = await save_img(answer_image)
        cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, a_p, 'answer'))

    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/papers", response_class=HTMLResponse)
async def papers_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    
    # Fetch papers and mark if assigned
    ps = conn.execute('''
        SELECT p.*, s.name as s_name, COUNT(q.id) as q_count,
        CASE WHEN p.user_id != ? THEN 1 ELSE 0 END as is_assigned
        FROM papers p 
        JOIN subjects s ON p.subject_id = s.id 
        LEFT JOIN questions q ON p.id = q.paper_id 
        LEFT JOIN paper_assignments pa ON p.id = pa.paper_id
        WHERE p.user_id = ? OR pa.user_id = ?
        GROUP BY p.id ORDER BY p.created_at DESC
    ''', (user['id'], user['id'], user['id'])).fetchall()
    
    subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall()
    
    # Fetch other users for distribution if admin
    other_users = []
    if user['role'] == 'admin':
        other_users = [dict(u) for u in conn.execute("SELECT id, username FROM users WHERE id != ?", (user['id'],)).fetchall()]
        
    conn.close()
    return templates.TemplateResponse("papers.html", {
        "request": request, 
        "app_name": get_app_name(), 
        "user": user, 
        "papers": [dict(p) for p in ps], 
        "subjects": [dict(s) for s in subs],
        "all_users": other_users
    })

@app.post("/paper/add")
async def add_paper(request: Request, name: str = Form(...), sid: int = Form(...)):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); conn.execute("INSERT OR IGNORE INTO papers (name, subject_id, user_id) VALUES (?,?,?)", (name.strip(), sid, user['id']))
    conn.commit(); conn.close(); return RedirectResponse("/papers", status_code=303)

@app.get("/paper/{pid}", response_class=HTMLResponse)
async def paper_detail(request: Request, pid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    p = conn.execute('''
        SELECT p.*, s.name as s_name FROM papers p 
        JOIN subjects s ON p.subject_id = s.id 
        LEFT JOIN paper_assignments pa ON p.id = pa.paper_id
        WHERE p.id = ? AND (p.user_id = ? OR pa.user_id = ?)
    ''', (pid, user['id'], user['id'])).fetchone()
    if not p: conn.close(); raise HTTPException(404)
    try:
        # V1.3.6: Update query to fetch User Status for Paper Questions
        q_ids_rows = conn.execute("SELECT id FROM questions WHERE paper_id = ? ORDER BY id ASC", (pid,)).fetchall()
        q_ids = [r['id'] for r in q_ids_rows]
        
        questions = []
        for qid in q_ids:
            q = get_question_data(conn, qid, user['id'])
            # Ensure status is present (get_question_data adds it, but let's verify)
            if q: questions.append(q)
        
        is_owner = p['user_id'] == user['id']
        conn.close(); return templates.TemplateResponse("paper_detail.html", {
            "request": request, 
            "app_name": get_app_name(), 
            "user": user, 
            "paper": dict(p), 
            "questions": questions,
            "is_owner": is_owner
        })
    except Exception as e:
        conn.close()
        return HTMLResponse(content=f"<h1>Error in Paper Detail</h1><pre>{e}</pre>", status_code=500)

@app.post("/paper/delete/{pid}")
async def delete_paper(request: Request, pid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    # Check ownership
    p = conn.execute("SELECT user_id FROM papers WHERE id = ?", (pid,)).fetchone()
    if p and p['user_id'] == user['id']:
        conn.execute("DELETE FROM papers WHERE id = ?", (pid,))
        conn.commit()
    conn.close()
    return RedirectResponse("/papers", status_code=303)

@app.get("/paper/{pid}/test", response_class=HTMLResponse)
async def paper_test(request: Request, pid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    try:
        p = conn.execute('''
            SELECT p.* FROM papers p 
            LEFT JOIN paper_assignments pa ON p.id = pa.paper_id
            WHERE p.id = ? AND (p.user_id = ? OR pa.user_id = ?)
        ''', (pid, user['id'], user['id'])).fetchone()
        
        if not p: 
            conn.close()
            return HTMLResponse("<h1>Access Denied or Not Found / 无权访问或试卷不存在</h1>", status_code=404)

        ids = [r['id'] for r in conn.execute("SELECT id FROM questions WHERE paper_id = ? ORDER BY id ASC", (pid,)).fetchall()]
        questions = [get_question_data(conn, qid, user['id']) for qid in ids]
        questions = [q for q in questions if q]
        
        conn.close()
        # V1.3.9: Pass mode='paper_test' to distinguish in template if needed
        return templates.TemplateResponse("study.html", {"request": request, "app_name": get_app_name(), "user": user, "subject": {"name": p['name'], "id": p['subject_id']}, "questions": questions, "mode": "paper_test", "is_paper": True})
    except Exception as e:
        conn.close()
        return HTMLResponse(content=f"<h1>Error in Paper Test</h1><pre>{e}</pre>", status_code=500)

@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request, sid: Optional[int] = None):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall()
    q_str = '''
        SELECT q.*, s.name as s_name, uqs.is_difficult 
        FROM questions q 
        JOIN subjects s ON q.subject_id = s.id 
        LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ? 
        WHERE q.paper_id IS NULL AND q.user_id = ?
    '''
    params = [user['id'], user['id']]
    if sid: q_str += " AND q.subject_id = ?"; params.append(sid)
    qs = conn.execute(q_str + " ORDER BY q.created_at DESC", params).fetchall()
    conn.close(); return templates.TemplateResponse("manage.html", {"request": request, "app_name": get_app_name(), "user": user, "questions": [dict(q) for q in qs], "subjects": [dict(s) for s in subs], "current_sid": sid})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall(); conn.close()
    return templates.TemplateResponse("settings.html", {"request": request, "app_name": get_app_name(), "user": user, "subjects": [dict(s) for s in subs]})

# Admin Routes
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    conn = get_db(); users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall(); conn.close()
    return templates.TemplateResponse("admin_users.html", {"request": request, "app_name": get_app_name(), "user": user, "users": [dict(u) for u in users]})

@app.post("/admin/user/add")
async def admin_add_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("user")):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username.strip(), pwd_context.hash(password), role))
        conn.commit()
    except: pass
    conn.close(); return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/user/delete/{uid}")
async def admin_delete_user(request: Request, uid: int):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin' or user['id'] == uid: return RedirectResponse("/", status_code=303)
    conn = get_db(); conn.execute("DELETE FROM users WHERE id = ?", (uid,)); conn.commit(); conn.close()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/distribute")
async def admin_distribute(request: Request):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = await request.json()
    pid, target_uids = data['pid'], data['uids']; conn = get_db()
    for uid in target_uids:
        conn.execute("INSERT OR IGNORE INTO paper_assignments (paper_id, user_id, assigned_by) VALUES (?, ?, ?)", (pid, uid, user['id']))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/admin/revoke/{pid}")
async def admin_revoke(request: Request, pid: int):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); conn.execute("DELETE FROM paper_assignments WHERE paper_id = ? AND assigned_by = ?", (pid, user['id']))
    conn.commit(); conn.close(); return {"status": "ok"}

# Refactored API
@app.post("/api/record")
async def record(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = await request.json(); qid, ok = data['qid'], data['ok']; conn = get_db(); cur = conn.cursor()
    
    # Check permission (simple existence check)
    allowed = cur.execute("SELECT 1 FROM questions WHERE id = ?", (qid,)).fetchone()
    if not allowed: conn.close(); return JSONResponse({"error": "Question not found"}, status_code=404)
    
    # Check if status record exists
    status_row = cur.execute("SELECT wrong_count, is_difficult FROM user_question_status WHERE user_id = ? AND question_id = ?", (user['id'], qid)).fetchone()
    
    if not status_row:
        # Create new record
        wc = 0 if ok else 1
        hw = 0 if ok else 1
        is_diff = 0
        cur.execute("INSERT INTO user_question_status (user_id, question_id, wrong_count, history_wrong, is_difficult) VALUES (?, ?, ?, ?, ?)", (user['id'], qid, wc, hw, is_diff))
    else:
        # Update existing
        if ok:
            # CORRECT: Clear active wrong_count, keep history and difficulty (manual clear only for difficult)
            cur.execute("UPDATE user_question_status SET wrong_count = 0 WHERE user_id = ? AND question_id = ?", (user['id'], qid))
        else:
            # WRONG: Increment wrong_count, set history_wrong
            new_wc = status_row['wrong_count'] + 1
            # Auto-mark difficult if wrong >= 2 times (Active count)
            new_diff = 1 if new_wc >= 2 else status_row['is_difficult']
            cur.execute("UPDATE user_question_status SET wrong_count = ?, history_wrong = 1, is_difficult = ? WHERE user_id = ? AND question_id = ?", (new_wc, new_diff, user['id'], qid))
    
    # Record study log with LOCAL TIME
    cur.execute("INSERT INTO study_records (user_id, question_id, is_correct, studied_at) VALUES (?,?,?, datetime('now', 'localtime'))", (user['id'], qid, ok))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/delete/{qid}")
async def delete_q(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); conn.execute("DELETE FROM questions WHERE id = ? AND user_id = ?", (qid, user['id'])); conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/clear-status/{qid}")
async def clear_status(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); conn.execute("UPDATE user_question_status SET wrong_count = 0, is_difficult = 0 WHERE user_id = ? AND question_id = ?", (user['id'], qid)); conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/unmark-difficult/{qid}")
async def unmark_difficult(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); conn.execute("UPDATE user_question_status SET is_difficult = 0, wrong_count = 0 WHERE question_id = ? AND user_id = ?", (qid, user['id'])); conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/clone-to-bank/{qid}")
async def clone_to_bank(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); cur = conn.cursor()
    # Updated check: allow if owned OR assigned
    q = cur.execute('''
        SELECT q.*, s.name as s_name FROM questions q 
        JOIN subjects s ON q.subject_id = s.id
        LEFT JOIN paper_assignments pa ON q.paper_id = pa.paper_id
        WHERE q.id = ? AND (q.user_id = ? OR pa.user_id = ?)
    ''', (qid, user['id'], user['id'])).fetchone()
    
    if not q: conn.close(); return JSONResponse({"error": "Not found or No permission"}, status_code=404)
    
    # Map subject: find or create same-named subject for current user
    target_sub = cur.execute("SELECT id FROM subjects WHERE name = ? AND user_id = ?", (q['s_name'], user['id'])).fetchone()
    if target_sub:
        target_sid = target_sub['id']
    else:
        cur.execute("INSERT INTO subjects (name, user_id) VALUES (?, ?)", (q['s_name'], user['id']))
        target_sid = cur.lastrowid
        
    src = q['source']
    if q['paper_id'] and not src:
        p = cur.execute("SELECT name FROM papers WHERE id = ?", (q['paper_id'],)).fetchone()
        if p: src = p['name']
        
    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, is_difficult) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                (target_sid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q['option_a'], q['option_b'], q['option_c'], q['option_d'], src, q['is_difficult']))
    new_qid = cur.lastrowid
    
    # Copy images physically
    imgs = cur.execute("SELECT * FROM question_images WHERE question_id = ?", (qid,)).fetchall()
    for img in imgs:
        old_path = os.path.join(UPLOAD_DIR, img['path'])
        if os.path.exists(old_path):
            new_name = f"{uuid.uuid4().hex}.webp"
            shutil.copy2(old_path, os.path.join(UPLOAD_DIR, new_name))
            cur.execute("INSERT INTO question_images (question_id, path, image_type) VALUES (?, ?, ?)", (new_qid, new_name, img['image_type']))
            
    conn.commit(); conn.close(); return {"status": "ok"}

@app.post("/api/reset-stats")
async def reset_stats(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); conn.execute("DELETE FROM study_records WHERE user_id = ?", (user['id'],)); conn.execute("UPDATE questions SET wrong_count = 0, is_difficult = 0 WHERE user_id = ?", (user['id'],)); conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/nuclear-reset")
async def nuclear_reset(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM study_records WHERE user_id = ?", (user['id'],))
    c.execute("DELETE FROM question_images WHERE question_id IN (SELECT id FROM questions WHERE user_id = ?)", (user['id'],))
    c.execute("DELETE FROM questions WHERE user_id = ?", (user['id'],))
    c.execute("DELETE FROM papers WHERE user_id = ?", (user['id'],))
    c.execute("DELETE FROM subjects WHERE user_id = ?", (user['id'],))
    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/api/export/paper/{pid}")
async def export_paper(request: Request, pid: int):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db()
    p_row = conn.execute('''SELECT p.*, s.name as s_name FROM papers p JOIN subjects s ON p.subject_id = s.id LEFT JOIN paper_assignments pa ON p.id = pa.paper_id WHERE p.id = ? AND (p.user_id = ? OR pa.user_id = ?)''', (pid, user['id'], user['id'])).fetchone()
    if not p_row: conn.close(); return JSONResponse({"error": "Not found"}, status_code=404)
    data = {"paper": dict(p_row), "questions": []}
    qs = conn.execute("SELECT * FROM questions WHERE paper_id = ?", (pid,)).fetchall()
    for q in qs:
        qd = dict(q); qd['images'] = [dict(r) for r in conn.execute("SELECT * FROM question_images WHERE question_id = ?", (q['id'],)).fetchall()]
        data['questions'].append(qd)
    conn.close()
    fn = f"{data['paper']['name']}.zip"; fp = f"/tmp/{fn}"
    with zipfile.ZipFile(fp, 'w') as zf:
        zf.writestr('data.json', json.dumps(data, ensure_ascii=False))
        for q in data['questions']:
            for img in q['images']:
                ip = os.path.join(UPLOAD_DIR, img['path'])
                if os.path.exists(ip): zf.write(ip, f"uploads/{img['path']}")
    return FileResponse(fp, filename=fn)

@app.post("/api/import")
async def import_data(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    tmp = f"/tmp/import_{user['id']}_{file.filename}"
    with open(tmp, "wb") as f: shutil.copyfileobj(file.file, f)
    try:
        with zipfile.ZipFile(tmp, 'r') as zf:
            import_json = json.loads(zf.read('data.json'))
            conn = get_db(); cur = conn.cursor(); old_p = import_json['paper']; sn = old_p.get('s_name', '导入内容')
            sr = cur.execute("SELECT id FROM subjects WHERE name = ? AND user_id = ?", (sn, user['id'])).fetchone()
            if sr: sid = sr[0]
            else: cur.execute("INSERT INTO subjects (name, user_id) VALUES (?, ?)", (sn, user['id'])); sid = cur.lastrowid
            cur.execute("INSERT INTO papers (name, subject_id, user_id) VALUES (?, ?, ?)", (old_p['name'], sid, user['id'])); pid = cur.lastrowid
            for q in import_json['questions']:
                cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (sid, pid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), q.get('source')))
                qid = cur.lastrowid
                for img in q.get('images', []):
                    cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, img['path'], img['image_type']))
                    target_path = os.path.join(UPLOAD_DIR, img['path'])
                    if not os.path.exists(target_path):
                        try:
                            with zf.open(f"uploads/{img['path']}") as zsrc:
                                with open(target_path, "wb") as zdst: shutil.copyfileobj(zsrc, zdst)
                        except: pass
            conn.commit(); conn.close()
    finally:
        if os.path.exists(tmp): os.remove(tmp)
    return RedirectResponse("/papers?msg=import_ok", status_code=303)

@app.get("/api/backup")
async def full_backup(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ?", (user['id'],)).fetchall(); data = {"subjects": []}
    for s in subs:
        sd = dict(s); sd['papers'] = []
        papers = conn.execute("SELECT * FROM papers WHERE subject_id = ? AND user_id = ?", (s['id'], user['id'])).fetchall()
        for p in papers:
            pd = dict(p); pd['questions'] = []
            qs = conn.execute("SELECT * FROM questions WHERE paper_id = ?", (p['id'],)).fetchall()
            for q in qs:
                qd = dict(q); qd['images'] = [dict(r) for r in conn.execute("SELECT * FROM question_images WHERE question_id = ?", (q['id'],)).fetchall()]
                pd['questions'].append(qd)
            sd['papers'].append(pd)
        sd['standalone_questions'] = []
        qs = conn.execute("SELECT * FROM questions WHERE subject_id = ? AND paper_id IS NULL AND user_id = ?", (s['id'], user['id'])).fetchall()
        for q in qs:
            qd = dict(q); qd['images'] = [dict(r) for r in conn.execute("SELECT * FROM question_images WHERE question_id = ?", (q['id'],)).fetchall()]
            sd['standalone_questions'].append(qd)
        data['subjects'].append(sd)
    conn.close()
    fn = f"backup_{user['username']}_{date.today()}.zip"; fp = f"/tmp/{fn}"
    with zipfile.ZipFile(fp, 'w') as zf:
        zf.writestr('backup.json', json.dumps(data, ensure_ascii=False))
        for s in data['subjects']:
            for p in s['papers']:
                for q in p['questions']:
                    for img in q['images']:
                        ip = os.path.join(UPLOAD_DIR, img['path'])
                        if os.path.exists(ip): zf.write(ip, f"uploads/{img['path']}")
            for q in s['standalone_questions']:
                for img in q['images']:
                    ip = os.path.join(UPLOAD_DIR, img['path'])
                    if os.path.exists(ip): zf.write(ip, f"uploads/{img['path']}")
    return FileResponse(fp, filename=fn)

@app.post("/api/restore")
async def restore_backup(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    tmp = f"/tmp/restore_{user['id']}_{file.filename}"
    with open(tmp, "wb") as f: shutil.copyfileobj(file.file, f)
    try:
        with zipfile.ZipFile(tmp, 'r') as zf:
            backup_json = json.loads(zf.read('backup.json'))
            conn = get_db(); cur = conn.cursor()
            for s in backup_json.get('subjects', []):
                cur.execute("INSERT OR IGNORE INTO subjects (name, user_id) VALUES (?, ?)", (s['name'], user['id']))
                sr = cur.execute("SELECT id FROM subjects WHERE name = ? AND user_id = ?", (s['name'], user['id'])).fetchone()
                sid = sr[0]
                for p in s.get('papers', []):
                    cur.execute("INSERT INTO papers (name, subject_id, user_id) VALUES (?, ?, ?)", (p['name'], sid, user['id']))
                    pid = cur.lastrowid
                    for q in p.get('questions', []):
                        cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (sid, pid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), q.get('source')))
                        qid = cur.lastrowid
                        for img in q.get('images', []):
                            cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, img['path'], img['image_type']))
                            target_path = os.path.join(UPLOAD_DIR, img['path'])
                            if not os.path.exists(target_path):
                                try:
                                    with zf.open(f"uploads/{img['path']}") as zsrc:
                                        with open(target_path, "wb") as zdst: shutil.copyfileobj(zsrc, zdst)
                                except: pass
                for q in s.get('standalone_questions', []):
                    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source) VALUES (?,NULL,?,?,?,?,?,?,?,?,?)', (sid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), q.get('source')))
                    qid = cur.lastrowid
                    for img in q.get('images', []):
                        cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, img['path'], img['image_type']))
                        target_path = os.path.join(UPLOAD_DIR, img['path'])
                        if not os.path.exists(target_path):
                            try:
                                with zf.open(f"uploads/{img['path']}") as zsrc:
                                    with open(target_path, "wb") as zdst: shutil.copyfileobj(zsrc, zdst)
                            except: pass
            conn.commit(); conn.close()
    finally:
        if os.path.exists(tmp): os.remove(tmp)
    return RedirectResponse("/settings?msg=restore_ok", status_code=303)

@app.post("/settings/update")
async def update_settings(request: Request, app_name: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    conn = get_db(); conn.execute("UPDATE config SET value = ? WHERE key = 'app_name'", (app_name.strip(),)); conn.commit(); conn.close()
    return RedirectResponse("/settings", status_code=303)

@app.post("/api/change-password")
async def change_password(request: Request, old_pwd: str = Form(...), new_pwd: str = Form(...)):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    db_user = conn.execute("SELECT * FROM users WHERE id = ?", (user['id'],)).fetchone()
    if not db_user or not pwd_context.verify(old_pwd, db_user['password_hash']):
        conn.close(); return RedirectResponse("/settings?msg=pwd_err", status_code=303)
    
    new_hash = pwd_context.hash(new_pwd)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user['id']))
    conn.commit(); conn.close()
    return RedirectResponse("/settings?msg=pwd_ok", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
