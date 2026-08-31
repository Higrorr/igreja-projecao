"""
run.py
======

Ponto de entrada para o executável compilado (PyInstaller).

Usa debug=False e desliga o reloader: no .exe o processamento é único
(um processo), e a interface do projeto não é para desenvolvimento.
"""

from backend.app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)