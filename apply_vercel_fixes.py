import os
import re

print("Applying Vercel fixes...")

# 1. Fix Database SQLite Path
db_path = "backend/app/core/database.py"
with open(db_path, "r", encoding="utf-8") as f:
    db_content = f.read()

if "os.getenv(\"VERCEL\")" not in db_content:
    db_content = db_content.replace(
        "return \"sqlite+aiosqlite:///./batch_history.db\"",
        "import os\n    if os.getenv(\"VERCEL\"):\n        return \"sqlite+aiosqlite:////tmp/batch_history.db\"\n    return \"sqlite+aiosqlite:///./batch_history.db\""
    )
    with open(db_path, "w", encoding="utf-8") as f:
        f.write(db_content)
    print("Fixed database.py")

# 2. Create api/index.py
os.makedirs("api", exist_ok=True)
with open("api/index.py", "w", encoding="utf-8") as f:
    f.write("""import os
import sys

# Ensure backend directory is in the python path
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(current_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
""")
print("Created api/index.py")

# 3. Create vercel.json
with open("vercel.json", "w", encoding="utf-8") as f:
    f.write("""{
  "version": 2,
  "buildCommand": "npm run build",
  "outputDirectory": "frontend/dist",
  "installCommand": "npm install --prefix frontend",
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    },
    {
      "src": "frontend/package.json",
      "use": "@vercel/vite"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/api/index.py"
    },
    {
      "src": "/health",
      "dest": "/api/index.py"
    },
    {
      "src": "/docs",
      "dest": "/api/index.py"
    },
    {
      "src": "/openapi.json",
      "dest": "/api/index.py"
    },
    {
      "src": "/(.*)",
      "dest": "/frontend/$1"
    }
  ]
}""")
print("Created vercel.json")

# 4. Check __init__.py files
for root, dirs, files in os.walk("backend/app"):
    if "__init__.py" not in files:
        with open(os.path.join(root, "__init__.py"), "w", encoding="utf-8") as f:
            pass
print("Checked __init__.py files")

# 5. Fix config defaults if necessary
config_path = "backend/app/core/config.py"
with open(config_path, "r", encoding="utf-8") as f:
    config_content = f.read()

# Configs already have default values based on previous inspection
print("Checked config.py")

print("All fixes applied successfully.")
