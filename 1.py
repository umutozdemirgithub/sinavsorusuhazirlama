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
import zipfile
import re  # Regex eklendi
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

try:
    import PyPDF2
except ImportError:
    st.warning("⚠️ PDF okuma için 'PyPDF2' gerekli: pip install PyPDF2")

# --- AI Kütüphaneleri ---
import google.generativeai as genai

# --- API Anahtarını Alma ve Yapılandırma ---
try:
    # st.secrets varsayılan olarak okunur
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except Exception:
    # Eğer secrets yoksa, kullanıcı girişi kontrol edilecek
    api_key = None

# ==============================================================================
# 1. AYARLAR VE TASARIM
# ==============================================================================
st.set_page_config(
    page_title="SSOP Pro v5.0: Enterprise",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

def local_css():
    st.markdown("""
    <style>
    /* GENEL */
    .stApp { background-color: #f0f2f6; }
    
    /* SIDEBAR */
    [data-testid="stSidebar"] { background-color: #2c3e50; }
    
    /* INPUT & FORMS */
    .stTextInput > div > div > input { border-radius: 8px; border: 1px solid #ddd; }
    
    /* KULLANICI KARTI */
    .user-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        padding: 20px;
        border-radius: 15px;
        color: #333;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid rgba(0,0,0,0.05);
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    .profile-pic {
        width: 80px; height: 80px; border-radius: 50%;
        border: 3px solid #3498db; object-fit: cover; margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. VERİTABANI VE ALTYAPI
# ==============================================================================
DB_FILE = "ssop_v5.sqlite"
FONT_FILENAME = "DejaVuSans.ttf"
FONT_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"

@st.cache_resource
def check_and_download_font():
    """Font dosyasını sadece yoksa indirir ve cache mekanizmasını kullanır."""
    if not os.path.exists(FONT_FILENAME):
        try:
            urllib.request.urlretrieve(FONT_URL, FONT_FILENAME)
        except Exception:
            pass

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return False

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
            
            # 1. Tabloları oluştur
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    Username TEXT PRIMARY KEY,
                    Password TEXT NOT NULL,
                    Role TEXT DEFAULT 'Teacher',
                    FullName TEXT,
                    Photo TEXT
                )
            """)
            if not cursor.execute("SELECT 1 FROM users WHERE Username = 'admin'").fetchone():
                cursor.execute("INSERT INTO users (Username, Password, Role, FullName) VALUES (?, ?, ?, ?)", 
                               ('admin', hash_password('admin'), 'Admin', 'Sistem Yöneticisi'))
            
            # --- MIGRATION: LastEditedBy/At ekleme ---
            cursor.execute("PRAGMA table_info(questions)")
            q_cols = [info[1] for info in cursor.fetchall()]

            if 'LastEditedBy' not in q_cols:
                try:
                    cursor.execute("ALTER TABLE questions ADD COLUMN LastEditedBy TEXT")
                    cursor.execute("ALTER TABLE questions ADD COLUMN LastEditedAt TIMESTAMP")
                except Exception:
                    pass
            
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
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    LastEditedBy TEXT,
                    LastEditedAt TIMESTAMP
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
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    IsArchived INTEGER DEFAULT 0,
                    Status TEXT DEFAULT 'Final'
                )
            """)

            # --- MIGRATION / GÜNCELLEME KONTROLÜ (Eski Sütunlar) ---
            cursor.execute("PRAGMA table_info(created_exams)")
            columns = [info[1] for info in cursor.fetchall()]
            
            if 'TotalScore' not in columns:
                try: cursor.execute("ALTER TABLE created_exams ADD COLUMN TotalScore REAL DEFAULT 0")
                except Exception: pass
            if 'IsArchived' not in columns:
                try: cursor.execute("ALTER TABLE created_exams ADD COLUMN IsArchived INTEGER DEFAULT 0")
                except Exception: pass
            if 'Status' not in columns:
                try: cursor.execute("ALTER TABLE created_exams ADD COLUMN Status TEXT DEFAULT 'Final'")
                except Exception: pass
                
    def create_user(self, username, password, fullname, role):
        hashed_password = hash_password(password)
        with get_db_connection() as conn:
            try:
                conn.execute("INSERT INTO users (Username, Password, FullName, Role) VALUES (?, ?, ?, ?)", 
                             (username, hashed_password, fullname, role))
                return True
            except sqlite3.IntegrityError:
                return False # Kullanıcı adı zaten var

    def delete_user(self, username):
        """Kullanıcı silme fonksiyonu eklendi."""
        if username == 'admin': return False # Admin silinmesini engelle
        with get_db_connection() as conn:
            conn.execute("DELETE FROM users WHERE Username = ?", (username,))
        return True

    def login(self, username, password):
        with get_db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE Username = ?", (username,)).fetchone()
            if user and check_password(password, user['Password']):
                return dict(user)
        return None

    def add_question(self, data):
        options_json = json.dumps(data.get('Options', {}), ensure_ascii=False) if data.get('QuestionType') == 'MC' else None
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO questions (CourseCode, TopicArea, Complexity, QuestionType, Score, QuestionText, Options, CorrectAnswer, CreatedBy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['CourseCode'], data['TopicArea'], data['Complexity'], data['QuestionType'], data['Score'], 
                  data['QuestionText'], options_json, data['CorrectAnswer'], data['CreatedBy']))

    def update_question(self, q_id, data, editor_username):
        options_json = json.dumps(data.get('Options', {}), ensure_ascii=False) if data.get('QuestionType') == 'MC' else None
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE questions SET CourseCode=?, TopicArea=?, Complexity=?, QuestionType=?, Score=?, QuestionText=?, Options=?, CorrectAnswer=?, LastEditedBy=?, LastEditedAt=?
                WHERE QuestionID=?
            """, (data['CourseCode'], data['TopicArea'], data['Complexity'], data['QuestionType'], data['Score'], 
                  data['QuestionText'], options_json, data['CorrectAnswer'], editor_username, datetime.now(), q_id))

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
            topics = conn.execute(f"SELECT TopicArea, COUNT(*) as cnt FROM questions {where_clause} GROUP BY TopicArea", params).fetchall()
            avg_diff = conn.execute(f"SELECT AVG(Complexity) FROM questions {where_clause}", params).fetchone()[0] or 0
            exams = conn.execute(f"SELECT COUNT(*) FROM created_exams {where_clause}", params).fetchone()[0]
            types = conn.execute(f"SELECT QuestionType, COUNT(*) FROM questions {where_clause} GROUP BY QuestionType", params).fetchall()
            diffs = conn.execute(f"SELECT Complexity, COUNT(*) FROM questions {where_clause} GROUP BY Complexity", params).fetchall()

            return {
                'total': total, 'courses': dict(courses), 'topics': dict(topics), 'avg_diff': avg_diff, 
                'exams': exams, 'types': dict(types), 'diffs': dict(diffs)
            }

    def save_exam(self, meta, questions, status='Final'):
        exam_json = json.dumps(questions, ensure_ascii=False)
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO created_exams (Title, CourseCode, TotalScore, ExamData, CreatedBy, Status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (meta['title'], meta['course'], meta['score'], exam_json, meta['creator'], status))

    def archive_exam(self, exam_id):
        """Sınavı veritabanında silmeden IsArchived=1 olarak işaretler."""
        with get_db_connection() as conn:
            conn.execute("UPDATE created_exams SET IsArchived = 1 WHERE ExamID = ?", (exam_id,))

    def get_exams(self, user_context, status=None):
        """Sadece IsArchived = 0 olan (aktif) sınavları çeker."""
        query = "SELECT * FROM created_exams WHERE IsArchived = 0"
        params = []
        
        if user_context['Role'] != 'Admin':
            query += " AND CreatedBy = ?"
            params.append(user_context['Username'])
            
        if status:
            query += " AND Status = ?"
            params.append(status)
            
        query += " ORDER BY CreatedAt DESC"
        with get_db_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_all_users(self):
        with get_db_connection() as conn:
            return [dict(row) for row in conn.execute("SELECT Username, Role, FullName FROM users").fetchall()]

