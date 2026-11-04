import os

from dotenv import load_dotenv
load_dotenv()  # reads a .env file in the project root, if present — must run before other app imports

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .database import engine
from .routers import auth, buses, seats, bookings, payments, admin

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="YatraLine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your actual frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(buses.router)
app.include_router(seats.router)
app.include_router(bookings.router)
app.include_router(payments.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Static frontend mount MUST come last — Starlette matches mounted routes by
# prefix, so anything registered after "/" would otherwise be shadowed by it.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
