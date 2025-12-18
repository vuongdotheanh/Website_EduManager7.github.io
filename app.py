import re
import uvicorn
from json import dumps as json_dumps
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random

# CẤU HÌNH EMAIL 
SENDER_EMAIL = "thengudot1233@gmail.com"
SENDER_PASSWORD = "qjxt jvxj ofjn horm" # Dán mật khẩu ứng dụng vào đây

def send_verification_email(receiver_email):
    # 1. Tạo mã xác thực ngẫu nhiên 6 số
    verification_code = str(random.randint(100000, 999999))
    
    # 2. Nội dung email
    subject = "Mã xác thực đăng ký EduManager"
    body = f"""
    <html>
        <body>
            <h2>Xin chào,</h2>
            <p>Mã xác thực của bạn là: <strong style="color: #4361ee; font-size: 20px;">{verification_code}</strong></p>
            <p>Vui lòng không chia sẻ mã này cho ai.</p>
        </body>
    </html>
    """

    # 3. Thiết lập gửi
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    try:
        # Kết nối tới server Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        return verification_code # Trả về mã để lưu vào database kiểm tra
    except Exception as e:
        print(f"Lỗi gửi email: {e}")
        return None

# =========================
# 1. CẤU HÌNH DATABASE
# =========================
SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()



class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    email = Column(String, unique=True) 
    phone = Column(String) 
    role = Column(String, default="teacher")
    full_name = Column(String) # THÊM CỘT HỌ VÀ TÊN
    verification_code = Column(String, nullable=True) # MÃ XÁC THỰC EMAIL

class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(Integer, primary_key=True, index=True)
    room_name = Column(String, unique=True, index=True) 
    capacity = Column(Integer)                         
    equipment = Column(String)                        
    status = Column(String, default="Available")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer)
    user_id = Column(Integer)
    booker_name = Column(String) 
    start_time = Column(String) 
    duration_hours = Column(String)
    status = Column(String, default="Confirmed")

Base.metadata.create_all(bind=engine)

# =========================
# 2. KHỞI TẠO FASTAPI
# =========================
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def to_json(obj): return json_dumps(obj)
templates.env.filters['tojson'] = to_json

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        # Admin mặc định cũng có họ tên
        db.add(User(username="admin", password="123", role="admin", full_name="Quản Trị Viên"))
    if not db.query(Classroom).first():
        rooms = [
            Classroom(room_name="Phòng A101", capacity=40, equipment="Máy chiếu", status="Available"),
            Classroom(room_name="Phòng A102", capacity=40, equipment="Máy chiếu", status="Available"),
            Classroom(room_name="Phòng B201", capacity=50, equipment="Loa, Mic", status="Available"),
            Classroom(room_name="Phòng Lab 1", capacity=30, equipment="PC", status="Available"),
            Classroom(room_name="Hội trường", capacity=100, equipment="Full", status="Available"),
        ]
        db.add_all(rooms)
        db.commit()
    db.close()

# --- PHÂN QUYỀN ---
def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("current_user")
    if not username: return None
    user = db.query(User).filter(User.username == username).first()
    return user