db = DatabaseManager()

# ==============================================================================
# 3. YARDIMCI SINIFLAR (AI / PDF / WORD)
# ==============================================================================
# ==============================================================================
# AI CLASS (Geliştirildi)
# ==============================================================================
class AIGenerator:
    @staticmethod
    def get_api_key(provider):
        try:
            if provider == "google": 
                # Session state'i öncelikli kontrol et (Kullanıcı girişi)
                if f"user_provided_{provider}_key" in st.session_state and st.session_state[f"user_provided_{provider}_key"]:
                    return st.session_state[f"user_provided_{provider}_key"]
                # Sonra secrets.toml kontrol et
                return st.secrets["GOOGLE_API_KEY"]
        except: 
            return None
    
    @staticmethod
    def extract_text_from_file(uploaded_file):
        text = ""
        try:
            if uploaded_file.name.endswith('.pdf'):
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                for page in pdf_reader.pages: 
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
            elif uploaded_file.name.endswith('.docx'):
                doc = Document(uploaded_file)
                for para in doc.paragraphs: text += para.text + "\n"
            else:
                text = uploaded_file.read().decode("utf-8")
        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")
        return text

    @staticmethod
    def generate_from_text(text, num_questions=3, provider="google"):
        api_key = AIGenerator.get_api_key(provider)
        
        if not api_key:
            st.warning(f"⚠️ {provider.title()} servisi için API anahtarı tanımlanmamış. Lütfen alanı kontrol edin.", icon="🤖")
            return [] 

        prompt = f"""
        Aşağıdaki metni analiz et ve {num_questions} adet akademik sınav sorusu oluştur.
        
        Metin: "{text[:8000]}"
        
        Kurallar:
        1. Çıktı SADECE geçerli bir JSON formatında olsun. Markdown (```json) kullanma.
        2. Her sorunun tipi Çoktan Seçmeli (MC) olsun.
        3. JSON Şeması:
        [
            {{
                "QuestionText": "Soru metni buraya",
                "Options": {{"A": "Şık1", "B": "Şık2", "C": "Şık3", "D": "Şık4"}},
                "CorrectAnswer": "A",
                "Complexity": 2, 
                "Score": 10
            }}
        ]
        """
        response_text = ""
        try:
            if provider == "google":
                genai.configure(api_key=api_key)
                
                try:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(prompt)
                except Exception:
                    # Fallback
                    model = genai.GenerativeModel('gemini-pro')
                    response = model.generate_content(prompt)
                
                response_text = response.text

            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            
            if json_match:
                cleaned_json = json_match.group(0)
            else:
                cleaned_json = response_text.replace("```json", "").replace("```", "").strip()
                if cleaned_json.startswith("{") and cleaned_json.endswith("}"):
                    cleaned_json = f"[{cleaned_json}]"
            
            # JSON'ı Yüklemeyi Dene
            questions_data = json.loads(cleaned_json)
            
            final_questions = []
            for q in questions_data:
                final_questions.append({
                    'CourseCode': 'AI-GEN', 
                    'TopicArea': 'AI Üretimi',
                    'Complexity': q.get('Complexity', 2), 
                    'QuestionType': 'MC',
                    'Score': q.get('Score', 10), 
                    'QuestionText': q.get('QuestionText', 'Soru metni alınamadı'),
                    'Options': q.get('Options', {}), 
                    'CorrectAnswer': q.get('CorrectAnswer', 'A'),
                    'CreatedBy': st.session_state['user']['Username']
                })
            return final_questions

        except json.JSONDecodeError as e:
            # Geliştirilmiş JSON hata bildirimi
            error_details = f"JSON format hatası. Model düzgün JSON döndüremedi. Hata: {str(e)}"
            if response_text:
                 error_details += f"\n\nModelin Ham Çıktısı (ilk 500 karakter): {response_text[:500]}..."
            st.error(f"AI İşlem Hatası: {error_details}")
            return []
        except Exception as e:
            st.error(f"AI Genel Hata: {str(e)}")
            return []

