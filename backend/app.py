"""
app.py
======

Aplicação Flask do sistema de projeção para cultos.

Serve o frontend responsivo e expõe as rotas da API. Escuta em 0.0.0.0
para que o celular (usado como controle) acesse via rede local.

Uso:
    python -m backend.app
"""

import json

from flask import Flask, jsonify, request, render_template

from backend import config
from backend.database import database
from backend.services import busca, projetor, scanner

app = Flask(
    __name__,
    static_folder=config.FRONTEND_DIR,
    static_url_path="",
    template_folder=config.FRONTEND_DIR,
)


@app.route("/")
def index():
    """Serve a interface."""
    return render_template("index.html")


@app.route("/api/status")
def status():
    """Resumo do acervo indexado."""
    database.criar_tabelas()
    conn = database.conectar()
    try:
        b = conn.execute("SELECT COUNT(*) c FROM biblia").fetchone()["c"]
        h = conn.execute("SELECT COUNT(*) c FROM harpa").fetchone()["c"]
        return jsonify({"biblia": b, "harpa": h})
    finally:
        conn.close()


@app.route("/api/atualizar", methods=["POST"])
def atualizar():
    """Roda o scanner e devolve o resultado."""
    resumo = scanner.escanear_tudo()
    return jsonify(resumo)


@app.route("/api/pesquisa")
def pesquisa():
    """Pesquisa unificada: Bíblia + Harpa + Playbacks."""
    q = request.args.get("q", "")
    limite = request.args.get("limite", 40, type=int)
    return jsonify(busca.buscar(q, limite))


@app.route("/api/projetar", methods=["POST"])
def projetar():
    """Projeta o item no PowerPoint ou abre o playback."""
    dados = request.get_json(silent=True) or {}
    tipo = dados.get("tipo")
    item_id = dados.get("id")
    if tipo not in ("biblia", "harpa", "playback") or item_id is None:
        return jsonify({"erro": "Parâmetros inválidos."}), 400
    try:
        resultado = projetor.projetar(tipo, int(item_id))
        return jsonify(resultado)
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422
    except Exception as e:
        return jsonify({"erro": f"Erro interno: {e}"}), 500


if __name__ == "__main__":
    database.criar_tabelas()
    app.run(host="0.0.0.0", port=5000, debug=True)
