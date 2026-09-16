#!/usr/bin/env python3
"""
Runner Unificado de Comando Único (Full Stack)
Inicializa o Backend (FastAPI/Uvicorn) e Frontend (Vite/React) de forma concorrente,
gerenciando ciclo de vida, dependências e finalização limpa de processos.
"""

import atexit
import os
import shutil
import signal
import subprocess
import sys
import time
from typing import List, Optional

# Garante suporte a UTF-8 no terminal Windows para evitar UnicodeEncodeError (cp1252)
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

IS_WINDOWS = sys.platform.startswith("win")

# Cores ANSI para formatação profissional no terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_step(message: str) -> None:
    bullet = "➜" if not IS_WINDOWS else ">>"
    print(f"{CYAN}{bullet}{RESET} {BOLD}{message}{RESET}")


def print_success(message: str) -> None:
    check = "✔" if not IS_WINDOWS else "[OK]"
    print(f"{GREEN}{check}{RESET} {message}")


def print_warning(message: str) -> None:
    warn = "⚠" if not IS_WINDOWS else "[AVISO]"
    print(f"{YELLOW}{warn}{RESET} {message}")


def resolve_python_executable(root_dir: str) -> str:
    """Detecta se há um ambiente virtual local (.venv) ou utiliza o Python atual."""
    venv_win = os.path.join(root_dir, "backend", ".venv", "Scripts", "python.exe")
    venv_unix = os.path.join(root_dir, "backend", ".venv", "bin", "python")

    if IS_WINDOWS and os.path.isfile(venv_win):
        return venv_win
    if not IS_WINDOWS and os.path.isfile(venv_unix):
        return venv_unix

    return sys.executable


def resolve_npm_executable() -> str:
    """Localiza o binário correto do npm conforme o sistema operacional."""
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    found = shutil.which(npm_cmd)
    if not found:
        return "npm.cmd" if IS_WINDOWS else "npm"
    return found


def ensure_backend_dependencies(python_bin: str, root_dir: str) -> None:
    """Verifica e instala dependências do backend de forma silenciosa e rápida."""
    req_file = os.path.join(root_dir, "backend", "requirements.txt")
    if not os.path.isfile(req_file):
        return

    print_step("Verificando dependencias do backend (Python)...")
    try:
        cmd = [python_bin, "-m", "pip", "install", "-q", "-r", req_file]
        subprocess.run(cmd, check=True, cwd=os.path.join(root_dir, "backend"))
        print_success("Dependencias do backend validadas.")
    except Exception as exc:
        print_warning(f"Aviso ao verificar dependencias do backend: {exc}")


def ensure_frontend_dependencies(npm_bin: str, root_dir: str) -> None:
    """Verifica e instala pacotes do frontend se node_modules não existir."""
    frontend_dir = os.path.join(root_dir, "frontend")
    node_modules = os.path.join(frontend_dir, "node_modules")

    if not os.path.isdir(node_modules):
        print_step("Diretorio node_modules ausente. Instalando dependencias do frontend (npm)...")
        try:
            subprocess.run([npm_bin, "install"], check=True, cwd=frontend_dir)
            print_success("Dependencias do frontend instaladas com sucesso.")
        except Exception as exc:
            print_warning(f"Erro ao executar npm install: {exc}")
    else:
        print_success("Dependencias do frontend ja instaladas.")


active_processes: List[subprocess.Popen] = []


def cleanup_all_processes() -> None:
    """Garante que todos os processos e árvores de filhos sejam encerrados."""
    global active_processes
    for proc in active_processes:
        kill_process_tree(proc)
    active_processes.clear()


atexit.register(cleanup_all_processes)


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Encerra recursivamente uma árvore de processos para liberar portas."""
    if proc.poll() is not None:
        return

    pid = proc.pid
    try:
        if IS_WINDOWS:
            # Finalização forçada em árvore no Windows via taskkill
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Finalização em grupo de processos no Linux/macOS
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def print_banner() -> None:
    """Exibe o painel visual formatado no terminal conforme especificado."""
    rocket = "🚀" if not IS_WINDOWS else "[*]"
    pc = "💻" if not IS_WINDOWS else ">>"
    gear = "⚙️" if not IS_WINDOWS else ">>"
    book = "📖" if not IS_WINDOWS else ">>"
    health = "🩺" if not IS_WINDOWS else ">>"

    banner = f"""
{CYAN}================================================================={RESET}
  {BOLD}{rocket} HIT DIGITAL - SISTEMA FULL STACK INICIALIZADO COM SUCESSO{RESET}
{CYAN}================================================================={RESET}
  {pc} {BOLD}Frontend Console{RESET} :  {GREEN}http://localhost:5173{RESET}
  {gear} {BOLD}Backend API{RESET}      :  {CYAN}http://localhost:8000{RESET}
  {book} {BOLD}Swagger Docs{RESET}     :  {CYAN}http://localhost:8000/docs{RESET}
  {health} {BOLD}Health Check{RESET}     :  {CYAN}http://localhost:8000/health{RESET}
{CYAN}================================================================={RESET}
  {DIM}[Pressione CTRL+C para encerrar todos os servicos]{RESET}
"""
    print(banner)


def main() -> None:
    root_dir = os.path.abspath(os.path.dirname(__file__))
    python_bin = resolve_python_executable(root_dir)
    npm_bin = resolve_npm_executable()

    print(f"\n{BOLD}Inicializando Runner Full Stack Hit Digital...{RESET}")
    print(f"{DIM}OS: {sys.platform} | Python: {python_bin} | npm: {npm_bin}{RESET}\n")

    # 1. Validação de pré-requisitos
    ensure_backend_dependencies(python_bin, root_dir)
    ensure_frontend_dependencies(npm_bin, root_dir)

    print_step("Iniciando servidores assincronos...")

    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")

    # Comandos de inicialização
    backend_cmd = [
        python_bin,
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]

    frontend_cmd = [npm_bin, "run", "dev"]

    backend_proc: Optional[subprocess.Popen] = None
    frontend_proc: Optional[subprocess.Popen] = None

    kwargs_backend = {"cwd": backend_dir}
    kwargs_frontend = {"cwd": frontend_dir}

    if not IS_WINDOWS:
        kwargs_backend["preexec_fn"] = os.setsid
        kwargs_frontend["preexec_fn"] = os.setsid

    try:
        backend_proc = subprocess.Popen(backend_cmd, **kwargs_backend)
        frontend_proc = subprocess.Popen(frontend_cmd, **kwargs_frontend)
        active_processes.extend([backend_proc, frontend_proc])

        # Aguarda 2 segundos para estabilização dos serviços
        time.sleep(2)

        # Exibe o banner informativo
        print_banner()

        # Monitora a execução até interrupção
        while True:
            if backend_proc.poll() is not None:
                print_warning("O processo do backend foi encerrado.")
                break
            if frontend_proc.poll() is not None:
                print_warning("O processo do frontend foi encerrado.")
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Interrupcao solicitada pelo usuario (Ctrl+C).{RESET}")
    finally:
        bullet = ">>" if IS_WINDOWS else "➜"
        check = "[OK]" if IS_WINDOWS else "✔"
        print(f"{CYAN}{bullet}{RESET} Encerrando processos do backend e frontend de forma segura...")
        if backend_proc:
            kill_process_tree(backend_proc)
        if frontend_proc:
            kill_process_tree(frontend_proc)

        time.sleep(1)
        print(f"{GREEN}{check}{RESET} Todos os servicos foram finalizados com sucesso.\n")


if __name__ == "__main__":
    main()
