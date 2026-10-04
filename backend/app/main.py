import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from . import auth, tickets, workspaces
from .config import settings
from .db import engine

logger = logging.getLogger('flowdesk')


@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()


app = FastAPI(title='FlowDesk', version='0.1.0', lifespan=lifespan)


def error(request, status, message):
    codes = {401: 'UNAUTHENTICATED', 403: 'FORBIDDEN', 404: 'NOT_FOUND', 409: 'CONFLICT', 422: 'VALIDATION_ERROR'}
    return JSONResponse(status_code=status, content={'code': codes.get(status, 'SERVER_ERROR'), 'message': message, 'request_id': getattr(request.state, 'request_id', '')})


@app.middleware('http')
async def request_boundary(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('origin') not in settings.allowed_origins:
        response = error(request, 403, '请求来源校验失败')
    else:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('Unhandled request error request_id=%s', request.state.request_id)
            response = error(request, 500, '服务暂时不可用，请稍后重试')
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return error(request, exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return error(request, 422, '输入格式不正确，请检查必填项、长度和参数范围')


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return error(request, 409, '数据约束冲突，请刷新后重试')


@app.get('/api/v1/health')
async def health():
    return {'status': 'ok'}


for router in (auth.router, workspaces.router, tickets.router):
    app.include_router(router, prefix='/api/v1')