class ExamPDFEngine(FPDF):
    def __init__(self, meta, is_answer_key=False, group_name="A", classical_lines=5):
        super().__init__()
        self.meta = meta
        self.is_answer_key = is_answer_key
        self.group_name = group_name
        self.classical_lines = classical_lines # Yeni parametre
        check_and_download_font()
        self.set_auto_page_break(auto=True, margin=20)
        if os.path.exists(FONT_FILENAME):
            self.add_font('DejaVu', '', FONT_FILENAME, uni=True)
            self.add_font('DejaVu', 'B', FONT_FILENAME, uni=True)
            self.font_family = 'DejaVu'
        else:
            self.font_family = 'Arial' 

    # (Header ve Footer metotları aynı kaldı, kod tekrarından kaçınıldı)
    def header(self):
        self.set_font(self.font_family, 'B', 14)
        title_suffix = " - CEVAP ANAHTARI" if self.is_answer_key else ""
        self.cell(0, 10, f"{self.meta['title']}{title_suffix}", 0, 1, 'C')
        self.set_font(self.font_family, '', 10)
        self.cell(0, 5, f"Ders: {self.meta['course']} | Grup: {self.group_name} | Tarih: {datetime.now().strftime('%d.%m.%Y')}", 0, 1, 'C')
        self.ln(5)
        
        if not self.is_answer_key:
            self.set_line_width(0.3)
            start_y = self.get_y()
            self.rect(10, start_y, 190, 25)
            self.set_font(self.font_family, '', 9)
            
            self.set_xy(12, start_y + 3)
            self.cell(20, 5, "Adı Soyadı:", 0, 0)
            self.cell(70, 5, "."*40, 0, 1)
            
            self.set_xy(12, start_y + 11)
            self.cell(20, 5, "Numarası:", 0, 0)
            self.cell(70, 5, "."*40, 0, 1)

            self.set_xy(110, start_y + 3)
            self.cell(15, 5, "Bölümü:", 0, 0)
            self.cell(70, 5, "."*40, 0, 1)
            
            self.set_xy(110, start_y + 11)
            self.cell(15, 5, "İmza:", 0, 0)
            self.cell(70, 5, "."*40, 0, 1)
            
            self.set_xy(12, start_y + 19)
            self.set_font(self.font_family, 'B', 12)
            self.cell(190, 5, f"KİTAPÇIK TÜRÜ: {self.group_name}", 0, 1, 'C')
            self.ln(5) 
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_family, '', 8)
        self.cell(0, 10, f'SSOP Pro - Grup {self.group_name} - Sayfa {self.page_no()}', 0, 0, 'C')

    def generate_content(self, questions):
        self.add_page()
        self.set_font(self.font_family, '', 11)
        
        for idx, q in enumerate(questions, 1):
            q_text = q['QuestionText']
            score_txt = f"({q['Score']} Puan)" if 'Score' in q else ""
            
            if self.is_answer_key:
                 header = f"{idx}. {q_text}\n   >>> DOĞRU CEVAP: {q.get('CorrectAnswer', '-')}"
                 self.set_text_color(200, 0, 0) 
            else:
                 header = f"{idx}. {q_text} {score_txt}"
                 self.set_text_color(0, 0, 0)

            if self.get_y() > 250: self.add_page()
            
            self.set_font(self.font_family, 'B', 11)
            self.multi_cell(0, 6, header)
            self.set_font(self.font_family, '', 11)
            self.set_text_color(0, 0, 0)
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
                elif q['QuestionType'] == 'CL': # Klasik soru boşluğu dinamikleştirildi
                    self.ln(2)
                    for _ in range(self.classical_lines):
                        self.cell(0, 5, "_"*80, 0, 1) # Yatay çizgi ekle
                    self.ln(3)

            self.ln(3)
            if not self.is_answer_key:
                self.set_draw_color(200,200,200)
                self.line(10, self.get_y(), 200, self.get_y())
                self.set_draw_color(0,0,0)
                self.ln(4)
            
    def get_pdf_bytes(self):
        return self.output(dest='S').encode('latin-1')

class ExamDocxEngine:
    """Word formatında sınav çıktısı üretir (Geliştirildi)"""
    def __init__(self, meta, is_answer_key=False, group_name="A", classical_lines=5):
        self.meta = meta
        self.is_answer_key = is_answer_key
        self.group_name = group_name
        self.classical_lines = classical_lines
        self.doc = Document()
        
    def generate(self, questions):
        # Header
        h1 = self.doc.add_heading(self.meta['title'], 0)
        h1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        info = f"Ders: {self.meta['course']} | Grup: {self.group_name} | Tarih: {datetime.now().strftime('%d.%m.%Y')}"
        p = self.doc.add_paragraph(info)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        if not self.is_answer_key:
            self.doc.add_paragraph("_"*80)
            self.doc.add_paragraph("Adı Soyadı: ....................................................   Numarası: ............................")
            self.doc.add_paragraph(f"KİTAPÇIK TÜRÜ: {self.group_name}")
            self.doc.add_paragraph("_"*80)
        
        self.doc.add_paragraph("")
        
        for idx, q in enumerate(questions, 1):
            q_text = q['QuestionText']
            score_txt = f"({q['Score']} Puan)"
            
            p = self.doc.add_paragraph()
            runner = p.add_run(f"{idx}. {q_text} {score_txt}")
            runner.bold = True
            
            if self.is_answer_key:
                ans_p = self.doc.add_paragraph()
                ans_runner = ans_p.add_run(f"   >>> DOĞRU CEVAP: {q.get('CorrectAnswer', '-')}")
                ans_runner.font.color.rgb = RGBColor(255, 0, 0)
                ans_runner.bold = True
            else:
                if q['QuestionType'] == 'MC':
                    opts = json.loads(q['Options']) if isinstance(q['Options'], str) else q['Options']
                    if opts:
                        for k, v in sorted(opts.items()):
                            self.doc.add_paragraph(f"   {k}) {v}")
                elif q['QuestionType'] == 'TF':
                    self.doc.add_paragraph("   ( ) Doğru    ( ) Yanlış")
                elif q['QuestionType'] == 'CL': # Klasik soru boşluğu dinamikleştirildi
                    for _ in range(self.classical_lines):
                        self.doc.add_paragraph("   " + "_"*90) 
            
            self.doc.add_paragraph("-" * 20) 

    def get_docx_bytes(self):
        buffer = BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()

# ==============================================================================
# 5. SAYFALAR
# ==============================================================================
def login_page():
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style='text-align: center; background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);'>
            <h1 style='color: #2c3e50; margin-bottom:0;'>🎓 SSOP Pro</h1>
            <p style='color: #3498db; font-size: 1.1em; font-weight:bold;'>Enterprise Edition v5.0</p>
            <p style='color: #7f8c8d; font-size: 0.9em;'>Akademik Sınav Sistemi</p>
            <hr style='margin: 20px 0;'>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            user = st.text_input("Kullanıcı Adı")
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", type="primary", use_container_width=True):
                account = db.login(user, pwd)
                if account:
                    st.session_state['user'] = account
                    st.rerun()
                else:
                    st.error("Hatalı kullanıcı adı veya şifre!")
        st.info("Demo: admin / admin")

