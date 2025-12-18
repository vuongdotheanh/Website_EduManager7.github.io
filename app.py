import re
import uvicorn
from json import dumps as json_dumps
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# =========================
# 1. CẤU HÌNH DATABASE
# =========================
SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True)
    full_name = Column(String)
    dob = Column(String)
    status = Column(String)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    email = Column(String, unique=True) 
    phone = Column(String) 
    role = Column(String, default="teacher")
    full_name = Column(String) # THÊM CỘT HỌ VÀ TÊN

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

# =========================
# 3. ROUTE API
# =========================
@app.post("/api/register")
async def register(data: dict, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data['username']).first():
        return {"status": "error", "message": "Tên đăng nhập đã tồn tại"}
    if db.query(User).filter(User.email == data['email']).first():
        return {"status": "error", "message": "Email này đã được sử dụng"}

    user_role = data.get('role', 'teacher') # Mặc định teacher như bạn yêu cầu
    
    # Kiểm tra mã GV
    if user_role == 'teacher':
        if data.get('teacher_code') != "EDU2025":
            return {"status": "error", "message": "Sai mã xác thực Giáo viên"}

    # LƯU HỌ VÀ TÊN VÀO DB
    new_user = User(
        username=data['username'], 
        password=data['password'], 
        email=data['email'], 
        phone=data['phone'], 
        role=user_role,
        full_name=data.get('full_name', data['username']) # Nếu không nhập thì lấy tạm username
    )
    db.add(new_user)
    db.commit()
    return {"status": "success"}

# --- API QUÊN MẬT KHẨU (MỚI) ---
# --- API QUÊN MẬT KHẨU (MỚI) ---
# --- API QUÊN MẬT KHẨU (ĐÃ CẬP NHẬT TÊN) ---
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

# --- API ĐẶT LỊCH (LƯU TÊN THẬT) ---
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
@app.post("/api/profile/update")
async def update_profile(data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user: return {"status": "error", "message": "Chưa đăng nhập!"}
    current_user.email = data.get('email', current_user.email)
    current_user.phone = data.get('phone', current_user.phone)
    # Cho phép cập nhật cả tên hiển thị nếu muốn
    # current_user.full_name = data.get('full_name', current_user.full_name) 
    if data.get('password'): current_user.password = data['password']
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

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)