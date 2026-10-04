import asyncio

import uvicorn

from app.runtime import loop_factory

if __name__ == '__main__':
    server = uvicorn.Server(uvicorn.Config('app.main:app', host='127.0.0.1', port=8000, loop='none'))
    asyncio.run(server.serve(), loop_factory=loop_factory)