def dashboard_page():
    user = st.session_state['user']
    st.markdown(f"## 👋 Hoşgeldin, {user['FullName']}")
    
    stats = db.get_stats(user)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Soru", stats['total'], "Adet")
    c2.metric("Aktif Ders", len(stats['courses']), "Ders")
    c3.metric("Ort. Zorluk", f"{stats['avg_diff']:.1f}", "/ 3.0")
    c4.metric("Üretilen Sınav", stats['exams'], "Adet")
    
    st.divider()
    
    col_g1, col_g2 = st.columns([2, 1])
    with col_g1:
        st.subheader("📊 Ders & Konu Dağılımı")
        if stats['courses']:
            treemap_data = []
            for course, count in stats['courses'].items():
                treemap_data.append(dict(Ders=course, Parent="Tüm Dersler", Soru=count))
            
            fig = px.treemap(
                treemap_data,
                path=['Parent', 'Ders'],
                values='Soru',
                color='Soru',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("Görüntülenecek veri yok.")
            
    with col_g2:
        st.subheader("🧩 Soru Analizi")
        if stats.get('types'):
            df_t = pd.DataFrame(list(stats['types'].items()), columns=['Tip', 'Adet'])
            fig3 = px.pie(df_t, values='Adet', names='Tip', hole=0.6)
            st.plotly_chart(fig3, use_container_width=True)
        else: st.info("Veri yok.")

def question_bank_page():
    user = st.session_state['user']
    st.title("🗃️ Soru Bankası Yönetimi")
    
    # 1. Verileri Çek
    all_q = db.get_questions(user)
    if not all_q:
        st.warning("📭 Soru bankası boş. 'Soru Ekle' menüsünden içerik ekleyin.")
        return

    # 2. Filtreleme Alanı
    with st.expander("🔎 Filtreleme ve Arama", expanded=True):
        c1, c2, c3, c4 = st.columns([1.5, 1, 1, 2])
        courses = sorted(list(set(q['CourseCode'] for q in all_q)))
        
        sel_course = c1.multiselect("Ders", courses)
        # Ders Tipi haritası
        type_map = {"MC": "Çoktan Seçmeli", "TF": "Doğru/Yanlış", "CL": "Klasik"}
        sel_type = c3.multiselect("Tip", ["MC", "TF", "CL"], format_func=lambda x: type_map.get(x, x))
        search_txt = c4.text_input("Metin Ara", placeholder="Soru içinde ara...")
    
    # 3. DataFrame Oluştur ve Filtrele
    df = pd.DataFrame(all_q)
    if sel_course: df = df[df['CourseCode'].isin(sel_course)]
    if sel_type: df = df[df['QuestionType'].isin(sel_type)]
    if search_txt: df = df[df['QuestionText'].str.contains(search_txt, case=False)]
    
    # --- EXCEL DIŞA AKTARMA (EXPORT) ---
    col_res, col_btn = st.columns([3, 1])
    col_res.markdown(f"**Sonuç:** {len(df)} kayıt bulundu.")
    
    excel_data = BytesIO()
    with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sorular')
    
    col_btn.download_button(
        label="📥 Excel Olarak İndir",
        data=excel_data.getvalue(),
        file_name=f"sorular_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    # -----------------------------------

    # 4. Data Editor
    # Seçim kutusu için sütun ekle
    df_editor = df.copy()
    df_editor.insert(0, "Seç", False)
    
    edited_df = st.data_editor(
        df_editor[['Seç', 'QuestionID', 'CourseCode', 'QuestionType', 'Score', 'QuestionText', 'LastEditedBy', 'LastEditedAt']],
        column_config={
            "Seç": st.column_config.CheckboxColumn(required=True),
            "QuestionID": st.column_config.NumberColumn("ID", width="small"),
            "QuestionText": st.column_config.TextColumn("Soru Metni", width="large"),
            "QuestionType": st.column_config.TextColumn("Tip"),
            "LastEditedBy": st.column_config.TextColumn("Son Düzenleyen"),
            "LastEditedAt": st.column_config.DatetimeColumn("Düzenleme Tarihi"),
        },
        use_container_width=True,
        hide_index=True,
        height=400,
        disabled=['QuestionID', 'CourseCode', 'QuestionType', 'Score', 'QuestionText', 'LastEditedBy', 'LastEditedAt'] # Tablo üzerinde direkt değişimi kapattık, aşağıda form ile yapacağız
    )
    
    # 5. Aksiyonlar (Silme ve Düzenleme)
    selected_rows = edited_df[edited_df['Seç']]
    
    if not selected_rows.empty:
        st.divider()
        st.subheader("🛠️ İşlemler")
        col_act1, col_act2 = st.columns([1, 3])
        
        # A) TOPLU SİLME
        with col_act1:
            if st.button(f"🗑️ Seçili {len(selected_rows)} Soruyu Sil", type="primary", use_container_width=True):
                ids_to_del = selected_rows['QuestionID'].tolist()
                db.bulk_delete_questions(ids_to_del)
                st.toast(f"{len(ids_to_del)} soru silindi!", icon="✅")
                time.sleep(1)
                st.rerun()
        
        # B) TEKLİ DÜZENLEME (Sadece 1 satır seçiliyse açılır)
        if len(selected_rows) == 1:
            q_row = selected_rows.iloc[0]
            q_id = int(q_row['QuestionID'])
            full_data = next((q for q in all_q if q['QuestionID'] == q_id), None)
            
            with col_act2:
                with st.container(border=True):
                    st.markdown(f"**Soru Düzenle (ID: {q_id})**")
                    with st.form("quick_edit_form"):
                        ne_text = st.text_area("Soru Metni", value=full_data['QuestionText'], height=100)
                        
                        c_ne1, c_ne2, c_ne3 = st.columns(3)
                        ne_course = c_ne1.text_input("Ders Kodu", value=full_data['CourseCode'])
                        ne_score = c_ne2.number_input("Puan", value=float(full_data['Score']))
                        ne_ans = c_ne3.text_input("Doğru Cevap", value=full_data['CorrectAnswer'])
                        
                        if full_data['QuestionType'] == 'MC':
                            current_opts = full_data.get('Options', '{}')
                            if isinstance(current_opts, str):
                                try: current_opts_dict = json.loads(current_opts)
                                except: current_opts_dict = {}
                            else:
                                current_opts_dict = current_opts
                                
                            st.caption("Seçenekler (JSON formatında düzenleyin veya olduğu gibi bırakın)")
                            ne_opts_str = st.text_area("Seçenekler JSON", value=json.dumps(current_opts_dict, ensure_ascii=False))
                        else:
                            ne_opts_str = None

                        if st.form_submit_button("💾 Değişiklikleri Kaydet"):
                            update_payload = full_data.copy()
                            update_payload['QuestionText'] = ne_text
                            update_payload['CourseCode'] = ne_course
                            update_payload['Score'] = ne_score
                            update_payload['CorrectAnswer'] = ne_ans
                            
                            if ne_opts_str:
                                try:
                                    update_payload['Options'] = json.loads(ne_opts_str)
                                except:
                                    st.error("JSON format hatası!")
                                    return

                            db.update_question(q_id, update_payload, user['Username']) # Düzenleyen bilgisi eklendi
                            st.success("Soru başarıyla güncellendi!")
                            time.sleep(1)
                            st.rerun()

def add_question_page():
    st.title("➕ Soru Ekleme Merkezi")
    t1, t2, t3 = st.tabs(["✍️ Manuel Ekleme", "📂 Excel Yükleme", "🤖 AI Soru Asistanı"])
    
    # --- TAB 1: MANUEL EKLEME ---
    with t1:
        c1, c2, c3, c4 = st.columns(4)
        qc = c1.text_input("Ders Kodu", "MAT101").upper()
        qt = c2.text_input("Konu", "Genel")
        qdiff = c3.slider("Zorluk Seviyesi", 1, 3, 2)
        qtype = c4.selectbox("Soru Tipi", ["MC", "TF", "CL"], format_func=lambda x: {"MC": "Çoktan Seçmeli", "TF": "Doğru/Yanlış", "CL": "Klasik"}.get(x))
        
        with st.form("add_manual_form", clear_on_submit=True):
            qtext = st.text_area("Soru Metni", height=100, placeholder="Soru metnini buraya giriniz...")
            
            opts = {}
            if qtype == "MC":
                st.write("Seçenekler:")
                oc1, oc2 = st.columns(2)
                opts['A'] = oc1.text_input("A)", placeholder="Seçenek A")
                opts['B'] = oc2.text_input("B)", placeholder="Seçenek B")
                opts['C'] = oc1.text_input("C)", placeholder="Seçenek C")
                opts['D'] = oc2.text_input("D)", placeholder="Seçenek D")
                opts['E'] = oc1.text_input("E)", placeholder="Seçenek E (Opsiyonel)")
                opts = {k:v for k,v in opts.items() if v.strip()}
            
            fc1, fc2 = st.columns(2)
            qans = fc1.text_input("Doğru Cevap (Örn: A veya Doğru)")
            qscore = fc2.number_input("Varsayılan Puan", 1, 100, 10)
            
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

    # --- TAB 2: EXCEL YÜKLEME ---
    with t2:
        st.info("Toplu soru yüklemek için aşağıdaki şablonu kullanın.")
        
        # 1. Şablon İndirme Butonu
        demo_data = pd.DataFrame([
            {
                "CourseCode": "MAT101", "TopicArea": "Türev", "Complexity": 2, 
                "QuestionType": "MC", "Score": 10, "QuestionText": "f(x)=x^2 ise f'(x) nedir?", 
                "OptionA": "2x", "OptionB": "x", "OptionC": "2", "OptionD": "0", "OptionE": "", 
                "CorrectAnswer": "A"
            },
            {
                "CourseCode": "TAR101", "TopicArea": "Tarih", "Complexity": 1, 
                "QuestionType": "TF", "Score": 5, "QuestionText": "İstanbul 1453'te fethedildi.", 
                "OptionA": "", "OptionB": "", "OptionC": "", "OptionD": "", "OptionE": "", 
                "CorrectAnswer": "Doğru"
            }
        ])
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            demo_data.to_excel(writer, index=False)
        
        st.download_button("📥 Örnek Excel Şablonunu İndir", data=buffer.getvalue(), file_name="soru_yukleme_sablonu.xlsx")
        st.markdown("---")

        # 2. Dosya Yükleme ve İşleme (Hata raporlama iyileştirildi)
        up_file = st.file_uploader("Excel Dosyası Yükle (.xlsx)", type=['xlsx'])
        if up_file and st.button("Soruları İçeri Aktar", type="primary"):
            try:
                df_up = pd.read_excel(up_file)
                df_up = df_up.fillna('') # NaN hatalarını önle
                success_count = 0
                error_rows = []
                
                with st.spinner('Sorular işleniyor...'):
                    for index, row in df_up.iterrows():
                        try:
                            # Seçenekleri topla (Sütun yapısından Dict yapısına)
                            opts = {}
                            if str(row.get('QuestionType')) == 'MC':
                                for letter in ['A','B','C','D','E']:
                                    key_name = f'Option{letter}'
                                    if key_name in row and str(row[key_name]).strip():
                                        opts[letter] = str(row[key_name]).strip()
                            
                            db.add_question({
                                'CourseCode': str(row.get('CourseCode', 'GENEL')),
                                'TopicArea': str(row.get('TopicArea', 'Genel')),
                                'Complexity': int(row.get('Complexity', 2)),
                                'QuestionType': str(row.get('QuestionType', 'CL')),
                                'Score': float(row.get('Score', 10)),
                                'QuestionText': str(row.get('QuestionText', '')),
                                'Options': opts,
                                'CorrectAnswer': str(row.get('CorrectAnswer', '')),
                                'CreatedBy': st.session_state['user']['Username']
                            })
                            success_count += 1
                        except Exception as inner_e:
                            error_rows.append((index + 2, str(inner_e))) # Excel satır numarası + 2 (Header ve 0'dan başlama)

                if error_rows:
                    st.warning(f"⚠️ {len(error_rows)} satır hata nedeniyle atlandı. Başarılı eklenen: {success_count} soru.")
                    error_details = "\n".join([f"Satır {num}: {err}" for num, err in error_rows])
                    st.expander("Hata Detayları").code(error_details)
                
                if success_count > 0:
                    st.success(f"✅ {success_count} soru başarıyla veritabanına eklendi!")
                    time.sleep(1) 
            except Exception as e:
                st.error(f"Excel okuma hatası: {e}")

    # --- TAB 3: AI SORU ASİSTANI (Geliştirildi) ---
    with t3:
        st.markdown("### 🤖 Yapay Zeka ile Soru Üret")
        st.info("Not: AI bazen formatı bozabilir. Sistem otomatik düzeltmeye çalışır.")
        
        c_ai1, c_ai2 = st.columns([1, 1])
        ai_provider = c_ai1.radio("AI Modeli Seçin", ["Google Gemini"], horizontal=True) # Şimdilik sadece Gemini destekleniyor
        provider_code = "google"
        num_q = c_ai2.slider("Üretilecek Soru Sayısı", 1, 10, 3)

        # Kullanıcıdan API anahtarı alma alanı eklendi
        if not AIGenerator.get_api_key(provider_code):
            user_key = st.text_input(f"⚠️ {ai_provider} API Anahtarınızı Buraya Girin", type="password")
            if user_key:
                st.session_state[f"user_provided_{provider_code}_key"] = user_key
            else:
                 st.warning("Lütfen API anahtarınızı girin veya `st.secrets` dosyasına ekleyin.")

        # Girdi Yöntemleri
        tab_ai_file, tab_ai_text = st.tabs(["📄 Dosyadan (PDF/Docx)", "📝 Metinden"])
        
        final_text = ""
        with tab_ai_file:
            uploaded_doc = st.file_uploader("Ders Notu Yükle", type=['pdf', 'docx', 'txt'])
            if uploaded_doc:
                final_text = AIGenerator.extract_text_from_file(uploaded_doc)
        
        with tab_ai_text:
            pasted_text = st.text_area("Metni Buraya Yapıştır", height=150)
            if not final_text and pasted_text:
                final_text = pasted_text
        
        # Üret Butonu
        if st.button("🚀 Soruları Oluştur", type="primary"):
            if not AIGenerator.get_api_key(provider_code):
                st.error("Lütfen bir API Anahtarı girin.")
            elif len(final_text) < 50:
                st.warning("⚠️ Lütfen analiz için yeterli uzunlukta bir metin veya dosya sağlayın.")
            else:
                with st.spinner(f"{ai_provider} içeriği analiz ediyor ve soruları hazırlıyor..."):
                    qs = AIGenerator.generate_from_text(final_text, num_q, provider_code)
                    if qs:
                        st.session_state['ai_questions'] = qs
                        st.success(f"✅ {len(qs)} adet soru taslağı oluşturuldu. Aşağıdan inceleyip ekleyebilirsiniz.")
                    # Hata AIGenerator içinde raporlanmıştır

        # Üretilenleri Listeleme ve Ekleme
        if 'ai_questions' in st.session_state and st.session_state['ai_questions']:
            st.divider()
            st.markdown("#### 📝 Üretilen Soru Taslakları")
            
            for idx, q in enumerate(st.session_state['ai_questions']):
                with st.expander(f"Soru {idx+1}: {q.get('QuestionText', '')[:60]}...", expanded=True):
                    col_q1, col_q2 = st.columns([3, 1])
                    with col_q1:
                        st.markdown(f"**Soru:** {q.get('QuestionText')}")
                        if q.get('Options'):
                            st.json(q.get('Options'))
                    with col_q2:
                        st.info(f"Cevap: {q.get('CorrectAnswer')}")
                        st.caption(f"Zorluk: {q.get('Complexity')}")
                    
                    if st.button(f"💾 Veritabanına Ekle (Soru {idx+1})", key=f"btn_ai_save_{idx}"):
                        db.add_question(q)
                        st.toast(f"Soru {idx+1} eklendi!", icon="✅")

def shuffle_question_options(questions_list):
    """
    Çoktan Seçmeli soruların şıklarını ve doğru cevap anahtarını karıştırır.
    """
    shuffled_questions = []
    
    for q_orig in questions_list:
        q = q_orig.copy() 
        
        if q['QuestionType'] == 'MC':
            raw_opts = q.get('Options')
            opts = json.loads(raw_opts) if isinstance(raw_opts, str) else raw_opts
            
            if opts and len(opts) > 1:
                old_correct_key = q.get('CorrectAnswer', '').strip()
                correct_text = opts.get(old_correct_key)
                
                if correct_text:
                    keys = list(opts.keys())
                    values = list(opts.values())
                    
                    random.shuffle(values)
                    
                    new_opts = dict(zip(keys, values))
                    
                    # 2. Doğru cevabın YENİ KEY'ini bul
                    new_correct_key = None
                    for k, v in new_opts.items():
                        if v == correct_text:
                            new_correct_key = k
                            break
                    
                    # 3. Soruyu güncelle
                    q['Options'] = new_opts
                    q['CorrectAnswer'] = new_correct_key
                    
        shuffled_questions.append(q)
    
    return shuffled_questions

def exam_create_page():
    st.title("⚙️ Sınav Sihirbazı v2.0")
    user = st.session_state['user']
    
    if 'exam_stage' not in st.session_state:
        st.session_state['exam_stage'] = 'setup'
        st.session_state['selected_questions'] = []

    # ADIM 1: AYARLAR (Klasik soru satır sayısı eklendi)
    if st.session_state['exam_stage'] == 'setup':
        st.info("Adım 1/3: Sınav Ayarları")
        pool = db.get_questions(user) 
        courses = sorted(list(set(q['CourseCode'] for q in pool)))
        
        c1, c2 = st.columns(2)
        sel_course = c1.selectbox("Ders", courses) if courses else st.selectbox("Ders", ["Veri Yok"])
        sel_title = c2.text_input("Başlık", f"{sel_course} Final")
        
        c3, c4, c5, c6 = st.columns(4)
        sel_score = c3.number_input("Toplam Puan", value=100)
        method = c4.radio("Yöntem", ["🎲 Rastgele", "✅ Manuel"], horizontal=True)
        groups = c5.selectbox("Kitapçıklar", ["Sadece A", "A ve B", "A, B, C, D"])
        classical_lines = c6.slider("Klasik Soru Cevap Satırı", 1, 15, 5) # Yeni parametre
        
        if st.button("İleri ➡️", type="primary") and courses:
            st.session_state['exam_meta'] = {
                'course': sel_course, 'title': sel_title, 'score': sel_score, 
                'method': method, 'creator': user['Username'], 'groups': groups,
                'classical_lines': classical_lines # Meta'ya eklendi
            }
            st.session_state['exam_stage'] = 'selection'
            st.rerun()

    # ADIM 2: SEÇİM 
    elif st.session_state['exam_stage'] == 'selection':
        meta = st.session_state['exam_meta']
        pool = db.get_questions(user, meta['course'])
        
        tab_random, tab_manual = st.tabs(["🎲 Zorluk Bazlı (Rastgele)", "✍️ Listeden Seç (Manuel)"])
        
        # --- SEKME 1: RASTGELE / ZORLUK BAZLI ---
        with tab_random:
            st.info("Sistemin belirlediğiniz sayılarda rastgele soru seçmesi için adetleri girin.")
            
            pool_easy = [q for q in pool if int(q.get('Complexity', 1)) == 1]
            pool_med  = [q for q in pool if int(q.get('Complexity', 2)) == 2]
            pool_hard = [q for q in pool if int(q.get('Complexity', 3)) == 3]
            
            c_r1, c_r2, c_r3 = st.columns(3)
            with c_r1:
                st.markdown(f"**🟢 Kolay** (Mevcut: {len(pool_easy)})")
                req_easy = st.number_input("Adet", 0, len(pool_easy), 0, key="rnd_easy")
            with c_r2:
                st.markdown(f"**🟡 Orta** (Mevcut: {len(pool_med)})")
                req_med = st.number_input("Adet", 0, len(pool_med), 0, key="rnd_med")
            with c_r3:
                st.markdown(f"**🔴 Zor** (Mevcut: {len(pool_hard)})")
                req_hard = st.number_input("Adet", 0, len(pool_hard), 0, key="rnd_hard")
                
            total_req = req_easy + req_med + req_hard
            
            # Dinamik puan gösterimi eklendi
            score_per_q_rand = meta['score'] / total_req if total_req > 0 else 0
            st.caption(f"Toplam Seçilen: {total_req} Soru (Soru Başı ≈ {score_per_q_rand:.2f} Puan)")
            
            if st.button("🎲 Rastgele Oluştur", type="primary", use_container_width=True):
                if total_req == 0:
                    st.warning("En az 1 soru seçmelisiniz.")
                else:
                    selected_qs = []
                    if req_easy > 0: selected_qs.extend(random.sample(pool_easy, req_easy))
                    if req_med > 0:  selected_qs.extend(random.sample(pool_med, req_med))
                    if req_hard > 0: selected_qs.extend(random.sample(pool_hard, req_hard))
                    
                    random.shuffle(selected_qs) # Karıştır
                    st.session_state['selected_questions'] = selected_qs
                    st.session_state['exam_stage'] = 'preview'
                    st.rerun()

        # --- SEKME 2: MANUEL SEÇİM ---
        with tab_manual:
            st.info("Aşağıdaki listeden sınavda sormak istediğiniz soruları işaretleyin.")
            
            if not pool:
                st.warning("Bu ders için soru havuzu boş.")
            else:
                df = pd.DataFrame(pool)
                df.insert(0, "Seç", False)
                
                edited_df = st.data_editor(
                    df,
                    column_config={
                        "Seç": st.column_config.CheckboxColumn(required=True),
                        "QuestionText": st.column_config.TextColumn("Soru", width="large"),
                        "Complexity": st.column_config.NumberColumn("Zorluk", help="1:Kolay, 2:Orta, 3:Zor"),
                        "Score": st.column_config.NumberColumn("Puan"),
                    },
                    disabled=["QuestionID", "CourseCode", "QuestionText", "Complexity", "Score", "QuestionType"], # Sadece checkbox aktif
                    hide_index=True,
                    use_container_width=True,
                    height=500
                )
                
                manual_selections = edited_df[edited_df["Seç"]]
                count_sel = len(manual_selections)
                
                # Dinamik puan gösterimi eklendi
                score_per_q_man = meta['score'] / count_sel if count_sel > 0 else 0
                st.write(f"**Seçilen Soru Sayısı:** {count_sel} (Soru Başı ≈ {score_per_q_man:.2f} Puan)")
                
                if st.button("✅ Seçilenlerle Oluştur", type="primary", use_container_width=True):
                    if count_sel == 0:
                        st.warning("Lütfen listeden en az bir soru işaretleyin.")
                    else:
                        selected_ids = manual_selections['QuestionID'].tolist()
                        final_selection = [q for q in pool if q['QuestionID'] in selected_ids]
                        
                        st.session_state['selected_questions'] = final_selection
                        st.session_state['exam_stage'] = 'preview'
                        st.rerun()

    # ADIM 3: ÖNİZLEME
    elif st.session_state['exam_stage'] == 'preview':
        qs = st.session_state['selected_questions']
        meta = st.session_state['exam_meta']
        
        st.write(f"Seçilen Soru: {len(qs)} | Soru Başı Puan: {meta['score']/len(qs):.2f}")
        
        score_per_q = meta['score'] / len(qs)
        for q in qs: q['Score'] = round(score_per_q, 2)

        c_save1, c_save2 = st.columns([1, 1])
        if c_save1.button("💾 Sınavı Oluştur (PDF + Word)", type="primary", use_container_width=True):
            db.save_exam(meta, qs, status='Final')
            st.session_state['final_qs'] = qs
            st.session_state['exam_stage'] = 'finish'
            st.rerun()

    # BİTİŞ: DOSYA ÜRETİMİ
    elif st.session_state['exam_stage'] == 'finish':
        st.success("✅ Sınav Hazırlandı!")
        meta = st.session_state['exam_meta']
        base_questions = st.session_state['final_qs']
        
        group_list = ["A"]
        if meta['groups'] == "A ve B": group_list = ["A", "B"]
        elif "C" in meta['groups']: group_list = ["A", "B", "C", "D"]
        
        # Klasik soru satır sayısını al
        classical_lines = meta.get('classical_lines', 5)

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zf:
            for grp in group_list:
                current_qs = [q.copy() for q in base_questions]
                if grp != "A": 
                    random.shuffle(current_qs)
                    current_qs = shuffle_question_options(current_qs)

                # PDF - Sınav
                pdf = ExamPDFEngine(meta, group_name=grp, classical_lines=classical_lines)
                pdf.generate_content(current_qs)
                zf.writestr(f"SoruKitapcigi_{grp}.pdf", pdf.get_pdf_bytes())
                
                # PDF - Cevap Anahtarı
                pdfk = ExamPDFEngine(meta, is_answer_key=True, group_name=grp)
                pdfk.generate_content(current_qs)
                zf.writestr(f"CevapAnahtari_{grp}.pdf", pdfk.get_pdf_bytes())

                # DOCX - Sınav 
                docx = ExamDocxEngine(meta, group_name=grp, classical_lines=classical_lines)
                docx.generate(current_qs)
                zf.writestr(f"SoruKitapcigi_{grp}.docx", docx.get_docx_bytes())

        st.download_button(
            "📦 Tüm Seti İndir (PDF + Word)",
            data=zip_buffer.getvalue(),
            file_name="sinav_seti_v5.zip",
            mime="application/zip",
            type="primary"
        )
        if st.button("Yeni Sınav"):
            del st.session_state['exam_stage']
            st.rerun()

def admin_page():
    if st.session_state['user']['Role'] != 'Admin':
        st.error("Bu sayfaya erişim yetkiniz yok.")
        return
        
    st.title("🛡️ Yönetici Paneli")
    
    tab1, tab2, tab3 = st.tabs(["Kullanıcı Listesi", "Yeni Kullanıcı Ekle", "Veritabanı Yönetimi"])
    
    with tab1:
        users = db.get_all_users()
        df_users = pd.DataFrame(users)
        st.dataframe(df_users, use_container_width=True, hide_index=True)
        
        st.markdown("### Kullanıcı Silme")
        
        for u in users:
            col_u1, col_u2, col_u3 = st.columns([3, 1, 1])
            col_u1.write(f"**{u['Username']}** ({u['FullName']}) - {u['Role']}")
            
            if u['Username'] != 'admin':
                if col_u3.button("🗑️ Sil", key=f"del_{u['Username']}", type="secondary"):
                    if db.delete_user(u['Username']): # Tanımlanan fonksiyon çağrılıyor
                        st.toast("Kullanıcı silindi.", icon="✅")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Hata: Kullanıcı silinemedi.")
            else:
                 col_u3.info("Sistem Yöneticisi")
                  
    with tab2:
        with st.form("new_user"):
            new_u = st.text_input("Kullanıcı Adı")
            new_p = st.text_input("Şifre", type="password")
            new_n = st.text_input("Ad Soyad")
            new_r = st.selectbox("Rol", ["Teacher", "Admin"])
            if st.form_submit_button("Kullanıcı Oluştur", type="primary"):
                if db.create_user(new_u, new_p, new_n, new_r):
                    st.success("Kullanıcı oluşturuldu!")
                else:
                    st.error("Kullanıcı adı zaten var.")
                    
    with tab3:
        st.subheader("Veritabanı Yedekleme")
        db_path = DB_FILE
        if os.path.exists(db_path):
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="📥 SQLite Veritabanını İndir (.sqlite)",
                data=db_bytes,
                file_name=f"ssop_yedek_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite",
                mime="application/octet-stream"
            )
            st.caption("Bu, uygulamanın tüm verilerini (sorular, kullanıcılar, sınavlar) içeren yedek dosyadır.")
        else:
            st.error("Veritabanı dosyası bulunamadı.")


def history_page():
    user = st.session_state['user']
    st.title("🗂️ Sınav Arşivi")
    
    # Aktif ve Arşivlenmiş/Taslak ayrımı yapılabilir
    tab_active, tab_archived = st.tabs(["Aktif Sınavlar", "Arşivlenmiş/Gizli"])
    
    with tab_active:
        exams = db.get_exams(user)
        if not exams:
            st.info("Henüz oluşturulmuş aktif bir sınav yok.")
            return

        st.markdown("---")

        for ex in exams:
            col_main, col_action = st.columns([6, 1])
            
            with col_main:
                expander_title = f"📄 {ex['Title']} ({ex['CourseCode']}) | Tarih: {ex['CreatedAt']}"
                
                with st.expander(expander_title):
                    st.markdown(f"**Durum:** {ex['Status']}")
                    st.markdown(f"**Toplam Puan:** {ex['TotalScore']}")
                    st.markdown(f"**Oluşturan:** {ex['CreatedBy']}")
                    
                    try:
                        q_data = json.loads(ex['ExamData'])
                        st.info(f"Bu sınavda toplam **{len(q_data)}** soru bulunmaktadır.")
                        
                        if st.checkbox("Soruları Listele", key=f"view_q_{ex['ExamID']}"):
                            for i, q in enumerate(q_data, 1):
                                st.text(f"{i}. {q['QuestionText']} ({q['Score']} Puan)")
                    except Exception as e:
                        st.error(f"Veri hatası: {e}")

            with col_action:
                st.write("") 
                if st.button("🗑️ Arşivle", key=f"archive_exam_{ex['ExamID']}", type="secondary"):
                    db.archive_exam(ex['ExamID'])
                    st.toast(f"Sınav (ID: {ex['ExamID']}) arayüzden gizlendi!", icon="✅")
                    time.sleep(1)
                    st.rerun()
                    
    with tab_archived:
        # Arşivlenmiş sınavları çekmek için yeni bir get_exams çağrısı gerekir (şu anki fonksiyon sadece IsArchived=0 çeker)
        st.info("Bu alanda şu an için arşivlenmiş kayıtlar gösterilmiyor. Sadece aktif ve Final durumunda olanlar listelenir.")

# ==============================================================================
# 6. ANA AKIŞ
# ==============================================================================
def main():
    if 'user' not in st.session_state:
        login_page()
        return

    user = st.session_state['user']
    local_css()

    with st.sidebar:
        st.markdown(f"### 👤 {user['FullName']}")
        selected = option_menu(
            menu_title=None,
            options=["Gösterge Paneli", "Soru Bankası", "Soru Ekle", "Sınav Oluştur", "Arşiv"] + (["Yönetim"] if user['Role']=='Admin' else []),
            icons=["speedometer2", "collection", "plus-circle", "file-earmark-text", "archive", "gear"],
            default_index=0,
        )
        if st.button("Çıkış Yap"):
            del st.session_state['user']
            st.rerun()

    if selected == "Gösterge Paneli": dashboard_page()
    elif selected == "Soru Bankası": question_bank_page()
    elif selected == "Soru Ekle": add_question_page()
    elif selected == "Sınav Oluştur": exam_create_page()
    elif selected == "Arşiv": 
        history_page()
    elif selected == "Yönetim": admin_page()

if __name__ == "__main__":
    main()