from fastapi import FastAPI, Depends, HTTPException, Response, Request
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import bcrypt
from jose import jwt
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from jose import JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("FATAL ERROR: SECRET_KEY is missing from environment variables.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app=FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,                   
    allow_methods=["*"],
    allow_headers=["*"],
)


DATABASE_URL = "sqlite:///./taskmanager.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String)


# @app.get("/")
# def root():
#     return {"message": "Task Manager API Running"}


def add_user(db, username, password, role):

    hashed_password=hash_password(password)
    user=User(
        username=username,
        password=hashed_password,
        role=role,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


class register_request(BaseModel):
    username:str
    password:str
    role:str


class login_request(BaseModel):
    username:str
    password:str


@app.post("/register")
def register(data: register_request,response:Response, db=Depends(get_db)):

    if not data.username.strip():
        raise HTTPException(400, "Username cannot be empty")

    if not data.password.strip():
        raise HTTPException(400, "Password cannot be empty")

    existing_user=db.query(User).filter(User.username==data.username).first()

    if existing_user:
        raise HTTPException(400, "Username already exists")
    
    user= add_user(db, data.username, data.password, data.role)

    token=create_access_token({
        "sub":user.username,
        "id":user.id,
        "role":user.role
    })

    response.delete_cookie("access_token")

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
    )

    return {"message":"registration successful"}


@app.get("/users")
def get_users(db=Depends(get_db)):
    users=db.query(User).all()
    return users


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(
        plain_password.encode(),
        hashed_password.encode()
    )


@app.post("/login")
def login(data: login_request,response:Response, db=Depends(get_db)):

    if not data.username.strip():
        raise HTTPException(400, "Username cannot be empty")

    if not data.password.strip():
        raise HTTPException(400, "Password cannot be empty")


    user=db.query(User).filter(User.username==data.username).first()

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(401, "invalid credentials")
    
    token=create_access_token({
        "sub": user.username,
        "id": user.id,
        "role": user.role
    })

    response.delete_cookie("access_token")

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax"
    )

    return {"message": "login successful"}


def create_access_token(data:dict):

    to_encode=data.copy()
    expire_time=datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp":expire_time})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token:str):
    try:
        payload=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(401, "invalid or expired token")


security=HTTPBearer(auto_error=False)

def get_current_user(
        request:Request,
        credentials: HTTPAuthorizationCredentials=Depends(security)
):
    token=None
    if credentials:
        token=credentials.credentials
    if not token:
        token=request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "not authenticated")
    return decode_token(token)


@app.get("/protected")
def protected_access(user=Depends(get_current_user)):
    return {
        "message": "access granted",
        "user": user["sub"]
    }


def check_role(user, allowed_roles):
    if user["role"] not in allowed_roles:
        raise HTTPException(403, "action not allowed")
    

@app.get("/manager-only")
def manager_route(user=Depends(get_current_user)):
    check_role(user, ["manager"])
    return {"message": "manager access granted"}


class Task(Base):
    __tablename__="tasks"

    id=Column(Integer, primary_key=True, index=True)
    title=Column(String)
    description=Column(String)
    status=Column(String, default="created")

    assigned_by=Column(Integer)
    assigned_to=Column(Integer)

    deadline=Column(DateTime)

    review=Column(String, nullable=True)

    is_deleted = Column(Boolean, default=False)


class task_create_request(BaseModel):
    title: str
    description: str
    assigned_to: int
    deadline: datetime


