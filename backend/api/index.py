import os
import sys
import traceback

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from app.main import app
except Exception as exc:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Hit Digital - Startup Diagnostic")
    err_str = str(exc)
    err_tb = traceback.format_exc()

    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
    async def diagnostic_fallback(path_name: str):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Erro de importacao/inicializacao no ambiente Vercel.",
                "error": err_str,
                "traceback": err_tb.splitlines(),
                "sys_path": sys.path,
                "cwd": os.getcwd(),
                "files": os.listdir(backend_dir) if os.path.exists(backend_dir) else [],
            },
        )
