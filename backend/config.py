"""
config.py
=========

Configurações centrais do sistema. Centraliza os caminhos do projeto para
que os demais módulos não precisem calcular caminhos absolutos manualmente.

No executável compilado (PyInstaller), a "raiz" é a pasta onde o .exe está:
o acervo/ fica ao LADO do executável, não embutido nele.
"""

import os
import sys

# Diretório raiz do projeto.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pasta do acervo (onde ficam os PPTX).
ACERVO_DIR = os.path.join(BASE_DIR, "acervo")

# Pastas individuais do acervo.
BIBLIA_DIR = os.path.join(ACERVO_DIR, "biblia-ALM1911")
HARPA_DIR = os.path.join(ACERVO_DIR, "harpa")

# Pasta do banco de dados (criada na primeira execução, ao lado do executável).
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "slides.db")

# Pasta do frontend (HTML/CSS/JS) servida pelo Flask.
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Chave da YouTube Data API v3 (search.list). Vem de backend/secrets.py
# (arquivo embutido no exe via PyInstaller e não versionado); pode ser
# sobrescrita por variável de ambiente YOUTUBE_API_KEY.
_env_key = os.environ.get("YOUTUBE_API_KEY", "")
if _env_key:
    YOUTUBE_API_KEY = _env_key
else:
    try:
        from backend import secrets as _secrets
        YOUTUBE_API_KEY = getattr(_secrets, "YOUTUBE_API_KEY", "") or ""
    except Exception:
        YOUTUBE_API_KEY = ""