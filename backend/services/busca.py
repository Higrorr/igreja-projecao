"""
busca.py
========

Pesquisa unificada sobre o índice SQLite: Bíblia, Harpa e Playbacks.

A busca roda em memória sobre as tabelas (pouco mais de 1.800 registros),
o que permite ignorar acentos sem depender de uma coluna normalizada.

Regras:
  - 1º token é tratado como livro (exato > prefixo > contém);
  - token numérico após o livro é o capítulo;
  - query só numérica ("133") -> hino da Harpa;
  - resto da query busca no título da Harpa e nos playbacks.
"""

from backend.database import database
from backend.services import livros


def _serial_biblia(r) -> dict:
    return {
        "tipo": "biblia",
        "id": r["id"],
        "livro": r["livro"],
        "livro_exibicao": livros.nome_exibicao(r["livro"]),
        "capitulo": r["capitulo"],
        "arquivo": r["arquivo"],
        "caminho": r["caminho"],
    }


def _serial_harpa(r) -> dict:
    return {
        "tipo": "harpa",
        "id": r["id"],
        "numero": r["numero"],
        "titulo": r["titulo"] or "",
        "arquivo": r["arquivo"],
        "caminho": r["caminho"],
    }


def _serial_playback(r) -> dict:
    return {
        "tipo": "playback",
        "id": r["id"],
        "titulo": r["titulo"],
        "youtube_id": r["youtube_id"],
        "url": r["url"],
        "favorito": r["favorito"],
    }


def buscar(q: str, limite: int = 40) -> dict:
    q = (q or "").strip()
    if not q:
        return {"biblia": [], "harpa": [], "playback": []}

    conn = database.conectar()
    try:
        biblia_rows = conn.execute(
            "SELECT id, livro, capitulo, arquivo, caminho FROM biblia "
            "ORDER BY livro, capitulo"
        ).fetchall()
        harpa_rows = conn.execute(
            "SELECT id, numero, titulo, arquivo, caminho FROM harpa ORDER BY numero"
        ).fetchall()
        play_rows = conn.execute(
            "SELECT id, titulo, youtube_id, url, favorito FROM playback "
            "ORDER BY titulo"
        ).fetchall()
    finally:
        conn.close()

    q_norm = livros.normalizar(q)
    tokens = q_norm.split()

    resultado = {"biblia": [], "harpa": [], "playback": []}

    # ----- Bíblia ----------------------------------------------------
    livro = livros.procurar_livro(tokens[0]) if tokens else None
    capitulo = None
    for t in tokens[1:]:
        if t.isdigit():
            capitulo = int(t)
            break

    if livro:
        cap = capitulo if capitulo else None
        chaves = [r for r in biblia_rows if r["livro"] == livro]
        if cap is not None:
            chaves = [r for r in chaves if r["capitulo"] == cap]
        resultado["biblia"] = [_serial_biblia(r) for r in chaves[:limite]]
    elif len(tokens) == 1 and not tokens[0].isdigit():
        # livro parcial: lista os capítulos dos candidatos para o usuário escolher
        cands = livros.candidatos_livro(tokens[0])
        if cands:
            for sem in cands:
                for r in biblia_rows:
                    if r["livro"] == sem:
                        resultado["biblia"].append(_serial_biblia(r))
                if len(resultado["biblia"]) >= limite:
                    break

    # ----- Harpa ------------------------------------------------------
    if q_norm.isdigit():
        numero = int(q_norm)
        for r in harpa_rows:
            if r["numero"] == numero:
                resultado["harpa"].append(_serial_harpa(r))
                break
    else:
        for r in harpa_rows:
            if q_norm in livros.normalizar(r["titulo"] or ""):
                resultado["harpa"].append(_serial_harpa(r))
                if len(resultado["harpa"]) >= limite:
                    break

    # ----- Playbacks ---------------------------------------------------
    for r in play_rows:
        if q_norm in livros.normalizar(r["titulo"]):
            resultado["playback"].append(_serial_playback(r))
            if len(resultado["playback"]) >= 10:
                break

    return resultado