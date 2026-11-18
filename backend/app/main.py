import os
from fastapi import FastAPI, Request

from app.api import auth, calls, health, reports

dev = os.getenv('APP_ENV') == 'development'
app = FastAPI(title='CallGuard AI API', version='0.2.0', docs_url='/docs' if dev else None,
              redoc_url=None, openapi_url='/openapi.json' if dev else None)

@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return response

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(calls.router)
app.include_router(reports.router)
