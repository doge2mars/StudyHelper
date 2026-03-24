from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends, status, Body
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import sqlite3, os, uuid, shutil, zipfile, json, base64
from urllib.parse import unquote
from datetime import datetime, date, timedelta
from typing import Optional, List
from pydantic import BaseModel
from PIL import Image
import pillow_heif
from pdf2image import convert_from_path, pdfinfo_from_path
from passlib.context import CryptContext
from jose import JWTError, jwt

APP_VERSION = "v3.0.6"

app = FastAPI(title=f'深度学习 {APP_VERSION}', version=APP_VERSION)
pillow_heif.register_heif_opener()

# Security & Auth
SECRET_KEY = "66Lennoxwyr_Pro_Secret" # In production, this should be an env var
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

DB_PATH = '/app/data/study_pro.db'
UPLOAD_DIR = '/app/static/uploads'
VIDEO_UPLOAD_DIR = '/app/static/uploads/videos'
TEMP_DIR = '/tmp/study_helper_pro'
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VIDEO_UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app.mount('/static', StaticFiles(directory='/app/static'), name='static')
templates = Jinja2Templates(directory='/app/templates')
templates.env.globals['APP_VERSION'] = APP_VERSION
templates.env.globals['unquote'] = unquote

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
        display_name TEXT DEFAULT "",
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
        grade TEXT,
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
        is_difficult BOOLEAN DEFAULT 0, 
        answer_video TEXT, 
        analysis TEXT,
        grade TEXT,
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
        history_wrong INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, question_id),
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
    )''')
    
    # Tagging System (V2.5+)
    c.execute('''CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        subject_id INTEGER NOT NULL,
        FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
        UNIQUE(name, subject_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS question_tags (
        question_id INTEGER,
        tag_id INTEGER,
        PRIMARY KEY (question_id, tag_id),
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
    )''')
    
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('app_name', '深度学习')")
    c.execute("UPDATE config SET value = '深度学习' WHERE key = 'app_name'")
    
    # Performance Indexes
    print("Migrating: Creating performance indexes...")
    c.execute("CREATE INDEX IF NOT EXISTS idx_questions_subject_id ON questions (subject_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_questions_paper_id ON questions (paper_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_questions_user_id ON questions (user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_paper_assig_user_pid ON paper_assignments (user_id, paper_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_uqs_user_qid ON user_question_status (user_id, question_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_records_user_date ON study_records (user_id, studied_at)")
    
    # Default Admin
    admin_hash = pwd_context.hash("admin123")
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", admin_hash, "admin"))
    
    # V1.3.4+ Auto-Migration: Ensure history_wrong exists (Robust Check)
    try:
        # Check user_question_status
        info = c.execute("PRAGMA table_info(user_question_status)").fetchall()
        cols = [col[1] for col in info]
        if 'history_wrong' not in cols:
            print("Migrating: Adding history_wrong column to user_question_status...")
            c.execute("ALTER TABLE user_question_status ADD COLUMN history_wrong INTEGER DEFAULT 0")
            c.execute("UPDATE user_question_status SET history_wrong = 1 WHERE wrong_count > 0")
            conn.commit()
            
        # V1.3.24 Auto-Migration: Ensure questions table has new columns
        q_info = c.execute("PRAGMA table_info(questions)").fetchall()
        q_cols = [col[1] for col in q_info]
        
        # List of potentially missing columns and their definitions
        missing_cols = [
            ('difficulty', 'INTEGER DEFAULT 0'),
            ('source', 'TEXT'),
            ('wrong_count', 'INTEGER DEFAULT 0'),
            ('is_difficult', 'BOOLEAN DEFAULT 0'),
            ('answer_video', 'TEXT'),
            ('grade', 'TEXT'),
            ('analysis', 'TEXT')
        ]
        
        for col_name, col_def in missing_cols:
            if col_name not in q_cols:
                print(f"Migrating: Adding {col_name} column to questions...")
                try:
                    c.execute(f"ALTER TABLE questions ADD COLUMN {col_name} {col_def}")
                    conn.commit()
                except Exception as e:
                     print(f"Migration Error (adding {col_name}): {e}")

        # V1.5.0 Auto-Migration: Ensure papers table has `grade`
        p_info = c.execute("PRAGMA table_info(papers)").fetchall()
        p_cols = [col[1] for col in p_info]
        if 'grade' not in p_cols:
            print("Migrating: Adding grade column to papers...")
            c.execute("ALTER TABLE papers ADD COLUMN grade TEXT")
            conn.commit()

        # V1.5.1 Auto-Migration: Ensure users table has `display_name`
        u_info = c.execute("PRAGMA table_info(users)").fetchall()
        u_cols = [col[1] for col in u_info]
        if 'display_name' not in u_cols:
            print("Migrating: Adding display_name column to users...")
            c.execute('ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT ""')
            conn.commit()

    except Exception as e:
        print(f"Migration Global Error: {e}")
        
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
    return res[0] if res else "深度学习 V3.0"

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
        q = conn.execute("SELECT *, NULL as user_wrong_count, NULL as user_history_wrong, NULL as user_is_difficult, NULL as uqs_user_id FROM questions WHERE id = ?", (q_id,)).fetchone()
    
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
    
    # Process Video URL
    v = d.get('answer_video')
    if v and not v.startswith('http'):
        d['video_url'] = f"/static/uploads/videos/{v}"
    else:
        d['video_url'] = v
        
    return d

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"app_name": get_app_name()})

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

def process_question_tags(conn, qid: int, subject_id: int, tags_str: Optional[str]):
    # V2.5.0: Tagging System Helper
    conn.execute("DELETE FROM question_tags WHERE question_id = ?", (qid,))
    if not tags_str: return
    
    tag_names = list(set([t.strip() for t in tags_str.split(',') if t.strip()]))
    for t_name in tag_names:
        row = conn.execute("SELECT id FROM tags WHERE name = ? AND subject_id = ?", (t_name, subject_id)).fetchone()
        if row:
            t_id = row['id']
        else:
            cur = conn.cursor()
            cur.execute("INSERT INTO tags (name, subject_id) VALUES (?, ?)", (t_name, subject_id))
            t_id = cur.lastrowid
        conn.execute("INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)", (qid, t_id))

@app.get("/", response_class=HTMLResponse)
@app.head("/", response_class=HTMLResponse)
async def index(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); c = conn.cursor()
    active_grade = unquote(request.cookies.get('active_grade', ''))
    
    # Base conditions
    q_cond = " AND (q.grade = ? OR q.grade IS NULL)" if active_grade else ""
    p_cond = " AND (p.grade = ? OR p.grade IS NULL)" if active_grade else ""
    p_params = [active_grade] if active_grade else []
    
    # Total count: owned + assigned
    total_q = c.execute(f'''
        SELECT COUNT(DISTINCT q.id) FROM questions q 
        LEFT JOIN paper_assignments pa ON q.paper_id = pa.paper_id AND pa.user_id = ?
        WHERE (q.user_id = ? OR pa.user_id = ?){q_cond}
    ''', [user['id'], user['id'], user['id']] + p_params).fetchone()[0]
    
    today_q = c.execute("SELECT COUNT(*) FROM study_records WHERE user_id = ? AND date(studied_at) = date('now', 'localtime')", (user['id'],)).fetchone()[0]
    recs = c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as ok FROM study_records WHERE user_id = ?", (user['id'],)).fetchone()
    acc = round(recs['ok'] / recs['total'] * 100, 1) if recs['total'] and recs['total'] > 0 else 0
    
    # Subjects list: owned subjects (Optimized Query)
    # Use LEFT JOINs and GROUP BY instead of correlated subqueries for much better performance
    subs_query = f'''
        SELECT 
            s.id, s.name, s.user_id, s.created_at,
            COUNT(DISTINCT q.id) as q_count,
            COUNT(DISTINCT CASE WHEN uqs.wrong_count > 0 THEN uqs.question_id END) as wrong_count
        FROM subjects s 
        LEFT JOIN questions q ON s.id = q.subject_id AND q.user_id = ?{q_cond}
        LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ?
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.name
    '''
    subs = c.execute(subs_query, [user['id']] + p_params + [user['id'], user['id']]).fetchall()
    
    distributed = c.execute(f'''SELECT p.*, s.name as s_name FROM paper_assignments pa 
                                JOIN papers p ON pa.paper_id = p.id 
                                JOIN subjects s ON p.subject_id = s.id
                                WHERE pa.user_id = ?{p_cond}''', [user['id']] + p_params).fetchall()
    conn.close()
    return templates.TemplateResponse(request, "index.html", {"app_name": get_app_name(), "user": user, "subjects": [dict(s) for s in subs], "distributed": [dict(p) for p in distributed], "stats": {"total": total_q, "today": today_q, "accuracy": acc}})

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
async def subject(request: Request, sid: int, sort: Optional[str] = None):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    s = conn.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (sid, user['id'])).fetchone()
    if not s: conn.close(); raise HTTPException(404)
    active_grade = unquote(request.cookies.get('active_grade', ''))
    q_cond = " AND (q.grade = ? OR q.grade IS NULL)" if active_grade else ""
    
    # Base parameters for the query
    query_params = [user['id'], sid]
    if active_grade:
        query_params.append(active_grade)
    query_params.append(user['id'])
    
    query = f'''
        SELECT q.*, 
               uqs.wrong_count as user_wrong_count, 
               uqs.is_difficult as user_is_difficult, 
               uqs.history_wrong as user_history_wrong,
               uqs.user_id as uqs_uid
        FROM questions q
        LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ?
        WHERE q.subject_id = ? 
        AND q.paper_id IS NULL{q_cond}
        AND (
            q.user_id = ? 
            OR 
            (uqs.wrong_count > 0 OR uqs.is_difficult = 1 OR uqs.history_wrong = 1)
        )
    '''
    
    if sort == 'type':
        query += " ORDER BY q.question_type ASC, q.created_at DESC"
    elif sort == 'status':
        # Status Priority: 1. Wrong (wrong_count > 0, ordered by count) -> 2. Difficult (is_difficult=1) -> 3. Others
        query += '''
            ORDER BY 
                CASE 
                    WHEN COALESCE(uqs.wrong_count, 0) > 0 THEN 1 
                    WHEN COALESCE(uqs.is_difficult, 0) = 1 THEN 2 
                    ELSE 3 
                END ASC,
                COALESCE(uqs.wrong_count, 0) DESC,
                q.created_at DESC
        '''
    else:
        query += " ORDER BY q.created_at DESC"
        
    qs = conn.execute(query, query_params).fetchall()
    
    # Process for template
    questions = []
    for r in qs:
        d = dict(r)
        if d['user_wrong_count'] is not None:
            d['wrong_count'] = d['user_wrong_count']
        if d['user_is_difficult'] is not None:
             d['is_difficult'] = d['user_is_difficult']
        if d['user_history_wrong'] is not None:
            d['history_wrong'] = d['user_history_wrong']
            
        d['has_record'] = d['uqs_uid'] is not None
        questions.append(d)

    # V1.3.5: Calculate Stats
    stats = {
        "total": len(questions),
        "wrong": sum(1 for q in questions if q.get('wrong_count', 0) > 0),
        "difficult": sum(1 for q in questions if q.get('is_difficult') == 1)
    }

    conn.close()
    return templates.TemplateResponse(request, "subject.html", {"app_name": get_app_name(), "user": user, "subject": dict(s), "questions": questions, "stats": stats})

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

async def save_video(f: UploadFile) -> str:
    ext = os.path.splitext(f.filename)[1].lower()
    vid_name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(VIDEO_UPLOAD_DIR, vid_name), "wb") as out:
        shutil.copyfileobj(f.file, out)
    return vid_name

@app.get("/subject/{sid}/add", response_class=HTMLResponse)
async def add_q_page(request: Request, sid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    s = conn.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (sid, user['id'])).fetchone()
    conn.close()
    if not s: raise HTTPException(404)
    return templates.TemplateResponse(request, "add.html", {"app_name": get_app_name(), "user": user, "subject": dict(s)})

@app.post("/subject/{sid}/add")
async def add_q(request: Request, sid: int, q_text: str = Form(...), q_type: str = Form(...), ans: str = Form(...), a: Optional[str] = Form(None), b: Optional[str] = Form(None), c: Optional[str] = Form(None), d: Optional[str] = Form(None), source: Optional[str] = Form(None), grade: Optional[str] = Form(None), analysis: Optional[str] = Form(None), tags: Optional[str] = Form(None), q_images: List[UploadFile] = File([]), a_images: List[UploadFile] = File([]), paper_id_str: Optional[str] = Form(None, alias="paper_id"), v_url: Optional[str] = Form(None), v_file: Optional[UploadFile] = File(None)):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    
    paper_id = int(paper_id_str) if paper_id_str and paper_id_str.isdigit() else None
    
    # Handle Video
    final_v = v_url
    if v_file and v_file.filename:
        final_v = await save_video(v_file)

    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, answer_video, grade, analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, paper_id, user['id'], q_text, q_type, ans, a, b, c, d, source, final_v, grade, analysis))
    qid = cur.lastrowid
    for f in q_images:
        if f.filename:
            p = await save_img(f)
            cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, p, 'question'))
    for f in a_images:
        if f.filename:
            p = await save_img(f)
            cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, p, 'answer'))
            
    # Process Tags
    process_question_tags(conn, qid, sid, tags)
    
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
    
    active_grade = unquote(request.cookies.get('active_grade', ''))
    if active_grade:
        query += " AND (q.grade = ? OR q.grade IS NULL)"
        params.append(active_grade)
    
    access_condition = " AND (q.user_id = ? OR pa.user_id = ?)"
    params.extend([user['id'], user['id']])
    query += access_condition
    
    # 2. Mode Filter
    if mode == "difficult": 
        query += " AND uqs.is_difficult = 1 AND q.paper_id IS NULL"
    elif mode == "all_loop":
        # V1.3.7 FIX: User explicitly wants "Start Study" in Subject to NOT include Paper questions.
        # "All Loop" now means "All Questions in this Subject's BANK".
        query += " AND q.paper_id IS NULL"
    elif mode == "error": 
        # V1.3.15: Error mode should also be Pure Subject Questions
        query += " AND uqs.wrong_count > 0 AND q.paper_id IS NULL"
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
        return templates.TemplateResponse(request, "study.html", {"app_name": get_app_name(), "user": user, "subject": dict(s), "questions": questions, "mode": mode, "qtype": qtype, "is_paper": False})
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
    return templates.TemplateResponse(request, "study.html", {"app_name": get_app_name(), "user": user, "subject": dict(s), "questions": [d], "single": True})

@app.get("/paper-entry", response_class=HTMLResponse)
async def paper_entry_home(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "paper_entry_home.html", {"app_name": get_app_name(), "user": user})

@app.get("/slicer", response_class=HTMLResponse)
async def slicer_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall()
    papers = conn.execute("SELECT * FROM papers WHERE user_id = ? ORDER BY created_at DESC", (user['id'],)).fetchall()
    conn.close()
    return templates.TemplateResponse(request, "slicer.html", {"app_name": get_app_name(), "user": user, "subjects": [dict(s) for s in subs], "papers": [dict(p) for p in papers]})

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

class BatchDistributeRequest(BaseModel):
    question_ids: List[int]
    target_user_id: int

class BatchDeleteRequest(BaseModel):
    question_ids: List[int]

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
    answer_image: Optional[UploadFile] = File(None),
    v_url: Optional[str] = Form(None),
    v_file: Optional[UploadFile] = File(None),
    grade: Optional[str] = Form(None),
    analysis: Optional[str] = Form(None)
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
    
    # Handle Video
    final_v = v_url
    if v_file and v_file.filename:
        final_v = await save_video(v_file)

    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, answer_video, grade, analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', 
                (sid, pid, user['id'], text, type, ans, a, b, c, d, source, final_v, grade, analysis))
    qid = cur.lastrowid
    cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, q_img_name, 'question'))
    
    # Process Answer Image (Upload)
    if answer_image and answer_image.filename:
        a_p = await save_img(answer_image)
        cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, a_p, 'answer'))

    conn.commit(); conn.close(); return {"status": "ok"}

@app.get("/question/{qid}/edit", response_class=HTMLResponse)
async def edit_question_page(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    
    # Check if user owns the question or its subject
    q_row = conn.execute("SELECT * FROM questions WHERE id = ? AND user_id = ?", (qid, user['id'])).fetchone()
    if not q_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Question not found or access denied.")
    
    q_data = dict(q_row)
    s = conn.execute("SELECT * FROM subjects WHERE id = ?", (q_data['subject_id'],)).fetchone()
    
    # Fetch images
    q_imgs = conn.execute("SELECT * FROM question_images WHERE question_id = ? AND image_type = 'question'", (qid,)).fetchall()
    a_imgs = conn.execute("SELECT * FROM question_images WHERE question_id = ? AND image_type = 'answer'", (qid,)).fetchall()
    q_data['q_images'] = [dict(i) for i in q_imgs]
    q_data['a_images'] = [dict(i) for i in a_imgs]
    
    # Fetch tags
    q_tags = conn.execute("SELECT t.name FROM question_tags qt JOIN tags t ON qt.tag_id = t.id WHERE qt.question_id = ?", (qid,)).fetchall()
    q_data['tags'] = [t['name'] for t in q_tags]
    
    conn.close()
    return templates.TemplateResponse(request, "edit_question.html", {"app_name": get_app_name(), "user": user, "subject": dict(s), "q": q_data})

@app.post("/question/{qid}/edit")
async def edit_question_post(
    request: Request, 
    qid: int, 
    q_text: str = Form(...), 
    q_type: str = Form(...),
    ans: str = Form(...), 
    a: Optional[str] = Form(None), 
    b: Optional[str] = Form(None), 
    c: Optional[str] = Form(None), 
    d: Optional[str] = Form(None), 
    source: Optional[str] = Form(None), 
    grade: Optional[str] = Form(None), 
    analysis: Optional[str] = Form(None),
    is_difficult: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    q_files: List[UploadFile] = File([]),
    a_files: List[UploadFile] = File([]),
    v_file: Optional[UploadFile] = File(None)
):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    
    conn = get_db()
    # Check permission
    q_row = conn.execute("SELECT id, subject_id, answer_video FROM questions WHERE id = ? AND user_id = ?", (qid, user['id'])).fetchone()
    if not q_row:
        conn.close()
        return HTMLResponse("Access denied.", status_code=403)
        
    diff_val = 1 if is_difficult else 0
        
    conn.execute('''
        UPDATE questions SET 
            question_text = ?, 
            question_type = ?,
            correct_answer = ?, 
            option_a = ?, option_b = ?, option_c = ?, option_d = ?, 
            source = ?, grade = ?, 
            analysis = ?,
            is_difficult = ?
        WHERE id = ? AND user_id = ?
    ''', (q_text, q_type, ans, a, b, c, d, source, grade, analysis, diff_val, qid, user['id']))
    
    process_question_tags(conn, qid, q_row['subject_id'], tags)
    
    # Process new question images
    if q_files:
        for f in q_files:
            if f.filename:
                path = await save_img(f)
                if path:
                    conn.execute("INSERT INTO question_images (question_id, path, image_type) VALUES (?, ?, 'question')", (qid, path))
                    
    # Process new answer images
    if a_files:
        for f in a_files:
            if f.filename:
                path = await save_img(f)
                if path:
                    conn.execute("INSERT INTO question_images (question_id, path, image_type) VALUES (?, ?, 'answer')", (qid, path))
                    
    # Process new video
    if v_file and v_file.filename:
        v_path = await save_video(v_file)
        if v_path:
            # optionally delete old video file from disk here if needed, but not required
            conn.execute("UPDATE questions SET answer_video = ? WHERE id = ?", (v_path, qid))

    conn.commit()
    conn.close()
    
    return RedirectResponse("/manage", status_code=303)

@app.post("/api/delete-media/{media_id}")
async def delete_media(request: Request, media_id: int):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401)
    
    conn = get_db()
    # verify ownership
    row = conn.execute('''
        SELECT qi.path FROM question_images qi
        JOIN questions q ON qi.question_id = q.id
        WHERE qi.id = ? AND q.user_id = ?
    ''', (media_id, user['id'])).fetchone()
    
    if row:
        filename = row['path']
        # path stored is just filename (e.g. "abc123.webp"), construct full disk path
        full_path = os.path.join(UPLOAD_DIR, os.path.basename(filename))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                print(f"Error removing file {full_path}: {e}")
        
        conn.execute("DELETE FROM question_images WHERE id = ?", (media_id,))
        conn.commit()
        res = {"success": True}
    else:
        res = {"error": "Media not found or permission denied"}
        
    conn.close()
    return JSONResponse(content=res)

@app.post("/api/delete-video/{qid}")
async def delete_video(request: Request, qid: int):
    user = await get_current_user(request)
    if not user: raise HTTPException(status_code=401)
    
    conn = get_db()
    row = conn.execute("SELECT answer_video FROM questions WHERE id = ? AND user_id = ?", (qid, user['id'])).fetchone()
    
    if row and row['answer_video']:
        vid_filename = row['answer_video']
        # answer_video stores just the filename; build full disk path
        if vid_filename.startswith('/'):
            full_path = vid_filename
        else:
            full_path = os.path.join(VIDEO_UPLOAD_DIR, os.path.basename(vid_filename))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception:
                pass
        
        conn.execute("UPDATE questions SET answer_video = NULL WHERE id = ?", (qid,))
        conn.commit()
        res = {"success": True}
    else:
        res = {"error": "Question not found or video does not exist"}
        
    conn.close()
    return JSONResponse(content=res)

@app.get("/papers", response_class=HTMLResponse)
async def papers_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db()
    
    active_grade = unquote(request.cookies.get('active_grade', ''))
    p_cond = " AND (p.grade = ? OR p.grade IS NULL)" if active_grade else ""
    p_params = [active_grade] if active_grade else []
    
    # Fetch papers and mark if assigned
    ps = conn.execute(f'''
        SELECT p.*, s.name as s_name, COUNT(q.id) as q_count,
        CASE WHEN p.user_id != ? THEN 1 ELSE 0 END as is_assigned
        FROM papers p 
        JOIN subjects s ON p.subject_id = s.id 
        LEFT JOIN questions q ON p.id = q.paper_id 
        LEFT JOIN paper_assignments pa ON p.id = pa.paper_id
        WHERE (p.user_id = ? OR pa.user_id = ?){p_cond}
        GROUP BY p.id ORDER BY p.created_at DESC
    ''', [user['id'], user['id'], user['id']] + p_params).fetchall()
    
    subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall()
    
    # Fetch other users for distribution if admin
    other_users = []
    if user['role'] == 'admin':
        other_users = [dict(u) for u in conn.execute("SELECT id, username FROM users WHERE id != ?", (user['id'],)).fetchall()]
        
    conn.close()
    return templates.TemplateResponse(request, "papers.html", {
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
    
    active_grade = unquote(request.cookies.get('active_grade', ''))
    grade_val = active_grade if active_grade else None
    
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO papers (name, subject_id, user_id, grade) VALUES (?,?,?,?)", (name.strip(), sid, user['id'], grade_val))
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
        conn.close(); return templates.TemplateResponse(request, "paper_detail.html", {
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
        # V1.3.15: Cascade delete questions first
        conn.execute("DELETE FROM questions WHERE paper_id = ?", (pid,))
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
        return templates.TemplateResponse(request, "study.html", {"app_name": get_app_name(), "user": user, "subject": {"name": p['name'], "id": p['subject_id']}, "questions": questions, "mode": "paper_test", "is_paper": True})
    except Exception as e:
        conn.close()
        return HTMLResponse(content=f"<h1>Error in Paper Test</h1><pre>{e}</pre>", status_code=500)

@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request, sid: Optional[int] = None, sort: Optional[str] = None, tag_id: Optional[int] = None):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall()
    
    # Fetch tags for sidebar if a subject is selected
    tags = []
    if sid:
        # Only show tags that are actually used in the user's questions
        tags = conn.execute('''
            SELECT DISTINCT t.* FROM tags t
            JOIN question_tags qt ON t.id = qt.tag_id
            JOIN questions q ON qt.question_id = q.id
            WHERE t.subject_id = ? AND q.user_id = ? AND q.paper_id IS NULL
            ORDER BY t.name
        ''', (sid, user['id'])).fetchall()

    q_str = '''
        SELECT q.*, s.name as s_name, 
               uqs.is_difficult as user_is_difficult 
        FROM questions q 
        JOIN subjects s ON q.subject_id = s.id 
        LEFT JOIN user_question_status uqs ON q.id = uqs.question_id AND uqs.user_id = ? 
    '''
    if tag_id:
        q_str += " JOIN question_tags qt ON q.id = qt.question_id WHERE qt.tag_id = ? AND q.paper_id IS NULL AND q.user_id = ?"
        params = [user['id'], tag_id, user['id']]
    else:
        q_str += " WHERE q.paper_id IS NULL AND q.user_id = ?"
        params = [user['id'], user['id']]
    
    active_grade = unquote(request.cookies.get('active_grade', ''))
    if active_grade:
        q_str += " AND (q.grade = ? OR q.grade IS NULL)"
        params.append(active_grade)
        
    if sid: q_str += " AND q.subject_id = ?"; params.append(sid)
    
    if sort == 'type':
        q_str += " ORDER BY q.subject_id ASC, q.question_type ASC, q.created_at DESC"
    else:
        q_str += " ORDER BY q.created_at DESC"
        
    qs = conn.execute(q_str, params).fetchall()
    
    # Process to overwrite legacy is_difficult and fetch tags per question
    questions = []
    if qs:
        # Batch fetch tags to avoid N+1 queries
        q_ids = [r['id'] for r in qs]
        placeholders = ','.join(['?'] * len(q_ids))
        tags_query = f'''
            SELECT qt.question_id, t.id, t.name 
            FROM question_tags qt 
            JOIN tags t ON qt.tag_id = t.id 
            WHERE qt.question_id IN ({placeholders})
        '''
        tags_rows = conn.execute(tags_query, q_ids).fetchall()
        tags_map = {}
        for row in tags_rows:
            tags_map.setdefault(row['question_id'], []).append({'id': row['id'], 'name': row['name']})

        for r in qs:
            d = dict(r)
            if d['user_is_difficult'] is not None:
                d['is_difficult'] = d['user_is_difficult']
            d['tags'] = tags_map.get(d['id'], [])
            questions.append(d)
        
    all_users = conn.execute("SELECT id, username, role FROM users ORDER BY username").fetchall()
    conn.close()
    return templates.TemplateResponse(request, "manage.html", {
        "app_name": get_app_name(), "user": user, 
        "questions": questions, "subjects": [dict(s) for s in subs], 
        "current_sid": sid, "all_users": [dict(u) for u in all_users],
        "tags": [dict(t) for t in tags], "current_tag_id": tag_id
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    conn = get_db(); subs = conn.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (user['id'],)).fetchall(); conn.close()
    return templates.TemplateResponse(request, "settings.html", {"app_name": get_app_name(), "user": user, "subjects": [dict(s) for s in subs]})

# Admin Routes
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    conn = get_db(); users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall(); conn.close()
    return templates.TemplateResponse(request, "admin_users.html", {"app_name": get_app_name(), "user": user, "users": [dict(u) for u in users]})

@app.post("/admin/user/add")
async def admin_add_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("user"), display_name: str = Form("")):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)", (username.strip(), pwd_context.hash(password), role, display_name.strip()))
        conn.commit()
    except: pass
    conn.close(); return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/user/delete/{uid}")
async def admin_delete_user(request: Request, uid: int):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin' or user['id'] == uid: return RedirectResponse("/", status_code=303)
    conn = get_db(); conn.execute("DELETE FROM users WHERE id = ?", (uid,)); conn.commit(); conn.close()
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/user/update-name")
async def admin_update_name(request: Request, uid: int = Form(...), display_name: str = Form("")):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    conn = get_db()
    conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name.strip(), uid))
    conn.commit(); conn.close()
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
    try:
        cur.execute("INSERT INTO study_records (user_id, question_id, is_correct, studied_at) VALUES (?,?,?, datetime('now', 'localtime'))", (user['id'], qid, ok))
        conn.commit()
    except Exception as e:
        print(f"Record API Error: {e}")
        conn.rollback() # Ensure rollback on error to release locks
        return JSONResponse({"error": f"Database Error: {str(e)}"}, status_code=500)
    finally:
        conn.close()
    
    return {"status": "ok"}

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
    q = dict(q)  # Convert Row to dict for .get() support
    
    try:
        # Map subject: find or create same-named subject for current user
        target_sub = cur.execute("SELECT id FROM subjects WHERE name = ? AND user_id = ?", (q['s_name'], user['id'])).fetchone()
        if target_sub:
            target_sid = target_sub['id']
        else:
            cur.execute("INSERT INTO subjects (name, user_id) VALUES (?, ?)", (q['s_name'], user['id']))
            target_sid = cur.lastrowid
            
        src = q.get('source')
        if q.get('paper_id') and not src:
            p = cur.execute("SELECT name FROM papers WHERE id = ?", (q['paper_id'],)).fetchone()
            if p: src = p['name']
            
        cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, is_difficult, answer_video, grade, analysis) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                    (target_sid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), src, q.get('is_difficult', 0), q.get('answer_video'), q.get('grade'), q.get('analysis')))
        new_qid = cur.lastrowid
        
        # Clone Tags
        old_tags = conn.execute('''
            SELECT t.name FROM question_tags qt
            JOIN tags t ON qt.tag_id = t.id
            WHERE qt.question_id = ?
        ''', (qid,)).fetchall()
        for t_row in old_tags:
            t_name = t_row['name']
            check_tag = cur.execute("SELECT id FROM tags WHERE name = ? AND subject_id = ?", (t_name, target_sid)).fetchone()
            if check_tag:
                new_tid = check_tag['id']
            else:
                cur.execute("INSERT INTO tags (name, subject_id) VALUES (?, ?)", (t_name, target_sid))
                new_tid = cur.lastrowid
            cur.execute("INSERT INTO question_tags (question_id, tag_id) VALUES (?, ?)", (new_qid, new_tid))
            
        # Copy images physically
        imgs = cur.execute("SELECT * FROM question_images WHERE question_id = ?", (qid,)).fetchall()
        for img in imgs:
            old_path = os.path.join(UPLOAD_DIR, img['path'])
            if os.path.exists(old_path):
                new_name = f"{uuid.uuid4().hex}.webp"
                shutil.copy2(old_path, os.path.join(UPLOAD_DIR, new_name))
                cur.execute("INSERT INTO question_images (question_id, path, image_type) VALUES (?, ?, ?)", (new_qid, new_name, img['image_type']))
                
        conn.commit(); conn.close(); return {"status": "ok"}
    except Exception as e:
        print(f"Clone-to-bank error for qid={qid}: {e}")
        conn.close(); return JSONResponse({"error": str(e)}, status_code=500)

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
        tags = conn.execute("SELECT t.name FROM question_tags qt JOIN tags t ON qt.tag_id = t.id WHERE qt.question_id = ?", (q['id'],)).fetchall()
        qd['tags'] = [t['name'] for t in tags]
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

class ExportQuestionsRequest(BaseModel):
    question_ids: List[int]

@app.post("/api/export-questions")
async def export_questions(request: ExportQuestionsRequest, req: Request):
    user = await get_current_user(req)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if not request.question_ids: return JSONResponse({"error": "No questions selected"}, status_code=400)
    
    conn = get_db()
    data = {"type": "questions_batch", "questions": []}
    
    placeholders = ','.join('?' * len(request.question_ids))
    # Verify ownership
    qs = conn.execute(f"SELECT * FROM questions WHERE id IN ({placeholders}) AND user_id = ?", request.question_ids + [user['id']]).fetchall()
    
    for q in qs:
        qd = dict(q)
        qd['images'] = [dict(r) for r in conn.execute("SELECT * FROM question_images WHERE question_id = ?", (q['id'],)).fetchall()]
        tags = conn.execute("SELECT t.name FROM question_tags qt JOIN tags t ON qt.tag_id = t.id WHERE qt.question_id = ?", (q['id'],)).fetchall()
        qd['tags'] = [t['name'] for t in tags]
        data['questions'].append(qd)
    conn.close()
    
    if not data['questions']:
        return JSONResponse({"error": "No valid questions found"}, status_code=404)
        
    fn = f"study_export_{int(datetime.now().timestamp())}.zip"
    fp = f"/tmp/{fn}"
    with zipfile.ZipFile(fp, 'w') as zf:
        zf.writestr('data.json', json.dumps(data, ensure_ascii=False))
        for q in data['questions']:
            for img in q['images']:
                ip = os.path.join(UPLOAD_DIR, img['path'])
                if os.path.exists(ip): zf.write(ip, f"uploads/{img['path']}")
                
    return FileResponse(fp, filename=fn, media_type="application/zip")

@app.post("/api/import-questions")
async def import_questions(request: Request, sid: int = Form(...), file: UploadFile = File(...)):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    conn = get_db()
    # verify subject belongs to user
    sub = conn.execute("SELECT id FROM subjects WHERE id = ? AND user_id = ?", (sid, user['id'])).fetchone()
    if not sub:
        conn.close()
        return JSONResponse({"error": "Subject not found or access denied"}, status_code=404)
        
    tmp = f"/tmp/import_qs_{user['id']}_{file.filename}"
    with open(tmp, "wb") as f: shutil.copyfileobj(file.file, f)
    
    stats = {"total": 0, "success": 0, "duplicate": 0, "failed": 0}
    try:
        with zipfile.ZipFile(tmp, 'r') as zf:
            import_json = json.loads(zf.read('data.json'))
            if import_json.get('type') != 'questions_batch':
                return JSONResponse({"error": "Invalid file format. Select a valid question bundle."}, status_code=400)
            
            cur = conn.cursor()
            
            for q in import_json.get('questions', []):
                stats["total"] += 1
                try:
                    # Duplicate check: same question_text in the same subject
                    # For images only questions, text might be empty. Check exact dupes.
                    q_text = q.get('question_text', '').strip()
                    if q_text:
                        dup = cur.execute("SELECT id FROM questions WHERE subject_id = ? AND user_id = ? AND TRIM(question_text) = ?", (sid, user['id'], q_text)).fetchone()
                        if dup:
                            stats["duplicate"] += 1
                            continue
                    
                    cur.execute(
                        '''INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, 
                           correct_answer, option_a, option_b, option_c, option_d, source, grade, analysis) 
                           VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?,?)''', 
                        (sid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], 
                         q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), 
                         q.get('source'), q.get('grade'), q.get('analysis'))
                    )
                    qid = cur.lastrowid
                    
                    for t_name in q.get('tags', []):
                        check_tag = cur.execute("SELECT id FROM tags WHERE name = ? AND subject_id = ?", (t_name, sid)).fetchone()
                        if check_tag:
                            new_tid = check_tag['id']
                        else:
                            cur.execute("INSERT INTO tags (name, subject_id) VALUES (?, ?)", (t_name, sid))
                            new_tid = cur.lastrowid
                        cur.execute("INSERT INTO question_tags (question_id, tag_id) VALUES (?, ?)", (qid, new_tid))
                    
                    for img in q.get('images', []):
                        cur.execute('INSERT INTO question_images (question_id, path, image_type) VALUES (?,?,?)', (qid, img['path'], img['image_type']))
                        target_path = os.path.join(UPLOAD_DIR, img['path'])
                        if not os.path.exists(target_path):
                            try:
                                with zf.open(f"uploads/{img['path']}") as zsrc:
                                    with open(target_path, "wb") as zdst: shutil.copyfileobj(zsrc, zdst)
                            except Exception as e: 
                                pass
                    stats["success"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    
            conn.commit()
    finally:
        conn.close()
        if os.path.exists(tmp): os.remove(tmp)
        
    return JSONResponse(stats)

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
                q_text = q.get('question_text', '').strip()
                if q_text:
                    dup = cur.execute('SELECT id FROM questions WHERE subject_id = ? AND user_id = ? AND TRIM(question_text) = ?', (sid, user['id'], q_text)).fetchone()
                    if dup: continue
                cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, answer_video, grade, analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, pid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), q.get('source'), q.get('answer_video'), q.get('grade'), q.get('analysis')))
                qid = cur.lastrowid
                for t_name in q.get('tags', []):
                    check_tag = cur.execute("SELECT id FROM tags WHERE name = ? AND subject_id = ?", (t_name, sid)).fetchone()
                    if check_tag:
                        new_tid = check_tag['id']
                    else:
                        cur.execute("INSERT INTO tags (name, subject_id) VALUES (?, ?)", (t_name, sid))
                        new_tid = cur.lastrowid
                    cur.execute("INSERT INTO question_tags (question_id, tag_id) VALUES (?, ?)", (qid, new_tid))
                
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
                        cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, answer_video, grade, analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, pid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), q.get('source'), q.get('answer_video'), q.get('grade'), q.get('analysis')))
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
                    cur.execute('INSERT INTO questions (subject_id, paper_id, user_id, question_text, question_type, correct_answer, option_a, option_b, option_c, option_d, source, answer_video, grade, analysis) VALUES (?,NULL,?,?,?,?,?,?,?,?,?,?,?,?)', (sid, user['id'], q['question_text'], q['question_type'], q['correct_answer'], q.get('option_a'), q.get('option_b'), q.get('option_c'), q.get('option_d'), q.get('source'), q.get('answer_video'), q.get('grade'), q.get('analysis')))
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

@app.post("/admin/user/reset-password")
async def admin_reset_password(request: Request, uid: int = Form(...), new_password: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin': return RedirectResponse("/", status_code=303)
    
    conn = get_db()
    new_hash = pwd_context.hash(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, uid))
    conn.commit()
    conn.close()
    
    return RedirectResponse("/admin/users?msg=reset_pwd_ok", status_code=303)

# ==============================================================================
# V1.3.12: System Diagnosis & Repair (The "Nuclear Option")
# ==============================================================================
@app.get("/api/admin/diagnose")
async def diagnose_db(request: Request):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin':
        return JSONResponse({"error": "Unauthorized"}, status_code=403)
    
    conn = get_db()
    c = conn.cursor()
    
    # Check Schema
    try:
        info = c.execute("PRAGMA table_info(user_question_status)").fetchall()
        cols = [col[1] for col in info]
        missing = []
        if 'history_wrong' not in cols: missing.append('history_wrong')
        
        return {
            "status": "error" if missing else "ok",
            "missing_columns": missing,
            "db_path": DB_PATH
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        conn.close()

@app.post("/api/admin/fix_db")
async def fix_db(request: Request):
    user = await get_current_user(request)
    if not user or user['role'] != 'admin':
        return JSONResponse({"error": "Unauthorized"}, status_code=403)
        
    conn = get_db()
    c = conn.cursor()
    logs = []
    
    try:
        # Check again to be safe
        info = c.execute("PRAGMA table_info(user_question_status)").fetchall()
        cols = [col[1] for col in info]
        
        if 'history_wrong' not in cols:
            logs.append("Missing 'history_wrong'. Adding column...")
            c.execute("ALTER TABLE user_question_status ADD COLUMN history_wrong INTEGER DEFAULT 0")
            logs.append("Column added.")
            
            # Backfill
            logs.append("Backfilling data (wrong_count > 0 -> history_wrong = 1)...")
            c.execute("UPDATE user_question_status SET history_wrong = 1 WHERE wrong_count > 0")
            logs.append("Backfill complete.")
            conn.commit()
        else:
            logs.append("'history_wrong' already exists. Performing sanity check...")
        return {"status": "success", "logs": logs}
    except Exception as e:
        print(f"Fix DB Error: {e}", flush=True)
        conn.rollback()
        return JSONResponse({"status": "error", "logs": logs, "error_msg": str(e)}, status_code=500)
    finally:
        conn.close()

@app.post("/api/admin/test_record")
async def test_record_db(request: Request):
    """Deep Diagnostic: Simulate a full record lifecycle to catch hidden DB errors."""
    user = await get_current_user(request)
    if not user or user['role'] != 'admin':
        return JSONResponse({"error": "Unauthorized"}, status_code=403)
    
    conn = get_db()
    c = conn.cursor()
    logs = []
    
    try:
        # 1. Setup Dummy Data
        test_uid = user['id']
        test_qid = -999 # Non-existent question ID for testing
        
        logs.append(f"Test Start: User={test_uid}, QID={test_qid}")
        
        # 2. Clean up previous test mess if any
        c.execute("DELETE FROM user_question_status WHERE user_id=? AND question_id=?", (test_uid, test_qid))
        conn.commit()
        
        # 3. Test INSERT (Wrong)
        logs.append("Testing INSERT (Wrong)...")
        c.execute("INSERT INTO user_question_status (user_id, question_id, wrong_count, history_wrong, is_difficult) VALUES (?, ?, ?, ?, ?)", 
                  (test_uid, test_qid, 1, 1, 0))
        conn.commit()
        logs.append("INSERT OK.")
        
        # 4. Verify INSERT
        row = c.execute("SELECT * FROM user_question_status WHERE user_id=? AND question_id=?", (test_uid, test_qid)).fetchone()
        if not row: raise Exception("Insert failed silently (Select returned None)")
        if row['history_wrong'] != 1: raise Exception(f"Detailed integrity check failed: history_wrong={row['history_wrong']} (Expected 1)")
        logs.append(f"Verification OK: {dict(row)}")
        
        # 5. Test UPDATE (Correct)
        logs.append("Testing UPDATE (Correct -> wrong_count=0)...")
        c.execute("UPDATE user_question_status SET wrong_count = 0 WHERE user_id = ? AND question_id = ?", (test_uid, test_qid))
        conn.commit()
        row = c.execute("SELECT * FROM user_question_status WHERE user_id=? AND question_id=?", (test_uid, test_qid)).fetchone()
        if row['wrong_count'] != 0: raise Exception(f"Update failed: wrong_count={row['wrong_count']} (Expected 0)")
        logs.append("UPDATE OK.")
        
        # 6. Test UPDATE (Mark Difficult)
        logs.append("Testing UPDATE (Difficult)...")
        c.execute("UPDATE user_question_status SET is_difficult = 1 WHERE user_id = ? AND question_id = ?", (test_uid, test_qid))
        conn.commit()
        row = c.execute("SELECT * FROM user_question_status WHERE user_id=? AND question_id=?", (test_uid, test_qid)).fetchone()
        if row['is_difficult'] != 1: raise Exception(f"Update Difficult failed: is_difficult={row['is_difficult']}")
        logs.append("Difficult OK.")
        
        # 7. Cleanup
        c.execute("DELETE FROM user_question_status WHERE user_id=? AND question_id=?", (test_uid, test_qid))
        conn.commit()
        logs.append("Cleanup OK. Test Passed!")
        
        return {"status": "success", "logs": logs}

    except Exception as e:
        print(f"Deep Diag Error: {e}", flush=True)
        return {"status": "error", "logs": logs, "error_msg": str(e)}
    finally:
        conn.close()


class BatchDistributeRequest(BaseModel):
    question_ids: List[int]
    target_user_id: int

class BatchDeleteRequest(BaseModel):
    question_ids: List[int]

@app.post("/api/batch-distribute")
async def batch_distribute(req: BatchDistributeRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, 401)
    
    conn = get_db()
    try:
        # Check target user
        target_user = conn.execute("SELECT * FROM users WHERE id = ?", (req.target_user_id,)).fetchone()
        if not target_user:
            return JSONResponse({"error": "Target user not found"}, 404)

        stats = {
            "total": len(req.question_ids),
            "success": 0,
            "failed": 0,
            "duplicate": 0
        }
        
        for qid in req.question_ids:
            try:
                # Get Source Q
                q_row = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
                if not q_row: 
                    stats["failed"] += 1
                    continue
                q = dict(q_row)
                
                # Get Source Subject Name
                src_sub = conn.execute("SELECT name FROM subjects WHERE id = ?", (q['subject_id'],)).fetchone()
                if not src_sub: 
                    stats["failed"] += 1
                    continue
                sub_name = src_sub['name']
                
                # Find/Create Target Subject
                # Check if target user has this subject
                tgt_sub = conn.execute("SELECT id FROM subjects WHERE user_id = ? AND name = ?", (req.target_user_id, sub_name)).fetchone()
                if tgt_sub:
                    new_sub_id = tgt_sub['id']
                else:
                    # Create subject
                    cur = conn.cursor()
                    cur.execute("INSERT INTO subjects (name, user_id) VALUES (?, ?)", (sub_name, req.target_user_id))
                    new_sub_id = cur.lastrowid
                
                # V1.3.26: Check for Duplicate (Same Text + Same Subject + Same Target User)
                # We use strict text matching to prevent clutter
                duplicate_check = conn.execute(
                    "SELECT id FROM questions WHERE user_id = ? AND subject_id = ? AND question_text = ?",
                    (req.target_user_id, new_sub_id, q['question_text'])
                ).fetchone()
                
                if duplicate_check:
                    stats["duplicate"] += 1
                    continue
                
                # Clone Question
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO questions (subject_id, question_text, question_type, option_a, option_b, option_c, option_d, correct_answer, difficulty, source, user_id, paper_id, grade, answer_video, analysis)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                ''', (
                    new_sub_id, 
                    q['question_text'], 
                    q['question_type'], 
                    q.get('option_a'), 
                    q.get('option_b'), 
                    q.get('option_c'), 
                    q.get('option_d'), 
                    q['correct_answer'], 
                    q.get('difficulty', 0), 
                    q.get('source'), 
                    req.target_user_id,
                    q.get('grade'),
                    q.get('answer_video'),
                    q.get('analysis')
                ))
                new_qid = cur.lastrowid
                
                # Clone Images
                imgs = conn.execute("SELECT * FROM question_images WHERE question_id = ?", (qid,)).fetchall()
                for img in imgs:
                    # We can reuse the same image path since it's just a file reference. 
                    cur.execute("INSERT INTO question_images (question_id, image_type, path) VALUES (?, ?, ?)", (new_qid, img['image_type'], img['path']))
                
                # Clone Tags
                old_tags = conn.execute('''
                    SELECT t.name FROM question_tags qt
                    JOIN tags t ON qt.tag_id = t.id
                    WHERE qt.question_id = ?
                ''', (qid,)).fetchall()
                for t_row in old_tags:
                    t_name = t_row['name']
                    check_tag = cur.execute("SELECT id FROM tags WHERE name = ? AND subject_id = ?", (t_name, new_sub_id)).fetchone()
                    if check_tag:
                        new_tid = check_tag['id']
                    else:
                        cur.execute("INSERT INTO tags (name, subject_id) VALUES (?, ?)", (t_name, new_sub_id))
                        new_tid = cur.lastrowid
                    cur.execute("INSERT INTO question_tags (question_id, tag_id) VALUES (?, ?)", (new_qid, new_tid))
                    
                stats["success"] += 1
            except Exception as e:
                print(f"Distribute Error (QID {qid}): {e}")
                stats["failed"] += 1
            
        conn.commit()
        return JSONResponse({"status": "success", "stats": stats})
    except Exception as e:
        conn.rollback()
        print(f"Batch Distribute Error: {e}")
        return JSONResponse({"error": str(e)}, 500)
    finally:
        conn.close()

@app.post("/api/batch-delete")
async def batch_delete(req: BatchDeleteRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, 401)
    
    conn = get_db()
    try:
        count = 0
        for qid in req.question_ids:
            # Verify ownership (or admin)
            q = conn.execute("SELECT user_id FROM questions WHERE id = ?", (qid,)).fetchone()
            if not q: continue
            if q['user_id'] != user['id'] and user['role'] != 'admin': continue # Skip if not owner/admin
            
            conn.execute("DELETE FROM questions WHERE id = ?", (qid,))
            conn.execute("DELETE FROM question_images WHERE question_id = ?", (qid,))
            conn.execute("DELETE FROM user_question_status WHERE question_id = ?", (qid,))
            count += 1
        
        conn.commit()
        return JSONResponse({"status": "success", "count": count})
    except Exception as e:
        conn.rollback()
        return JSONResponse({"error": str(e)}, 500)
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