@app.post("/tasks/create")
def create_task(data: task_create_request, db=Depends(get_db), user=Depends(get_current_user)):
    check_role(user, ["manager"])

    if not data.title.strip():
        raise HTTPException(400, "Task title cannot be empty")

    if not data.description.strip():
        raise HTTPException(400, "Task description cannot be empty")
    
    assigned_user = (
    db.query(User)
    .filter(User.id == data.assigned_to)
    .first()
    )

    if not assigned_user:
        raise HTTPException(404, "Assigned user does not exist")

    if assigned_user.role != "employee":
        raise HTTPException(400, "Tasks can only be assigned to employees")

    task=Task(
        title=data.title,
        description=data.description,
        status="created",
        assigned_by=user["id"],
        assigned_to=data.assigned_to,
        deadline=data.deadline
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    history=TaskHistory(
        task_id=task.id,
        changed_by=user["id"],
        old_status=None,
        new_status="created",
    )

    db.add(history)
    db.commit()

    return {"message": "task created"}


@app.get("/tasks")
def get_all_tasks(db=Depends(get_db)):
    return db.query(Task).all()


@app.post("/tasks/accept/{task_id}")
def accept_task(task_id:int, user=Depends(get_current_user), db=Depends(get_db)):

    check_role(user, ["employee"])

    task=db.query(Task).filter(Task.id==task_id).first()

    if not task:
        raise HTTPException(404, "task does not exist")
    if task.assigned_to!=user["id"]:
        raise HTTPException(403, "task does not belong to this user")
    if task.status!="created":
        raise HTTPException(400, "task already accepted")
    
    history=TaskHistory(
        task_id=task_id,
        changed_by=user["id"],
        old_status=task.status,
        new_status="in_progress",
    )

    db.add(history)
    
    task.status="in_progress"

    db.commit()

    return {"message": "task accepted"}


@app.post("/tasks/complete/{task_id}")
def complete_task(task_id:int, user=Depends(get_current_user), db=Depends(get_db)):

    check_role(user, ["employee"])

    task=db.query(Task).filter(Task.id==task_id).first()

    if not task:
        raise HTTPException(404, "task does not exist")
    if task.assigned_to!=user["id"]:
        raise HTTPException(403, "task does not belong to this user")
    if task.status!="in_progress":
        raise HTTPException(401, "task is not in progress")
    
    current_time=datetime.now(timezone.utc)
    deadline=task.deadline

    if deadline.tzinfo is None:
        deadline=deadline.replace(tzinfo=timezone.utc)

    within_deadline=current_time<=deadline

    history=TaskHistory(
        task_id=task_id,
        changed_by=user["id"],
        old_status=task.status,
        new_status="completed",
        within_deadline=within_deadline,
    )
    
    db.add(history)

    task.status="completed"

    db.commit()

    return {"message": "task completed"}


@app.post("/tasks/review/{task_id}")
def review_task(task_id: int,review: str, user=Depends(get_current_user), db= Depends(get_db)):

    check_role(user, ["manager"])

    task=db.query(Task).filter(Task.id==task_id).first()

    if not task:
        raise HTTPException(404, "task does not exist")
    if task.assigned_by!=user["id"]:
        raise HTTPException(403, "task does not belong to this user")
    if task.status!="completed":
        raise HTTPException(400, "task is not completed yet")
    
    task_history=db.query(TaskHistory).filter(TaskHistory.task_id==task_id,
                                               TaskHistory.new_status=="completed").order_by(TaskHistory.timestamp.desc()).first()
    within_deadline=task_history.within_deadline if task_history else None

    history=TaskHistory(
        task_id=task_id,
        changed_by=user["id"],
        old_status=task.status,
        new_status="reviewed",
        within_deadline=within_deadline
    )

    db.add(history)

    task.review= review
    task.status= "reviewed"

    db.commit()

    return {"message": "task is reviewed"}


class TaskHistory(Base):
    __tablename__="task_histroy"

    id=Column(Integer, primary_key=True, index=True)

    task_id=Column(Integer)
    changed_by=Column(Integer)

    old_status=Column(String)
    new_status=Column(String)

    within_deadline=Column(Boolean, nullable=True)
    timestamp=Column(DateTime, default= lambda: datetime.now(timezone.utc))


Base.metadata.create_all(bind=engine)

@app.get("/tasks/history")
def get_all_task_history(db=Depends(get_db)):
    return db.query(TaskHistory).all()


@app.get("/tasks/my")
def get_my_tasks(
    limit:int=10,
    offset:int=0,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    if user["role"]=="manager":
        query= db.query(Task).filter(Task.assigned_by==user["id"], Task.is_deleted == False)
    
    elif user["role"]=="employee":
        query= db.query(Task).filter(Task.assigned_to==user["id"], Task.is_deleted == False)
    
    else:
        raise HTTPException(403, "Invalid role!")
    
    total_count=query.count()
    
    tasks=query.offset(offset).limit(limit).all()

    enriched_tasks = []

    for task in tasks:

        completed_record = (
            db.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task.id,
                TaskHistory.new_status == "completed"
            )
            .order_by(TaskHistory.timestamp.desc())
            .first()
        )

        enriched_tasks.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "review": task.review,
            "deadline": task.deadline,

            "completed_at": completed_record.timestamp if completed_record else None,
            "within_deadline": completed_record.within_deadline if completed_record else None
        })

    return {
        "tasks": enriched_tasks,   # ✅ CRITICAL CHANGE
        "count": len(enriched_tasks),
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


#Additions for Frontend implementation

@app.get("/users/me")
def get_current_user_info(user=Depends(get_current_user)):
    return{
        "username":user["sub"],
        "id":user["id"],
        "role":user["role"]
    }


@app.post("/logout")
def logout(response:Response):
    response.delete_cookie(
        key="access_token"
    )

    return {"message":"logout successful"}


@app.delete("/tasks/delete/{task_id}")
def delete_task(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):

    check_role(user, ["manager"])

    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(404, "Task not found")

    if task.assigned_by != user["id"]:
        raise HTTPException(403, "Cannot delete this task")

    task.is_deleted = True

    history = TaskHistory(
        task_id=task_id,
        changed_by=user["id"],
        old_status=task.status,
        new_status="deleted"
    )

    db.add(history)
    db.commit()

    return {"message": "Task deleted"}

# Serve the frontend files
app.mount("/", StaticFiles(directory=".", html=True), name="static")