def require_admin(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Chỉ Admin mới có quyền này.")
    return user

def require_staff(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Chỉ Giáo viên hoặc Admin mới có quyền này.")
    return user


# 3. ROUTE API

# --- API ĐĂNG KÝ MỚI (GỬI MAIL) ---
@app.post("/api/register")
async def register(data: dict, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data['username']).first():
        return {"status": "error", "message": "Tên đăng nhập đã tồn tại"}
    if db.query(User).filter(User.email == data['email']).first():
        return {"status": "error", "message": "Email này đã được sử dụng"}

    # Gửi mã xác thực
    otp_code = send_verification_email(data['email'])
    if not otp_code:
        return {"status": "error", "message": "Lỗi gửi email xác thực. Kiểm tra lại email!"}

    # Lưu user vào DB kèm mã OTP
    new_user = User(
        username=data['username'], 
        password=data['password'], 
        email=data['email'], 
        phone=data['phone'], 
        role=data['role'],
        full_name=data.get('full_name', data['username']),
        verification_code=otp_code # Lưu mã
    )
    db.add(new_user)
    db.commit()
    
    # Trả về username để chuyển sang trang nhập mã
    return {"status": "success", "username": data['username']}

# --- API XÁC THỰC OTP (MỚI) ---
@app.post("/api/verify-otp")
async def verify_otp(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data['username']).first()
    
    if not user:
        return {"status": "error", "message": "User không tồn tại"}
    
    if user.verification_code == data['otp']:
        # Đúng mã -> Xóa mã đi (coi như đã kích hoạt)
        user.verification_code = None 
        db.commit()
        return {"status": "success", "message": "Xác thực thành công!"}
    else:
        return {"status": "error", "message": "Mã xác thực không đúng!"}

# --- Route trang Xác thực ---
@app.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request): return templates.TemplateResponse("verify.html", {"request": request})

# --- API QUÊN MẬT KHẨU (BẢO MẬT HƠN) ---
@app.post("/api/forgotpw")
async def forgotpw(data: dict, db: Session = Depends(get_db)):
    # Tìm user khớp cả Tên đăng nhập VÀ Số điện thoại
    user = db.query(User).filter(
        User.username == data['username'], 
        User.phone == data['phone']
    ).first()
    
    if not user:
        # Nếu không khớp cả 2 thông tin thì báo lỗi chung để bảo mật
        return {"status": "error", "message": "Thông tin không chính xác (Sai tên đăng nhập hoặc số điện thoại)!"}
    
    # Nếu đúng thông tin -> Cập nhật mật khẩu mới
    user.password = data['new_password']
    db.commit()
    
    return {"status": "success", "message": "Đã đặt lại mật khẩu thành công! Hãy đăng nhập."}
@app.post("/api/login")
async def login(data: dict, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data['username'], User.password == data['password']).first()
    if user:
        response.set_cookie(key="current_user", value=user.username)
        return {"status": "success"}
    return {"status": "error", "message": "Sai tài khoản hoặc mật khẩu"}

# --- API QUẢN LÝ PHÒNG ---
@app.post("/api/rooms/create")
async def create_room(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    db.add(Classroom(room_name=data['room_name'], capacity=data['capacity'], equipment=data['equipment'], status=data.get('status', 'Available')))
    db.commit()
    return {"status": "success", "message": "Đã thêm phòng mới thành công!"}

@app.post("/api/rooms/update")
async def update_room(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    room = db.query(Classroom).filter(Classroom.id == data['room_id']).first()
    if room:
        room.room_name = data.get('room_name', room.room_name)
        room.capacity = data.get('capacity', room.capacity)
        room.equipment = data.get('equipment', room.equipment)
        room.status = data.get('status', room.status)
        db.commit()
        return {"status": "success", "message": "Cập nhật thành công!"}
    return {"status": "error", "message": "Không tìm thấy phòng!"}

@app.post("/api/rooms/delete")
async def delete_room(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    room = db.query(Classroom).filter(Classroom.id == data['room_id']).first()
    if room:
        db.delete(room)
        db.commit()
        return {"status": "success", "message": "Đã xóa phòng!"}
    return {"status": "error", "message": "Không tìm thấy phòng!"}

# --- API ĐẶT LỊCH ---
@app.post("/api/bookings/create")
async def create_booking(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    room = db.query(Classroom).filter(Classroom.id == data['room_id']).first()
    if not room: return {"status": "error", "message": "Không tìm thấy phòng học."}
    if room.status == 'Maintenance': return {"status": "error", "message": "Phòng đang bảo trì!"}
    
    # LƯU FULL_NAME VÀO BOOKER_NAME
    booker_display = current_user.full_name if current_user.full_name else current_user.username
    
    db.add(Booking(
        room_id=data['room_id'], 
        user_id=current_user.id, 
        booker_name=booker_display, # Dùng tên thật
        start_time=data['start_time'], 
        duration_hours=data['duration_display'], 
        status="Confirmed"
    ))
    db.commit()
    return {"status": "success", "message": "Đặt lịch thành công!"}

@app.post("/api/bookings/delete")
async def delete_booking(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    booking = db.query(Booking).filter(Booking.id == data['booking_id']).first()
    if not booking: return {"status": "error", "message": "Không tìm thấy lịch đặt."}
    
    # Cho phép Admin hoặc chính chủ xóa
    if current_user.role != 'admin' and booking.user_id != current_user.id:
        return {"status": "error", "message": "Không thể xóa lịch của người khác."}

    db.delete(booking)
    db.commit()
    return {"status": "success", "message": "Đã hủy lịch đặt thành công!"}

# --- API QUẢN LÝ USER ---
@app.post("/api/users/update")
async def update_user(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == data['user_id']).first()
    if not u: return {"status": "error", "message": "Không tìm thấy user!"}
    u.email = data.get('email', u.email)
    u.phone = data.get('phone', u.phone)
    u.role = data.get('role', u.role)
    if data.get('new_password'): u.password = data['new_password']
    db.commit()
    return {"status": "success", "message": "Cập nhật thành công!"}

@app.post("/api/users/delete")
async def delete_user(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == data['user_id']).first()
    if not u: return {"status": "error", "message": "User không tồn tại."}
    if u.id == current_user.id: return {"status": "error", "message": "Không thể xóa chính mình!"}
    db.delete(u)
    db.commit()
    return {"status": "success", "message": "Đã xóa user!"}

# --- API PROFILE CÁ NHÂN ---
# --- API PROFILE CÁ NHÂN (NÂNG CẤP BẢO MẬT) ---
@app.post("/api/profile/update")
async def update_profile(data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return {"status": "error", "message": "Chưa đăng nhập!"}
    
    # 1. Kiểm tra xem có thay đổi thông tin nhạy cảm không
    new_email = data.get('email')
    new_phone = data.get('phone')
    
    is_sensitive_change = False
    # Nếu gửi lên Email mới khác Email cũ -> Có thay đổi
    if new_email and new_email != current_user.email: 
        is_sensitive_change = True
    # Nếu gửi lên SĐT mới khác SĐT cũ -> Có thay đổi
    if new_phone and new_phone != current_user.phone: 
        is_sensitive_change = True
        
    # 2. Nếu có thay đổi nhạy cảm -> Bắt buộc kiểm tra OTP
    if is_sensitive_change:
        otp_input = data.get('otp') # Lấy mã OTP gửi kèm
        
        if not otp_input:
            # Báo cho Frontend biết là cần phải hỏi OTP
            return {"status": "require_otp", "message": "Thay đổi Email/SĐT cần xác thực OTP"}
        
        # Kiểm tra mã OTP
        if current_user.verification_code != otp_input:
            return {"status": "error", "message": "Mã xác thực không đúng!"}
        
        # Nếu đúng -> Xóa mã OTP đi (để không dùng lại được)
        current_user.verification_code = None

    # 3. Tiến hành cập nhật
    current_user.email = new_email
    current_user.phone = new_phone
    
    # (Mật khẩu xử lý ở API riêng, nhưng nếu muốn giữ logic cũ thì để lại dòng này, tuy nhiên nên bỏ đi để bảo mật hơn)
    # if data.get('password'): current_user.password = data['password'] 
    
    db.commit()
    return {"status": "success", "message": "Cập nhật thông tin thành công!"}

# =========================
# 4. ROUTE HIỂN THỊ (TRUYỀN FULL_NAME RA HTML)
# =========================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def reg(request: Request): return templates.TemplateResponse("register.html", {"request": request})

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot(request: Request): return templates.TemplateResponse("forgotpw.html", {"request": request})
@app.get("/logout")
async def logout(response: Response): response = RedirectResponse("/"); response.delete_cookie("current_user"); return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    u = get_current_user(request, db)
    if not u: return RedirectResponse("/")
    
    classrooms = db.query(Classroom).all()
    total_teachers = db.query(User).filter(User.role == 'teacher').count()
    total_rooms = len(classrooms)
    active_rooms = len([r for r in classrooms if r.status == 'Available'])
    
    if u.role == 'admin': booking_count = db.query(Booking).count()
    else: booking_count = db.query(Booking).filter(Booking.user_id == u.id).count()

    bookings_db = db.query(Booking).order_by(Booking.id.desc()).limit(10).all()
    history = []
    for b in bookings_db:
        room = db.query(Classroom).filter(Classroom.id == b.room_id).first()
        history.append({
            "booker": b.booker_name,
            "room_name": room.room_name if room else "Unknown",
            "time": b.start_time,
            "duration": b.duration_hours,
            "status": b.status
        })

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "username": u.username, 
        "full_name": u.full_name, # TRUYỀN TÊN THẬT
        "role": u.role, 
        "classrooms": classrooms, 
        "total": total_teachers, 
        "history": history,
        "total_rooms": total_rooms,
        "active_rooms": active_rooms,
        "booking_count": booking_count
    })

@app.get("/room-management", response_class=HTMLResponse)
async def room_mgmt(request: Request, db: Session = Depends(get_db)):
    u = get_current_user(request, db)
    if not u: return RedirectResponse("/")
    return templates.TemplateResponse("room_management.html", {
        "request": request, 
        "classrooms": db.query(Classroom).all(), 
        "role": u.role, 
        "username": u.username,
        "full_name": u.full_name # TRUYỀN TÊN THẬT
    })

@app.get("/booking-scheduler", response_class=HTMLResponse)
async def booking(request: Request, db: Session = Depends(get_db)):
    u = get_current_user(request, db)
    if not u: return RedirectResponse("/")
    bookings = [{"id":b.id, "room_id":b.room_id, "booker_name":b.booker_name, "start_time":b.start_time, "duration_hours":b.duration_hours} for b in db.query(Booking).all()]
    rooms = [{"id":c.id, "room_name":c.room_name, "capacity":c.capacity, "equipment":c.equipment, "status":c.status} for c in db.query(Classroom).all()]
    return templates.TemplateResponse("booking_scheduler.html", {
        "request": request, 
        "classrooms": rooms, 
        "bookings": bookings, 
        "username": u.username, 
        "role": u.role,
        "full_name": u.full_name # TRUYỀN TÊN THẬT
    })

@app.get("/user-management", response_class=HTMLResponse)
async def user_mgmt(request: Request, db: Session = Depends(get_db)):
    u = get_current_user(request, db)
    if not u or u.role != "admin": return RedirectResponse("/dashboard")
    return templates.TemplateResponse("user_management.html", {
        "request": request, 
        "users": db.query(User).all(), 
        "username": u.username, 
        "role": u.role,
        "full_name": u.full_name # TRUYỀN TÊN THẬT
    })

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    u = get_current_user(request, db)
    if not u: return RedirectResponse("/")
    user_bookings = db.query(Booking).filter(Booking.user_id == u.id).all()
    history = []
    for b in user_bookings:
        room = db.query(Classroom).filter(Classroom.id == b.room_id).first()
        history.append({
            "room_name": room.room_name if room else "Unknown",
            "start_time": b.start_time,
            "duration": b.duration_hours,
            "status": b.status
        })
    return templates.TemplateResponse("profile.html", {
        "request": request, 
        "user": u, 
        "username": u.username, 
        "role": u.role, 
        "history": history,
        "full_name": u.full_name # TRUYỀN TÊN THẬT
    })

# --- Route trang Xác thực (BẠN ĐANG THIẾU DÒNG NÀY) ---
@app.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request): return templates.TemplateResponse("verify.html", {"request": request})

# --- 1. LOGIC GỬI MAIL (ĐÃ CÓ - GIỮ NGUYÊN) ---
# ... (Đoạn code import smtplib và hàm send_verification_email giữ nguyên như cũ) ...

# =========================================
# API CHO CHỨC NĂNG QUÊN MẬT KHẨU (FORGOT PASSWORD)
# =========================================

# Bước 1: Gửi mã OTP để lấy lại mật khẩu
@app.post("/api/forgot/send-otp")
async def forgot_send_otp(data: dict, db: Session = Depends(get_db)):
    # Tìm user theo tên đăng nhập
    user = db.query(User).filter(User.username == data['username']).first()
    if not user:
        return {"status": "error", "message": "Tên đăng nhập không tồn tại!"}
    
    # Gửi mã về email đã đăng ký của user đó
    otp = send_verification_email(user.email)
    if not otp:
        return {"status": "error", "message": "Lỗi hệ thống gửi mail. Vui lòng thử lại sau."}
    
    # Lưu mã vào DB
    user.verification_code = otp
    db.commit()
    
    # Trả về email (đã che bớt) để user biết mã gửi về đâu
    hidden_email = user.email[:3] + "****" + user.email.split('@')[1]
    return {"status": "success", "message": f"Mã xác thực đã gửi tới {hidden_email}"}

# Bước 2: Xác nhận mã OTP và Đổi mật khẩu mới
@app.post("/api/forgot/reset")
async def forgot_reset_pass(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data['username']).first()
    if not user: return {"status": "error", "message": "User không tồn tại"}

    # Kiểm tra khớp mã OTP
    if user.verification_code != data['otp']:
        return {"status": "error", "message": "Mã xác thực không đúng!"}
    
    # Đổi mật khẩu
    user.password = data['new_password']
    user.verification_code = None # Xóa mã sau khi dùng
    db.commit()
    
    return {"status": "success", "message": "Đổi mật khẩu thành công! Hãy đăng nhập."}


# =========================================
# API CHO CHỨC NĂNG ĐỔI MẬT KHẨU TRONG PROFILE
# =========================================

# Bước 1: Gửi mã OTP về email của người đang đăng nhập
@app.post("/api/profile/send-otp")
async def profile_send_otp(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return {"status": "error", "message": "Chưa đăng nhập!"}

    otp = send_verification_email(user.email)
    if not otp: return {"status": "error", "message": "Không thể gửi email."}

    user.verification_code = otp
    db.commit()
    return {"status": "success", "message": "Đã gửi mã xác thực về Email của bạn."}

# Bước 2: Xác nhận OTP và cập nhật mật khẩu mới
@app.post("/api/profile/change-password")
async def profile_change_pass(data: dict, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return {"status": "error", "message": "Chưa đăng nhập!"}

    if user.verification_code != data['otp']:
        return {"status": "error", "message": "Mã xác thực sai!"}
    
    user.password = data['new_password']
    user.verification_code = None
    db.commit()
    return {"status": "success", "message": "Cập nhật mật khẩu thành công!"}

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)