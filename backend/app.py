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
from backend.services import agenda, busca, projetor, scanner, youtube as yt

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
        return jsonify({"biblia": b, "harpa": h, "projecao": projetor.tipo_projecao()})
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


@app.route("/api/youtube/salvar_link", methods=["POST"])
def youtube_salvar_link():
    """Salva um playback colando um link (YouTube ou outro)."""
    dados = request.get_json(silent=True) or {}
    url = dados.get("url")
    titulo = dados.get("titulo") or ""
    if not url:
        return jsonify({"erro": "Informe o link."}), 400
    try:
        return jsonify(yt.salvar_por_url(url, titulo)), 201
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400


@app.route("/api/playback/<int:playback_id>", methods=["DELETE"])
def playback_remover(playback_id):
    """Remove um playback (YouTube ou link) pelo id."""
    if not yt.remover_por_id(playback_id):
        return jsonify({"erro": "Playback não encontrado."}), 404
    return jsonify({"ok": True})


@app.route("/api/playback/<int:playback_id>", methods=["PUT"])
def playback_renomear(playback_id):
    """Renomeia um playback salvo (passa a ser pesquisável pelo novo nome)."""
    dados = request.get_json(silent=True) or {}
    try:
        return jsonify(yt.renomear(playback_id, dados.get("titulo") or ""))
    except KeyError:
        return jsonify({"erro": "Playback não encontrado."}), 404
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400


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


@app.route("/api/agenda")
def agenda_listar():
    """Lista as fichas da agenda (ordem de programação do culto)."""
    database.criar_tabelas()
    return jsonify(agenda.listar())


@app.route("/api/agenda", methods=["POST"])
def agenda_criar():
    dados = request.get_json(silent=True) or {}
    try:
        ficha = agenda.criar(
            dados.get("nome"), dados.get("texto"),
            dados.get("tipo"), dados.get("ref_id"),
        )
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    return jsonify(ficha), 201


@app.route("/api/agenda/<int:ficha_id>", methods=["PUT"])
def agenda_atualizar(ficha_id):
    dados = request.get_json(silent=True) or {}
    try:
        ficha = agenda.atualizar(
            ficha_id,
            nome=dados.get("nome", agenda._NAO_INFORMADO),
            texto=dados.get("texto", agenda._NAO_INFORMADO),
            tipo=dados.get("tipo", agenda._NAO_INFORMADO),
            ref_id=dados.get("ref_id", agenda._NAO_INFORMADO),
        )
    except KeyError as e:
        return jsonify({"erro": str(e)}), 404
    return jsonify(ficha)


@app.route("/api/agenda/ordenar", methods=["POST"])
def agenda_ordenar():
    dados = request.get_json(silent=True) or {}
    ids = dados.get("ids") or []
    agenda.reordenar([int(i) for i in ids])
    return jsonify({"ok": True})


@app.route("/api/agenda/<int:ficha_id>", methods=["DELETE"])
def agenda_remover(ficha_id):
    if not agenda.remover(ficha_id):
        return jsonify({"erro": "Ficha não encontrada."}), 404
    return jsonify({"ok": True})


@app.route("/api/agenda/<int:ficha_id>/projetar", methods=["POST"])
def agenda_projetar(ficha_id):
    """Projeta/abre o item da ficha escolhida na agenda."""
    try:
        return jsonify(agenda.projetar(ficha_id, request.host))
    except KeyError:
        return jsonify({"erro": "Ficha não encontrada."}), 404
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422
    except Exception:
        app.logger.exception("Falha ao projetar ficha da agenda")
        return jsonify({"erro": "Erro interno ao projetar."}), 500


@app.route("/api/projecao/tela_preta", methods=["POST"])
def projecao_tela_preta():
    """Alterna a projeção de tela preta (ligar/desligar)."""
    try:
        return jsonify(projetor.tela_preta(request.host))
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422


@app.route("/api/projecao/acao", methods=["POST"])
def projecao_acao():
    """Ação remota sobre a projeção: slide_proximo/anterior, play_pause."""
    dados = request.get_json(silent=True) or {}
    acao = dados.get("acao")
    try:
        return jsonify(projetor.acao_projecao(acao, request.host))
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422


@app.route("/api/projecao/primeiro_plano", methods=["POST"])
def projecao_primeiro_plano():
    """Traz a projeção atual (PPT ou player) para o primeiro plano/tela cheia."""
    try:
        return jsonify(projetor.primeiro_plano())
    except projetor.ErroProjecao as e:
        return jsonify({"erro": str(e)}), 422


@app.route("/api/player/comando")
def player_comando():
    """Comando pendente consumido pelo player (polling de play/pause)."""
    return jsonify(projetor.pegar_comando_player())


if __name__ == "__main__":
    database.criar_tabelas()
    app.run(host="0.0.0.0", port=5000, debug=True)
