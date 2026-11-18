from fastapi import FastAPI

from app.api import auth, calls, health, reports

app = FastAPI(title='CallGuard AI API', version='0.1.0')
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(calls.router)
app.include_router(reports.router)
