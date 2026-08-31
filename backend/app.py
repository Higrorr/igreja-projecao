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
import re

from flask import Flask, jsonify, request, render_template, redirect

from backend import config
from backend.database import database
from backend.services import busca, projetor, scanner, youtube as yt

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


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")


@app.route("/player/<youtube_id>")
def player(youtube_id):
    """Página local de tela cheia que embute o vídeo (sem UI do YouTube)."""
    if not _VIDEO_ID_RE.match(youtube_id or ""):
        return redirect("/")
    return render_template("player.html", youtube_id=youtube_id)


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


@app.route("/api/playbacks")
def listar_playbacks():
    """Lista os playbacks favoritos salvos."""
    return jsonify(yt.listar_favoritos())


@app.route("/api/canais/prioridade")
def listar_canais_prioridade():
    """Lista os canais prioritários (podem ser criados/removidos pela irmã)."""
    return jsonify(yt.listar_canais_prioridade())


@app.route("/api/canais/prioridade", methods=["POST"])
def adicionar_canal_prioridade():
    """Marca um canal como prioritário na busca do YouTube."""
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Falta nome do canal."}), 400
    canal = yt.adicionar_canal_prioridade(
        nome, (dados.get("channel_id") or "").strip() or None
    )
    return jsonify(canal), 201


@app.route("/api/canais/prioridade/<int:canal_id>", methods=["DELETE"])
def remover_canal_prioridade(canal_id):
    """Remove um canal da lista de prioritários."""
    if not yt.remover_canal_prioridade(canal_id):
        return jsonify({"erro": "Canal não encontrado."}), 404
    return jsonify({"ok": True})


@app.route("/api/youtube")
def youtube_pesquisa():
    """Pesquisa ao vivo no YouTube (usa cache de ~24h se tiver)."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"resultados": [], "fonte": "vazio", "erro": None})
    try:
        dados = yt.pesquisar(
            q,
            playback=request.args.get("playback", "1") != "0",
            instrumental=request.args.get("instrumental", "1") != "0",
            vivo=request.args.get("vivo", "0") == "1",
            forcar=request.args.get("forcar", "0") == "1",
        )
        return jsonify(dados)
    except yt.ErroYoutube as e:
        return jsonify({"resultados": [], "fonte": "erro", "erro": str(e)})


@app.route("/api/youtube/favoritar", methods=["POST"])
def youtube_favoritar():
    """Salva um vídeo achado na busca como favorito."""
    dados = request.get_json(silent=True) or {}
    yid = dados.get("youtube_id")
    if not yid:
        return jsonify({"erro": "Falta youtube_id."}), 400
    return (
        jsonify(yt.favoritar(yid, dados.get("titulo") or "Playback", dados.get("url"))),
        201,
    )


@app.route("/api/youtube/desfavoritar", methods=["POST"])
def youtube_desfavoritar():
    """Remove um vídeo dos favoritos."""
    dados = request.get_json(silent=True) or {}
    yid = dados.get("youtube_id")
    if not yid:
        return jsonify({"erro": "Falta youtube_id."}), 400
    yt.desfavoritar(yid)
    return jsonify({"ok": True})


@app.route("/api/youtube/abrir", methods=["POST"])
def youtube_abrir():
    """Abre o vídeo no navegador da máquina (projeção)."""
    dados = request.get_json(silent=True) or {}
    yid = dados.get("youtube_id")
    if not yid:
        return jsonify({"erro": "Falta youtube_id."}), 400
    try:
        return jsonify(projetor.abrir_youtube(yid, request.host))
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422


@app.route("/api/projetar", methods=["POST"])
def projetar():
    """Projeta o item no PowerPoint ou abre o playback."""
    dados = request.get_json(silent=True) or {}
    tipo = dados.get("tipo")
    item_id = dados.get("id")
    if tipo not in ("biblia", "harpa", "playback") or item_id is None:
        return jsonify({"erro": "Parâmetros inválidos."}), 400
    try:
        resultado = projetor.projetar(tipo, int(item_id), request.host)
        return jsonify(resultado)
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422
    except Exception as e:
        app.logger.exception("Falha interna ao projetar")
        return jsonify({"erro": f"Erro interno: {e}"}), 500


if __name__ == "__main__":
    database.criar_tabelas()
    app.run(host="0.0.0.0", port=5000, debug=True)
