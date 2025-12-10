import streamlit as st
import pandas as pd
import sqlite3
import json
import random
import os
import urllib.request
import base64
import bcrypt
import time
from contextlib import contextmanager
from io import BytesIO
from datetime import datetime

# --- Kütüphane Kontrolleri ve Importlar ---
try:
    from fpdf import FPDF
except ImportError:
    st.error("❌ FPDF kütüphanesi yüklü değil! Konsola: pip install fpdf")
    st.stop()

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    st.warning("⚠️ Grafikler için 'plotly' gerekli: pip install plotly")

try:
    import xlsxwriter
except ImportError:
    st.warning("⚠️ Excel işlemleri için 'xlsxwriter' gerekli: pip install xlsxwriter")

try:
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    st.warning("⚠️ Word çıktısı için 'python-docx' gerekli: pip install python-docx")

try:
    from streamlit_option_menu import option_menu
except ImportError:
    st.warning("⚠️ Daha şık menü için: pip install streamlit-option-menu")

# --- AI Kütüphaneleri ---
import google.generativeai as genai

# --- API Anahtarını Alma ve Yapılandırma ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except Exception:
    pass 

# ==============================================================================
# 1. AYARLAR VE TASARIM (MODERN UI UPDATE)
# ==============================================================================
st.set_page_config(
    page_title="SSOP Pro: Akademi AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

def local_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

    /* GENEL YAPILANDIRMA */
    html, body, [class*="css"] {
        font-family: 'Poppins', sans-serif;
        background-color: #f0f2f5;
        color: #1f2937;
    }
    
    /* BAŞLIKLAR */
    h1, h2, h3 {
        color: #111827;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    /* SIDEBAR */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e5e7eb;
    }
    
    /* KART TASARIMLARI (Container) */
    .stContainer, .block-container {
        padding-top: 2rem;
    }

    div.stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s ease;
        border: none;
        padding: 0.5rem 1rem;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4F46E5 0%, #4338ca 100%);
        color: white;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2);
    }
    
    div.stButton > button[kind="secondary"] {
        background-color: #f3f4f6;
        color: #374151;
        border: 1px solid #d1d5db;
    }

    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }

    /* INPUT ALANLARI */
    .stTextInput > div > div > input, 
    .stTextArea > div > div > textarea, 
    .stSelectbox > div > div > div {
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        background-color: #ffffff;
        transition: border-color 0.2s;
    }
    
    .stTextInput > div > div > input:focus, 
    .stTextArea > div > div > textarea:focus {
        border-color: #4F46E5;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
    }

    /* CUSTOM KPI CARDS */
    .kpi-card {
        background: white;
        padding: 20px;
        border-radius: 16px;
        border: 1px solid #f3f4f6;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        display: flex;
        align-items: center;
        margin-bottom: 20px;
        transition: transform 0.2s;
    }
    .kpi-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border-color: #4F46E5;
    }
    .kpi-icon {
        width: 50px;
        height: 50px;
        border-radius: 12px;
        background: #EEF2FF;
        color: #4F46E5;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        margin-right: 15px;
    }
    .kpi-content {
        display: flex;
        flex-direction: column;
    }
    .kpi-label {
        font-size: 0.85rem;
        color: #6B7280;
        font-weight: 500;
    }
    .kpi-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #111827;
    }

    /* TABLOLAR */
    [data-testid="stDataFrame"] {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        overflow: hidden;
    }

    /* LOGIN CARD */
    .login-container {
        max-width: 400px;
        margin: 5rem auto;
        padding: 2rem;
        background: white;
        border-radius: 20px;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. VERİTABANI VE ALTYAPI
# ==============================================================================
DB_FILE = "ssop_v4.sqlite"
FONT_FILENAME = "DejaVuSans.ttf"
FONT_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"

@st.cache_resource
def check_and_download_font():
    if not os.path.exists(FONT_FILENAME):
        try:
            with st.spinner("PDF fontları yapılandırılıyor..."):
                urllib.request.urlretrieve(FONT_URL, FONT_FILENAME)
        except Exception:
            pass

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Veritabanı Hatası: {e}")
        raise e
    finally:
        conn.close()

class DatabaseManager:
    def __init__(self):
        self.init_db()

    def init_db(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    Username TEXT PRIMARY KEY,
                    Password TEXT NOT NULL,
                    Role TEXT DEFAULT 'Ogretim Uyesi',
                    FullName TEXT,
                    Photo TEXT
                )
            """)
            if not cursor.execute("SELECT 1 FROM users WHERE Username = 'patron'").fetchone():
                cursor.execute("INSERT INTO users (Username, Password, Role, FullName) VALUES (?, ?, ?, ?)", 
                            ('patron', hash_password('12345'), 'Admin', 'Sistem Yöneticisi'))
                        
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    QuestionID INTEGER PRIMARY KEY AUTOINCREMENT,
                    CourseCode TEXT NOT NULL,
                    TopicArea TEXT NOT NULL,
                    Complexity INTEGER NOT NULL,
                    QuestionType TEXT NOT NULL,
                    Score REAL NOT NULL,
                    QuestionText TEXT NOT NULL,
                    Options TEXT,
                    CorrectAnswer TEXT,
                    CreatedBy TEXT NOT NULL,
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS created_exams (
                    ExamID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Title TEXT,
                    CourseCode TEXT,
                    TotalScore REAL,
                    ExamData TEXT,
                    CreatedBy TEXT,
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def login(self, username, password):
        with get_db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE Username = ?", (username,)).fetchone()
            if user and check_password(password, user['Password']):
                return dict(user)
        return None

    def create_user(self, username, password, fullname, role='Ogretim Uyesi'):
        with get_db_connection() as conn:
            try:
                conn.execute("INSERT INTO users (Username, Password, FullName, Role) VALUES (?, ?, ?, ?)",
                             (username, hash_password(password), fullname, role))
                return True
            except sqlite3.IntegrityError:
                return False

    def reset_password(self, username, new_password):
        with get_db_connection() as conn:
            conn.execute("UPDATE users SET Password = ? WHERE Username = ?", (hash_password(new_password), username))
            return True

    def delete_user(self, username):
        if username == 'admin': return False 
        with get_db_connection() as conn:
            conn.execute("DELETE FROM users WHERE Username = ?", (username,))
            return True

    def get_all_users(self):
        with get_db_connection() as conn:
            return [dict(row) for row in conn.execute("SELECT Username, Role, FullName FROM users").fetchall()]

    def add_question(self, data):
        options_json = json.dumps(data.get('Options', {}), ensure_ascii=False) if data.get('QuestionType') == 'MC' else None
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO questions (CourseCode, TopicArea, Complexity, QuestionType, Score, QuestionText, Options, CorrectAnswer, CreatedBy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['CourseCode'], data['TopicArea'], data['Complexity'], data['QuestionType'], data['Score'], 
                  data['QuestionText'], options_json, data['CorrectAnswer'], data['CreatedBy']))

    def update_question(self, q_id, data):
        options_json = json.dumps(data.get('Options', {}), ensure_ascii=False) if data.get('QuestionType') == 'MC' else None
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE questions SET CourseCode=?, TopicArea=?, Complexity=?, QuestionType=?, Score=?, QuestionText=?, Options=?, CorrectAnswer=?
                WHERE QuestionID=?
            """, (data['CourseCode'], data['TopicArea'], data['Complexity'], data['QuestionType'], data['Score'], 
                  data['QuestionText'], options_json, data['CorrectAnswer'], q_id))

    def bulk_delete_questions(self, q_ids):
        if not q_ids: return
        with get_db_connection() as conn:
            ph = ','.join('?' for _ in q_ids)
            conn.execute(f"DELETE FROM questions WHERE QuestionID IN ({ph})", q_ids)

    def get_questions(self, user_context, course_code=None):
        query = "SELECT * FROM questions WHERE 1=1"
        params = []
        if user_context['Role'] != 'Admin':
            query += " AND CreatedBy = ?"
            params.append(user_context['Username'])
        if course_code:
            query += " AND CourseCode = ?"
            params.append(course_code)
        query += " ORDER BY QuestionID DESC"
        with get_db_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_stats(self, user_context):
        where_clause = ""
        params = []
        if user_context['Role'] != 'Admin':
            where_clause = "WHERE CreatedBy = ?"
            params = [user_context['Username']]
            
        with get_db_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM questions {where_clause}", params).fetchone()[0]
            courses = conn.execute(f"SELECT CourseCode, COUNT(*) as cnt FROM questions {where_clause} GROUP BY CourseCode", params).fetchall()
            avg_diff = conn.execute(f"SELECT AVG(Complexity) FROM questions {where_clause}", params).fetchone()[0] or 0
            exams = conn.execute(f"SELECT COUNT(*) FROM created_exams {where_clause}", params).fetchone()[0]
            types = conn.execute(f"SELECT QuestionType, COUNT(*) FROM questions {where_clause} GROUP BY QuestionType", params).fetchall()
            diffs = conn.execute(f"SELECT Complexity, COUNT(*) FROM questions {where_clause} GROUP BY Complexity", params).fetchall()

            return {
                'total': total, 'courses': dict(courses), 'avg_diff': avg_diff, 
                'exams': exams, 'types': dict(types), 'diffs': dict(diffs)
            }

    def save_exam(self, meta, questions):
        exam_json = json.dumps(questions, ensure_ascii=False)
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO created_exams (Title, CourseCode, TotalScore, ExamData, CreatedBy)
                VALUES (?, ?, ?, ?, ?)
            """, (meta['title'], meta['course'], meta['score'], exam_json, meta['creator']))

    def get_exams(self, user_context):
        query = "SELECT * FROM created_exams"
        params = []
        if user_context['Role'] != 'Admin':
            query += " WHERE CreatedBy = ?"
            params.append(user_context['Username'])
        query += " ORDER BY CreatedAt DESC"
        with get_db_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_db_file_bytes(self):
        with open(DB_FILE, "rb") as f:
            return f.read()

db = DatabaseManager()

# ==============================================================================
# 3. YARDIMCI SINIFLAR (AI / PDF / WORD)
# ==============================================================================
class AIGenerator:
    @staticmethod
    def get_api_key(provider):
        try:
            if provider == "google":
                return st.secrets["GOOGLE_API_KEY"]
            elif provider == "openai":
                return st.secrets["OPENAI_API_KEY"]
        except:
            return os.getenv(f"{provider.upper()}_API_KEY")
        return None

    @staticmethod
    def generate_from_text(text, num_questions=3, provider="google"):
        api_key = AIGenerator.get_api_key(provider)
        session_key_name = f"user_provided_{provider}_key"
        if not api_key and session_key_name in st.session_state:
            api_key = st.session_state[session_key_name]

        if not api_key:
            st.warning(f"⚠️ {provider.title()} servisi için API anahtarı tanımlanmamış.", icon="🤖")
            with st.expander("🔑 Kendi API Anahtarınızı Kullanın", expanded=True):
                user_input = st.text_input(f"{provider.title()} API Key", type="password", key=f"input_{provider}")
                if st.button("Anahtarı Uygula", key=f"btn_{provider}"):
                    if user_input:
                        st.session_state[session_key_name] = user_input
                        st.rerun()
            return [] 

        prompt = f"""
        Sen uzman bir akademik soru hazırlayıcısın. Aşağıdaki metni analiz et ve {num_questions} adet çoktan seçmeli soru oluştur.
        Metin: "{text}"
        Çıktıyı SADECE geçerli bir JSON formatında ver. JSON formatı tam olarak şöyle olmalı:
        [
            {{
                "QuestionText": "Soru metni buraya",
                "Options": {{"A": "Şık 1", "B": "Şık 2", "C": "Şık 3", "D": "Şık 4", "E": "Şık 5"}},
                "CorrectAnswer": "A",
                "Complexity": 2, 
                "Score": 10
            }}
        ]
        """
        try:
            response_text = ""
            if provider == "google":
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                response_text = response.text
            elif provider == "openai":
                # OpenAI implementation placeholder
                pass

            cleaned_json = response_text.replace("```json", "").replace("```", "").strip()
            if not cleaned_json.startswith("["):
                 start = cleaned_json.find("[")
                 end = cleaned_json.rfind("]") + 1
                 if start != -1 and end != -1:
                     cleaned_json = cleaned_json[start:end]

            questions_data = json.loads(cleaned_json)
            final_questions = []
            for q in questions_data:
                final_questions.append({
                    'CourseCode': 'AI-GEN',
                    'TopicArea': 'AI Üretimi',
                    'Complexity': q.get('Complexity', 2),
                    'QuestionType': 'MC',
                    'Score': q.get('Score', 10),
                    'QuestionText': q.get('QuestionText'),
                    'Options': q.get('Options'),
                    'CorrectAnswer': q.get('CorrectAnswer'),
                    'CreatedBy': st.session_state['user']['Username']
                })
            return final_questions
        except Exception as e:
            st.error(f"AI İşlem Hatası: {str(e)}")
            return []

class ExamPDFEngine(FPDF):
    def __init__(self, meta, is_answer_key=False):
        super().__init__()
        self.meta = meta
        self.is_answer_key = is_answer_key
        check_and_download_font()
        self.set_auto_page_break(auto=True, margin=20)
        if os.path.exists(FONT_FILENAME):
            self.add_font('DejaVu', '', FONT_FILENAME, uni=True)
            self.add_font('DejaVu', 'B', FONT_FILENAME, uni=True)
            self.font_family = 'DejaVu'
        else:
            self.font_family = 'Arial' 

    def header(self):
        self.set_font(self.font_family, 'B', 14)
        title_suffix = " - CEVAP ANAHTARI" if self.is_answer_key else ""
        self.cell(0, 10, f"{self.meta['title']}{title_suffix}", 0, 1, 'C')
        
        self.set_font(self.font_family, '', 10)
        self.cell(0, 5, f"Ders: {self.meta['course']} | Tarih: {datetime.now().strftime('%d.%m.%Y')}", 0, 1, 'C')
        self.ln(5)
        
        if not self.is_answer_key:
            self.set_line_width(0.3)
            start_y = self.get_y()
            self.rect(10, start_y, 190, 20)
            self.set_font(self.font_family, '', 9)
            self.set_xy(12, start_y + 2)
            self.cell(90, 5, "Adı Soyadı: ...........................................................", 0, 1)
            self.set_xy(12, start_y + 10)
            self.cell(90, 5, "Numarası: ............................................................", 0, 1)
            self.set_xy(110, start_y + 2)
            self.cell(80, 5, "Bölümü: ............................................................", 0, 1)
            self.set_xy(110, start_y + 10)
            self.cell(80, 5, "İmzası: ..............................................................", 0, 1)
            self.ln(12) 
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_family, '', 8)
        self.cell(0, 10, f'SSOP Pro - Sayfa {self.page_no()}', 0, 0, 'C')

    def generate_content(self, questions):
        self.add_page()
        self.set_font(self.font_family, '', 11)
        for idx, q in enumerate(questions, 1):
            q_text = q['QuestionText']
            score_txt = f"({q['Score']} Puan)" if 'Score' in q else ""
            header = f"{idx}. {q_text} {score_txt}"
            if self.is_answer_key:
                 header = f"{idx}. {q_text}\n   >>> DOĞRU CEVAP: {q.get('CorrectAnswer', '-')}"
            
            if self.get_y() > 250: self.add_page()
            self.set_font(self.font_family, 'B', 11)
            self.multi_cell(0, 6, header)
            self.set_font(self.font_family, '', 11)
            self.ln(2)

            if not self.is_answer_key:
                if q['QuestionType'] == 'MC':
                    opts = json.loads(q['Options']) if isinstance(q['Options'], str) else q['Options']
                    if opts:
                        for k, v in sorted(opts.items()):
                            self.cell(10, 6, f"{k})", 0, 0)
                            self.multi_cell(0, 6, str(v))
                elif q['QuestionType'] == 'TF':
                    self.cell(5)
                    self.cell(30, 8, "◯ Doğru", 0, 0)
                    self.cell(30, 8, "◯ Yanlış", 0, 1)
                else:
                    space = 25
                    if self.get_y() + space > 270: self.add_page()
                    else: self.ln(space)
            self.ln(3)
            if not self.is_answer_key:
                self.set_draw_color(200,200,200)
                self.line(10, self.get_y(), 200, self.get_y())
                self.set_draw_color(0,0,0)
                self.ln(4)
            
    def get_pdf_bytes(self):
        return self.output(dest='S').encode('latin-1')

class ExamDocxEngine:
    def __init__(self, meta, is_answer_key=False):
        self.doc = Document()
        self.meta = meta
        self.is_answer_key = is_answer_key

    def generate(self, questions):
        suffix = " - CEVAP ANAHTARI" if self.is_answer_key else ""
        head = self.doc.add_heading(f"{self.meta['title']}{suffix}", 0)
        head.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        runner = p.add_run(f"Ders: {self.meta['course']} | Tarih: {datetime.now().strftime('%d.%m.%Y')}")
        runner.bold = True
        
        if not self.is_answer_key:
            table = self.doc.add_table(rows=2, cols=2)
            table.style = 'Table Grid'
            table.cell(0, 0).text = "Adı Soyadı:"
            table.cell(0, 1).text = "Bölümü:"
            table.cell(1, 0).text = "Numarası:"
            table.cell(1, 1).text = "İmzası:"
            self.doc.add_paragraph().add_run().add_break()

        for idx, q in enumerate(questions, 1):
            score_txt = f"({q['Score']} Puan)" if 'Score' in q else ""
            q_text = f"{idx}. {q['QuestionText']} {score_txt}"
            self.doc.add_paragraph(q_text, style='List Number')
            
            if self.is_answer_key:
                p_ans = self.doc.add_paragraph()
                run = p_ans.add_run(f"DOĞRU CEVAP: {q.get('CorrectAnswer', '-')}")
                run.bold = True
                run.font.color.rgb = RGBColor(255, 0, 0) 
            
            if not self.is_answer_key:
                if q['QuestionType'] == 'MC':
                    opts = json.loads(q['Options']) if isinstance(q['Options'], str) else q['Options']
                    if opts:
                        for k, v in sorted(opts.items()):
                            self.doc.add_paragraph(f"{k}) {v}", style='List 2')
                elif q['QuestionType'] == 'TF':
                    self.doc.add_paragraph("◯ Doğru    ◯ Yanlış")
                else:
                    self.doc.add_paragraph("\n"*3)

        buffer = BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()

# ==============================================================================
# 4. YARDIMCI FONKSİYONLAR
# ==============================================================================
def get_excel_template():
    df = pd.DataFrame(columns=[
        'CourseCode', 'TopicArea', 'QuestionType', 'Complexity', 
        'Score', 'QuestionText', 'CorrectAnswer', 
        'OptionA', 'OptionB', 'OptionC', 'OptionD', 'OptionE'
    ])
    df.loc[0] = ['MAT101', 'Türev', 'MC', 2, 10, 'x^2 türevi nedir?', '2x', '2x', 'x', '0', '1', '']
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sablon')
    return output.getvalue()

def export_questions_to_excel(questions):
    if not questions: return None
    df = pd.DataFrame(questions)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sorular')
    return output.getvalue()

def render_kpi_card(title, value, icon, color="blue"):
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">
            {icon}
        </div>
        <div class="kpi-content">
            <span class="kpi-label">{title}</span>
            <span class="kpi-value">{value}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. SAYFALAR
# ==============================================================================
def login_page():
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div class="login-container">
            <h1 style="color:#4F46E5; margin-bottom:10px;">🎓 SSOP Pro</h1>
            <p style="color:#6B7280; font-size:14px; margin-bottom:30px;">
                Akademik Sınav Yönetim Sistemi v4.0
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            st.markdown("### Giriş Yap")
            user = st.text_input("Kullanıcı Adı", placeholder="Kullanıcı adınız")
            pwd = st.text_input("Şifre", type="password", placeholder="••••••")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Sisteme Giriş Yap", type="primary", use_container_width=True):
                account = db.login(user, pwd)
                if account:
                    st.session_state['user'] = account
                    st.rerun()
                else:
                    st.error("❌ Hatalı kullanıcı adı veya şifre!")
        


def dashboard_page():
    user = st.session_state['user']
    st.markdown(f"## 👋 Hoşgeldin, <span style='color:#4F46E5'>{user['FullName']}</span>", unsafe_allow_html=True)
    st.markdown("Sistem durum özeti ve performans metrikleri aşağıdadır.")
    
    stats = db.get_stats(user)
    
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi_card("Toplam Soru", stats['total'], "📚")
    with c2: render_kpi_card("Aktif Ders", len(stats['courses']), "🔖")
    with c3: render_kpi_card("Ortalama Zorluk", f"{stats['avg_diff']:.1f}", "📈")
    with c4: render_kpi_card("Üretilen Sınav", stats['exams'], "📝")
    
    st.markdown("---")
    
    col_g1, col_g2 = st.columns([2, 1])
    with col_g1:
        st.subheader("📊 Ders Bazlı İçerik Analizi")
        if stats['courses']:
            df = pd.DataFrame(list(stats['courses'].items()), columns=['Ders', 'Soru'])
            fig = px.bar(
                df, x='Ders', y='Soru', color='Soru', text='Soru', 
                color_continuous_scale='Purples', title="" 
            )
            fig.update_layout(
                xaxis_title="Ders Kodu", 
                yaxis_title="Soru Sayısı",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=10, l=10, r=10, b=10)
            )
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("Görüntülenecek veri yok.")
            
    with col_g2:
        st.subheader("🧩 Dağılım")
        t1, t2 = st.tabs(["Soru Tipleri", "Zorluk"])
        with t1:
            if stats.get('types'):
                df_t = pd.DataFrame(list(stats['types'].items()), columns=['Tip', 'Adet'])
                t_map = {'MC': 'Çoktan Seçmeli', 'TF': 'Doğru/Yanlış', 'CL': 'Klasik'}
                df_t['Tip'] = df_t['Tip'].map(t_map).fillna(df_t['Tip'])
                fig3 = px.pie(df_t, values='Adet', names='Tip', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig3.update_layout(showlegend=False, margin=dict(t=0, l=0, r=0, b=0))
                st.plotly_chart(fig3, use_container_width=True)
            else: st.info("Veri yok.")
        with t2:
            if stats.get('diffs'):
                df_d = pd.DataFrame(list(stats['diffs'].items()), columns=['Zorluk', 'Adet'])
                d_map = {1: 'Kolay', 2: 'Orta', 3: 'Zor'}
                df_d['Zorluk'] = df_d['Zorluk'].map(d_map)
                fig_d = px.pie(df_d, values='Adet', names='Zorluk', hole=0.6, color_discrete_sequence=px.colors.sequential.RdBu)
                fig_d.update_layout(showlegend=False, margin=dict(t=0, l=0, r=0, b=0))
                st.plotly_chart(fig_d, use_container_width=True)
            else: st.info("Veri yok.")

def question_bank_page():
    user = st.session_state['user']
    c_head, c_btn = st.columns([3,1])
    with c_head: st.title("🗃️ Soru Bankası")
    
    all_q = db.get_questions(user)
    if not all_q:
        st.warning("📭 Soru bankası boş. 'Soru Ekle' menüsünden içerik ekleyin.")
        return

    with c_btn:
        excel_data = export_questions_to_excel(all_q)
        if excel_data:
            st.download_button(
                label="📥 Excel İndir",
                data=excel_data,
                file_name=f"ssop_sorular_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    with st.expander("🔎 Filtreleme & Arama", expanded=True):
        c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
        courses = sorted(list(set(q['CourseCode'] for q in all_q)))
        topics = sorted(list(set(q['TopicArea'] for q in all_q if q['TopicArea'])))
        
        sel_course = c1.multiselect("Ders", courses)
        sel_topic = c2.multiselect("Konu", topics)
        type_map = {"MC": "Çoktan Seçmeli", "TF": "Doğru/Yanlış", "CL": "Klasik"}
        sel_type = c3.multiselect("Tip", options=["MC", "TF", "CL"], format_func=lambda x: type_map.get(x, x))
        search_txt = c4.text_input("Ara...", placeholder="Soru metni içinde ara")
    
    df = pd.DataFrame(all_q)
    df['QuestionTypeDisplay'] = df['QuestionType'].map(type_map).fillna(df['QuestionType'])

    if sel_course: df = df[df['CourseCode'].isin(sel_course)]
    if sel_topic: df = df[df['TopicArea'].isin(sel_topic)]
    if sel_type: df = df[df['QuestionType'].isin(sel_type)]
    if search_txt: df = df[df['QuestionText'].str.contains(search_txt, case=False)]
    
    st.markdown(f"**Sonuç:** {len(df)} kayıt bulundu.", unsafe_allow_html=True)
    
    df_editor = df.copy()
    df_editor.insert(0, "Seç", False)
    
    edited_df = st.data_editor(
        df_editor[['Seç', 'QuestionID', 'CourseCode', 'TopicArea', 'QuestionTypeDisplay', 'Complexity', 'Score', 'QuestionText']],
        column_config={
            "Seç": st.column_config.CheckboxColumn(required=True),
            "QuestionID": st.column_config.NumberColumn("ID", width="small"),
            "QuestionText": st.column_config.TextColumn("Soru Metni", width="large"),
        },
        use_container_width=True,
        hide_index=True,
        height=400,
        disabled=['QuestionID', 'CourseCode', 'TopicArea', 'QuestionTypeDisplay', 'Complexity', 'Score', 'QuestionText']
    )
    
    selected_rows = edited_df[edited_df['Seç']]
    
    if not selected_rows.empty:
        col_act1, col_act2 = st.columns([1, 5])
        with col_act1:
            if st.button(f"🗑️ Sil ({len(selected_rows)})", type="primary"):
                ids_to_del = selected_rows['QuestionID'].tolist()
                db.bulk_delete_questions(ids_to_del)
                st.toast(f"{len(ids_to_del)} soru silindi!", icon="✅")
                st.rerun()

    st.markdown("---")
    with st.expander("✏️ Soru Düzenle (ID ile)", expanded=False):
        qid = st.number_input("Düzenlenecek Soru ID:", min_value=0, step=1)
        if qid > 0:
            q_data = next((q for q in all_q if q['QuestionID'] == qid), None)
            if q_data:
                with st.form("edit_q"):
                    n_text = st.text_area("Soru Metni", value=q_data['QuestionText'])
                    c_e1, c_e2 = st.columns(2)
                    n_score = c_e1.number_input("Puan", value=float(q_data['Score']))
                    n_ans = c_e2.text_input("Doğru Cevap", value=q_data['CorrectAnswer'])
                    
                    if st.form_submit_button("Değişiklikleri Kaydet"):
                        q_data.update({'QuestionText': n_text, 'Score': n_score, 'CorrectAnswer': n_ans})
                        db.update_question(qid, q_data)
                        st.success("Başarıyla güncellendi!")
                        time.sleep(1)
                        st.rerun()
            else:
                st.error("Bu ID ile soru bulunamadı.")

def add_question_page():
    st.title("➕ Soru Ekleme Merkezi")
    t1, t2, t3 = st.tabs(["✍️ Manuel Ekleme", "📂 Excel Yükleme", "🤖 AI Asistanı"])
    
    type_map = {"MC": "Çoktan Seçmeli", "TF": "Doğru/Yanlış", "CL": "Klasik"}

    # --- TAB 1: MANUEL ---
    with t1:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            qc = c1.text_input("Ders Kodu (Örn: MAT101)").upper()
            qt = c2.text_input("Konu (Örn: Türev)", "Genel")
            qdiff = c3.select_slider("Zorluk", options=[1, 2, 3], value=2, format_func=lambda x: {1:"Kolay", 2:"Orta", 3:"Zor"}[x])
            qtype = c4.selectbox("Tip", options=["MC", "TF", "CL"], format_func=lambda x: type_map.get(x, x))
            
            with st.form("add_form", clear_on_submit=True):
                st.markdown("**Soru Metni** (Matematiksel ifadeler için LaTeX: `$x^2$`)")
                qtext = st.text_area("Soru", height=120, label_visibility="collapsed")
                
                opts = {}
                if qtype == "MC":
                    st.info("Seçenekler:")
                    oc1, oc2 = st.columns(2)
                    opts['A'] = oc1.text_input("A")
                    opts['B'] = oc2.text_input("B")
                    opts['C'] = oc1.text_input("C")
                    opts['D'] = oc2.text_input("D")
                    opts['E'] = oc1.text_input("E (Opsiyonel)")
                    opts = {k:v for k,v in opts.items() if v}
                
                fc1, fc2 = st.columns(2)
                qans = fc1.text_input("Doğru Cevap (Örn: A veya Doğru)")
                qscore = fc2.number_input("Puan", 1, 100, 10)
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("Soru Ekle", type="primary"):
                    if qc and qtext:
                        db.add_question({
                            'CourseCode': qc, 'TopicArea': qt, 'Complexity': qdiff,
                            'QuestionType': qtype, 'Score': qscore, 'QuestionText': qtext,
                            'Options': opts, 'CorrectAnswer': qans, 'CreatedBy': st.session_state['user']['Username']
                        })
                        st.toast("Soru başarıyla eklendi!", icon="🎉")
                    else:
                        st.error("Ders Kodu ve Soru Metni zorunludur.")

    # --- TAB 2: EXCEL ---
    with t2:
        c_dl, c_ul = st.columns([1, 2])
        with c_dl:
            st.info("Formatı bilmiyor musunuz?")
            st.download_button(
                label="📥 Şablon İndir",
                data=get_excel_template(),
                file_name="soru_yukleme_sablonu.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        with c_ul:
            st.markdown("### Dosya Yükle")
            up_file = st.file_uploader("Excel Dosyası (.xlsx)", type=['xlsx'])
            if up_file and st.button("Soruları İçeri Aktar", type="primary"):
                try:
                    df = pd.read_excel(up_file).fillna('')
                    cnt = 0
                    with st.spinner('Sorular işleniyor...'):
                        for _, row in df.iterrows():
                            opts = {}
                            if str(row['QuestionType']) == 'MC':
                                for letter in ['A','B','C','D','E']:
                                    val = row.get(f'Option{letter}')
                                    if pd.notna(val) and str(val).strip(): opts[letter] = str(val)
                            
                            db.add_question({
                                'CourseCode': str(row['CourseCode']), 'TopicArea': str(row.get('TopicArea','Genel')),
                                'Complexity': int(row.get('Complexity', 2)), 'QuestionType': str(row['QuestionType']),
                                'Score': float(row.get('Score', 10)), 'QuestionText': str(row['QuestionText']),
                                'Options': opts, 'CorrectAnswer': str(row.get('CorrectAnswer', '')),
                                'CreatedBy': st.session_state['user']['Username']
                            })
                            cnt += 1
                    st.success(f"✅ {cnt} soru başarıyla içeri aktarıldı!")
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")

    # --- TAB 3: AI ---
    with t3:
        st.markdown("### 🤖 Yapay Zeka ile Soru Üretimi")
        st.info("Metni analiz eder, sınav formatına uygun sorular çıkarır.")
        
        ai_provider = st.radio("AI Model:", ["Google Gemini", "OpenAI GPT-4o"], horizontal=True)
        provider_code = "google" if "Google" in ai_provider else "openai"
        
        source_text = st.text_area("Kaynak Metin:", height=200, placeholder="Ders notlarını buraya yapıştırın...")
        c_ai1, c_ai2 = st.columns(2)
        num_q = c_ai1.slider("Soru Sayısı", 1, 10, 3)
        
        if st.button("🚀 Üretmeye Başla", type="primary"):
            if len(source_text) < 50:
                st.warning("⚠️ Lütfen daha uzun bir metin girin.")
            else:
                with st.spinner(f"{ai_provider} çalışıyor..."):
                    generated_qs = AIGenerator.generate_from_text(source_text, num_q, provider_code)
                    if generated_qs:
                        st.session_state['ai_questions'] = generated_qs
                        st.success(f"✅ {len(generated_qs)} soru üretildi!")
                    
        if 'ai_questions' in st.session_state and st.session_state['ai_questions']:
            st.write("---")
            for idx, q in enumerate(st.session_state['ai_questions']):
                with st.container():
                    st.markdown(f"**Soru {idx+1}:** {q['QuestionText']}")
                    cols = st.columns(2)
                    opts = q['Options']
                    for i, (k, v) in enumerate(opts.items()):
                        cols[i%2].write(f"**{k})** {v}")
                    st.caption(f"Doğru Cevap: {q['CorrectAnswer']} | Zorluk: {q['Complexity']}")
                    if st.button(f"💾 Ekle (Soru {idx+1})", key=f"ai_{idx}"):
                        db.add_question(q)
                        st.toast(f"Soru {idx+1} eklendi!")
                st.divider()

def exam_create_page():
    st.title("⚙️ Sınav Sihirbazı")
    user = st.session_state['user']
    
    if 'exam_stage' not in st.session_state:
        st.session_state['exam_stage'] = 'setup'
        st.session_state['selected_questions'] = []

    # ADIM 1: KURULUM
    if st.session_state['exam_stage'] == 'setup':
        st.info("Adım 1/3: Sınav Ayarları")
        pool_test = db.get_questions(user) 
        courses = sorted(list(set(q['CourseCode'] for q in pool_test)))
        
        if not courses:
            st.warning("⚠️ Soru havuzu boş.")
            return

        c1, c2 = st.columns(2)
        sel_course = c1.selectbox("Ders", courses)
        sel_title = c2.text_input("Sınav Başlığı", f"{sel_course} Final Sınavı")
        
        c3, c4 = st.columns(2)
        sel_score = c3.number_input("Toplam Puan", value=100)
        method = c4.radio("Yöntem", ["🎲 Rastgele", "✅ Manuel Seçim"], horizontal=True)
        
        if st.button("İleri: Soru Seçimi ➡️", type="primary"):
            st.session_state['exam_meta'] = {'course': sel_course, 'title': sel_title, 'score': sel_score, 'method': method, 'creator': user['Username']}
            st.session_state['exam_stage'] = 'selection'
            st.rerun()

    # ADIM 2: SEÇİM
    elif st.session_state['exam_stage'] == 'selection':
        st.info("Adım 2/3: Soruların Belirlenmesi")
        meta = st.session_state['exam_meta']
        pool = db.get_questions(user, meta['course'])
        
        if meta['method'].startswith("🎲"):
            st.subheader("Rastgele Dağılım")
            c1, c2, c3 = st.columns(3)
            d1 = [q for q in pool if q['Complexity'] == 1]
            d2 = [q for q in pool if q['Complexity'] == 2]
            d3 = [q for q in pool if q['Complexity'] == 3]
            
            n1 = c1.number_input(f"Kolay (Max: {len(d1)})", 0, len(d1), 0)
            n2 = c2.number_input(f"Orta (Max: {len(d2)})", 0, len(d2), 0)
            n3 = c3.number_input(f"Zor (Max: {len(d3)})", 0, len(d3), 0)
            
            if st.button("Soruları Getir ve Önizle"):
                sel = random.sample(d1, n1) + random.sample(d2, n2) + random.sample(d3, n3)
                if sel:
                    st.session_state['selected_questions'] = sel
                    st.session_state['exam_stage'] = 'preview'
                    st.rerun()
                else: st.warning("Lütfen soru sayısı girin.")
        else:
            df_pool = pd.DataFrame(pool)
            df_pool.insert(0, 'Seç', False)
            st.write("Listeden soruları seçiniz:")
            
            ed = st.data_editor(
                df_pool[['Seç', 'QuestionText', 'Complexity', 'Score']], 
                disabled=["QuestionText", "Score", "Complexity"],
                use_container_width=True,
                height=400
            )
            
            if st.button("Seçimi Onayla"):
                sel_indices = ed[ed['Seç']].index
                sel = [pool[i] for i in sel_indices]
                if sel:
                    st.session_state['selected_questions'] = sel
                    st.session_state['exam_stage'] = 'preview'
                    st.rerun()
                else: st.warning("Soru seçmediniz.")

        if st.button("⬅️ Geri Dön"):
             st.session_state['exam_stage'] = 'setup'
             st.rerun()

    # ADIM 3: ÖNİZLEME
    elif st.session_state['exam_stage'] == 'preview':
        st.info("Adım 3/3: Puanlama ve Çıktı")
        qs = st.session_state['selected_questions']
        meta = st.session_state['exam_meta']
        
        for q in qs:
            if 'BaseScore' not in q: q['BaseScore'] = q['Score']
            
        col_prev1, col_prev2 = st.columns([2, 1])
        with col_prev1:
            st.subheader("📝 Önizleme")
            sm = st.radio("Puanlama", ["🎯 Hedefe Orantıla", "⚖️ Eşit Dağıt", "✍️ Orijinal Puanlar"], horizontal=True)
            tgt = meta['score']
            
            if sm.startswith("🎯"):
                tot = sum(q['BaseScore'] for q in qs)
                if tot: 
                    f = tgt/tot
                    for q in qs: q['Score'] = round(q['BaseScore']*f, 2)
            elif sm.startswith("⚖️"):
                avg = tgt/len(qs)
                for q in qs: q['Score'] = round(avg, 2)
            elif sm.startswith("✍️"):
                for q in qs: q['Score'] = q['BaseScore']

            cur_tot = sum(q['Score'] for q in qs)
            st.caption(f"Toplam Puan: {cur_tot:.2f} (Hedef: {tgt})")
            
            for i, q in enumerate(qs, 1):
                st.markdown(f"**{i}. {q['QuestionText']}** ({q['Score']} Puan)")
                st.divider()

        with col_prev2:
            st.subheader("İşlemler")
            if st.button("💾 Sınavı Oluştur", type="primary", use_container_width=True):
                db.save_exam(meta, qs)
                st.session_state['final'] = {'meta': meta, 'q': qs}
                st.session_state['exam_stage'] = 'finish'
                st.rerun()
            
            if st.button("İptal", use_container_width=True):
                st.session_state['exam_stage'] = 'setup'
                st.rerun()

    # BİTİŞ
    elif st.session_state['exam_stage'] == 'finish':
        st.success("✅ Sınav Başarıyla Oluşturuldu!")
        d = st.session_state['final']
        
        pdf = ExamPDFEngine(d['meta'])
        pdf.generate_content(d['q'])
        pdf_bytes = pdf.get_pdf_bytes()
        
        pdfk = ExamPDFEngine(d['meta'], True)
        pdfk.generate_content(d['q'])
        pdfk_bytes = pdfk.get_pdf_bytes()
        
        try:
            docx_eng = ExamDocxEngine(d['meta'])
            docx_bytes = docx_eng.generate(d['q'])
            
            docxk_eng = ExamDocxEngine(d['meta'], True)
            docxk_bytes = docxk_eng.generate(d['q'])
            has_word = True
        except:
            has_word = False

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 📄 PDF")
            st.download_button("Sınav (PDF)", pdf_bytes, "sinav.pdf", "application/pdf", use_container_width=True)
            st.download_button("Cevaplar (PDF)", pdfk_bytes, "cevaplar.pdf", "application/pdf", use_container_width=True)
        
        with c2:
            st.markdown("### 📝 Word")
            if has_word:
                st.download_button("Sınav (Word)", docx_bytes, "sinav.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
                st.download_button("Cevaplar (Word)", docxk_bytes, "cevaplar.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
        
        st.markdown("---")
        if st.button("Yeni Sınav"):
            del st.session_state['exam_stage']
            st.rerun()

def history_page():
    user = st.session_state['user']
    st.title("🗂️ Sınav Arşivi")
    exams = db.get_exams(user)
    
    for ex in exams:
        with st.expander(f"📅 {ex['CreatedAt'][:16]} | {ex['Title']}"):
            q_data = json.loads(ex['ExamData'])
            c1, c2 = st.columns(2)
            if c1.button("PDF İndir", key=f"pdf_{ex['ExamID']}"):
                pdf = ExamPDFEngine({'title': ex['Title'], 'course': ex['CourseCode'], 'score': ex['TotalScore']})
                pdf.generate_content(q_data)
                st.download_button("📥 İndir", pdf.get_pdf_bytes(), f"sinav_{ex['ExamID']}.pdf", "application/pdf")
            
            if c2.button("Word İndir", key=f"docx_{ex['ExamID']}"):
                try:
                    eng = ExamDocxEngine({'title': ex['Title'], 'course': ex['CourseCode'], 'score': ex['TotalScore']})
                    b = eng.generate(q_data)
                    st.download_button("📥 İndir", b, f"sinav_{ex['ExamID']}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                except: st.error("Word modülü eksik.")

def admin_page():
    if st.session_state['user']['Role'] != 'Admin':
        st.error("Yetkisiz!")
        return

    st.title("👥 Yönetim Paneli")
    t1, t2, t3 = st.tabs(["Kullanıcılar", "Şifreler", "Yedek"])
    
    with t1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("Kullanıcı Ekle")
            with st.form("add_user"):
                new_user = st.text_input("Kullanıcı Adı")
                new_pass = st.text_input("Şifre", type="password")
                new_name = st.text_input("Ad Soyad")
                if st.form_submit_button("Ekle", type="primary"):
                    if db.create_user(new_user, new_pass, new_name):
                        st.success("Eklendi.")
                        time.sleep(1)
                        st.rerun()
                    else: st.error("Kullanıcı adı kullanımda.")
        
        with c2:
            st.subheader("Kullanıcı Listesi")
            users = db.get_all_users()
            st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)

            # --- KULLANICI SİLME BÖLÜMÜ EKLENDİ ---
            st.markdown("---")
            st.subheader("🗑️ Kullanıcı Sil")
            
            # Admin kendini silemesin diye filtreliyoruz
            users_to_delete = [u['Username'] for u in users if u['Username'] != 'admin']
            
            if users_to_delete:
                with st.container():
                    st.warning("Dikkat: Bu işlem geri alınamaz!")
                    col_del1, col_del2 = st.columns([3, 1])
                    selected_user_to_delete = col_del1.selectbox("Silinecek Kullanıcıyı Seç", users_to_delete, label_visibility="collapsed")
                    
                    if col_del2.button("Sil", type="primary"):
                        db.delete_user(selected_user_to_delete)
                        st.success(f"{selected_user_to_delete} silindi.")
                        time.sleep(1)
                        st.rerun()
            else:
                st.info("Silinecek başka kullanıcı yok.")


    with t2:
        st.subheader("🔑 Şifre Sıfırla")
        users = db.get_all_users()
        u_reset = st.selectbox("Kullanıcı", [u['Username'] for u in users])
        new_p = st.text_input("Yeni Şifre", type="password")
        if st.button("Güncelle"):
            db.reset_password(u_reset, new_p)
            st.success("Güncellendi.")
    
    with t3:
        st.subheader("💾 Veritabanı Yedeği")
        st.download_button("Yedeği İndir (.sqlite)", db.get_db_file_bytes(), "backup.sqlite", "application/x-sqlite3")

# ==============================================================================
# 6. ANA AKIŞ
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        local_css()
        login_page()
        return

    user = st.session_state['user']
    local_css()

    with st.sidebar:
        seed = user['FullName'].replace(' ', '')
        profile_image = f"https://api.dicebear.com/9.x/notionists/svg?seed={seed}&backgroundColor=eef2ff"
        
        st.markdown(f"""
            <div style="background: white; padding: 20px; border-radius: 12px; border: 1px solid #e5e7eb; text-align: center; margin-bottom: 20px;">
                <img src="{profile_image}" style="width: 80px; height: 80px; border-radius: 50%; margin-bottom: 10px;">
                <h3 style="margin: 0; font-size: 16px; font-weight: 600;">{user['FullName']}</h3>
                <p style="margin: 0; color: #6b7280; font-size: 12px;">{user['Role']}</p>
            </div>
        """, unsafe_allow_html=True)

        menu_items = ["Gösterge Paneli", "Soru Bankası", "Soru Ekle", "Sınav Oluştur", "Arşiv"]
        menu_icons = ["grid-1x2", "collection", "plus-circle", "pencil", "archive"]
        
        if user["Role"] == "Admin":
            menu_items.append("Yönetim")
            menu_icons.append("gear")

        selected = option_menu(
            menu_title=None,
            options=menu_items,
            icons=menu_icons,
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "icon": {"color": "#6B7280", "font-size": "14px"}, 
                "nav-link": {"font-size": "14px", "text-align": "left", "margin": "5px", "color": "#374151"},
                "nav-link-selected": {"background-color": "#4F46E5", "color": "white", "font-weight": "500"},
            }
        )

        st.markdown("---")
        if st.button("Çıkış Yap", key="logout"):
            del st.session_state['user']
            if 'exam_stage' in st.session_state: del st.session_state['exam_stage']
            st.rerun()

    if selected == "Gösterge Paneli": dashboard_page()
    elif selected == "Soru Bankası": question_bank_page()
    elif selected == "Soru Ekle": add_question_page()
    elif selected == "Sınav Oluştur": exam_create_page()
    elif selected == "Arşiv": history_page()
    elif selected == "Yönetim": admin_page()

if __name__ == "__main__":

    main()
