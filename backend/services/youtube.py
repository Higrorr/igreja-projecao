"""
youtube.py
==========

Pesquisa ao vivo no YouTube via YouTube Data API v3 (sem scraping).

Fluxo:
    termo + filtros -> cache? -> API search.list -> ranqueamento -> cache

Limites da API (grátis, sem cartão):
    - 10.000 unidades/dia por projeto;
    - search.list custa 100 unidades -> ~100 pesquisas/dia;
    - por isso o cache: música repetida não gasta quota.

A classificação ("ranqueamento") é o que torna útil no culto: dá bônus para
títulos com "playback / instrumental / sem voz / karaokê" e penaliza
"ao vivo / ministração / pregação", a menos que a irmã queira "ao vivo".
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from backend import config
from backend.database import database
from backend.services import livros

# Id do 1º resultado de busca que não é um vídeo: alguns resultados ficam fora.
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,}$")

_PALAVRAS_BONUS = [
    "playback",
    "instrumental",
    "karaoke",
    "karaokê",
    "sem voz",
    "sem vocal",
    "backing track",
    "base instrumental",
    "backing",
    "sem letra",
]

_PALAVRAS_CASTIGO = [
    "ao vivo",
    "live",
    "performance",
    "ministra",  # pega "ministração", "ministrando"
    "prega",
    "prédica",
    "congresso",
    "igreja",
    "clipe oficial de ",
    "studio session",
]


class ErroYoutube(Exception):
    """Erro de comunicação/quota com a API, com mensagem amigável."""


# ---------------------------------------------------------------------------
# Comunicação com a API
# ---------------------------------------------------------------------------
def _montar_query(termo: str, playback: bool, instrumental: bool, vivo: bool) -> str:
    extras: list[str] = []
    if playback:
        extras.append("playback")
    if instrumental:
        extras.append("instrumental")
    if vivo:
        extras.append("ao vivo")
    return " ".join([termo] + extras).strip()


def _chamar_api(query: str) -> list:
    """Chama search.list e devolve a lista crua de items de vídeo."""
    if not config.YOUTUBE_API_KEY:
        raise ErroYoutube(
            "Chave do YouTube não configurada (backend/secrets.py). "
            "Habilite a YouTube Data API v3 no seu projeto e gere uma chave."
        )
    params = {
        "part": "snippet",
        "type": "video",
        "videoCategoryId": "10",  # Música
        "maxResults": "12",
        "q": query,
        "key": config.YOUTUBE_API_KEY,
    }
    url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(
        params
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            dados = json.load(r)
    except urllib.error.HTTPError as e:
        corpo = ""
        try:
            corpo = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        if e.code == 403 and "quota" in corpo.lower():
            raise ErroYoutube("Quota diária do YouTube esgotada. Tente amanhã.") from e
        raise ErroYoutube(f"YouTube respondeu com erro {e.code} (sem internet?).") from e
    except OSError as e:
        raise ErroYoutube("Sem conexão com o YouTube. Verifique a internet.") from e

    itens = [
        it
        for it in dados.get("items", [])
        if it.get("id", {}).get("kind") == "youtube#video"
    ]
    return itens


# Prioridade de canais: bônus aplicado aos resultados vindos de canais que a
# irmã marcou como preferidos (tabela canal_prioridade, editável na aba
# Playbacks). Governa a ordem e o badge "★ priorizado" no card.
_BONUS_CANAL_PRIORIZADO = 6


def listar_canais_prioridade() -> list:
    """Lista os canais marcados como prioritários na busca do YouTube."""
    conn = database.conectar()
    try:
        rows = conn.execute(
            "SELECT id, nome, channel_id FROM canal_prioridade "
            "ORDER BY LOWER(nome), id"
        ).fetchall()
        return [
            {"id": r["id"], "nome": r["nome"], "channel_id": r["channel_id"]}
            for r in rows
        ]
    finally:
        conn.close()


def adicionar_canal_prioridade(nome: str, channel_id: str | None = None) -> dict:
    """Marca um canal como prioritário. Reutiliza registro com mesmo nome."""
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Nome do canal obrigatório.")
    conn = database.conectar()
    try:
        existente = conn.execute(
            "SELECT id, nome FROM canal_prioridade WHERE LOWER(nome)=LOWER(?)",
            (nome,),
        ).fetchone()
        if existente:
            if channel_id:
                conn.execute(
                    "UPDATE canal_prioridade SET channel_id=? WHERE id=?",
                    (channel_id, existente["id"]),
                )
                conn.commit()
            return {
                "id": existente["id"],
                "nome": existente["nome"],
                "channel_id": channel_id,
            }
        cur = conn.execute(
            "INSERT INTO canal_prioridade (nome, channel_id) VALUES (?,?)",
            (nome, channel_id),
        )
        conn.commit()
        return {"id": cur.lastrowid, "nome": nome, "channel_id": channel_id}
    finally:
        conn.close()


def remover_canal_prioridade(canal_id: int) -> bool:
    conn = database.conectar()
    try:
        cur = conn.execute("DELETE FROM canal_prioridade WHERE id=?", (canal_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _canal_eh_priorizado(canal: str, channel_id: str | None, lista: list) -> bool:
    """True se o canal corresponde a algum canal prioritário (id exato ou nome)."""
    if not lista:
        return False
    if channel_id:
        for c in lista:
            if c.get("channel_id") and c["channel_id"] == channel_id:
                return True
    canal_low = (canal or "").lower()
    for c in lista:
        nome = (c.get("nome") or "").lower()
        if nome and nome in canal_low:
            return True
    return False


def _calcular_pontos(
    titulo: str, canal: str, instrumental: bool, vivo: bool, priorizado: bool
) -> int:
    titulo_low = (titulo or "").lower()
    canal_low = (canal or "").lower()
    p = 0
    for w in _PALAVRAS_BONUS:
        if w in titulo_low:
            p += 3
        if w in canal_low:
            p += 1
    for w in _PALAVRAS_CASTIGO:
        if w in titulo_low:
            p -= 4
        if w in canal_low:
            p -= 1
    if not vivo and ("ao vivo" in titulo_low or "live" in titulo_low):
        p -= 5
    if priorizado:
        p += _BONUS_CANAL_PRIORIZADO
    return p


def ranquear(itens: list, instrumental: bool, vivo: bool, prioridade: list | None = None) -> list:
    """
    Ordena por relevância para uso em culto e marca os resultados com tags.
    Cada item retornado: youtube_id, titulo, canal, channel_id, url, thumb,
    tags, prioridade.
    """
    lista = prioridade or listar_canais_prioridade()
    objetos = []
    for it in itens:
        vid = it["id"].get("videoId") or ""
        if not _VIDEO_ID.match(vid):
            continue
        sn = it.get("snippet", {})
        titulo = (sn.get("title") or "").strip()
        canal = (sn.get("channelTitle") or "").strip()
        channel_id = (sn.get("channelId") or "").strip() or None
        thumbs = sn.get("thumbnails", {})
        thumb = (
            thumbs.get("medium", {}).get("url")
            or thumbs.get("default", {}).get("url")
            or ""
        )
        titulo_low = titulo.lower()
        tags = []
        for marca in ["instrumental", "sem voz", "sem vocal", "karaoke", "karaokê", "playback"]:
            if marca in titulo_low and marca not in tags:
                tags.append(marca)
        priorizado = _canal_eh_priorizado(canal, channel_id, lista)
        objetos.append(
            {
                "youtube_id": vid,
                "titulo": titulo,
                "canal": canal,
                "channel_id": channel_id,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "thumb": thumb,
                "tags": tags,
                "prioridade": priorizado,
                "_pontos": _calcular_pontos(titulo, canal, instrumental, vivo, priorizado),
            }
        )

    objetos.sort(key=lambda o: o["_pontos"], reverse=True)
    for o in objetos:
        o.pop("_pontos", None)
    return objetos


def _reaplicar_prioridade(resultados: list, instrumental: bool, vivo: bool) -> None:
    """
    Ao servir do cache, recalcula o bônus de canal prioritário (a lista pode
    ter mudado) e reordena: a nova preferência aparece na hora, sem esperar os
    24h de validade do cache nem gastar quota da API.
    """
    lista = listar_canais_prioridade()
    for r in resultados:
        priorizado = _canal_eh_priorizado(
            r.get("canal"), r.get("channel_id"), lista
        )
        r["prioridade"] = priorizado
        r["_pontos"] = _calcular_pontos(
            r.get("titulo"), r.get("canal"), instrumental, vivo, priorizado
        )
    resultados.sort(key=lambda r: r["_pontos"], reverse=True)
    for r in resultados:
        r.pop("_pontos", None)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def _chave_cache(termo: str, playback: bool, instrumental: bool, vivo: bool) -> str:
    base = livros.normalizar(termo.strip())
    return f"{base}|p={1 if playback else 0}|i={1 if instrumental else 0}|v={1 if vivo else 0}"


def _ler_cache(chave: str) -> dict | None:
    conn = database.conectar()
    try:
        row = conn.execute(
            "SELECT dados, criado_em FROM youtube_cache WHERE consulta=?", (chave,)
        ).fetchone()
        if not row:
            return None
        # cache válido por 24h
        if time.time() - row["criado_em"] > 86400:
            return None
        try:
            return json.loads(row["dados"])
        except Exception:
            return None
    finally:
        conn.close()


def _gravar_cache(chave: str, payload: dict) -> None:
    conn = database.conectar()
    try:
        conn.execute(
            "INSERT INTO youtube_cache (consulta, dados, criado_em) VALUES (?,?,?)"
            " ON CONFLICT(consulta) DO UPDATE SET dados=excluded.dados, criado_em=excluded.criado_em",
            (chave, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pesquisa principal
# ---------------------------------------------------------------------------
def _marcar_favoritos(resultados: list) -> None:
    """Marca em cada resultado se o vídeo está salvo como favorito."""
    favoritos = set(_ids_favoritos())
    for r in resultados:
        r["favorito"] = r["youtube_id"] in favoritos


def pesquisar(
    termo: str,
    playback: bool = True,
    instrumental: bool = True,
    vivo: bool = False,
    forcar: bool = False,
) -> dict:
    """Pesquisa no YouTube (ou devolve do cache). Resultado serializável."""
    termo = (termo or "").strip()
    if not termo:
        return {"resultados": [], "fonte": "vazio", "erro": None}

    chave = _chave_cache(termo, playback, instrumental, vivo)
    if not forcar:
        cached = _ler_cache(chave)
        if cached:
            _marcar_favoritos(cached.get("resultados", []))
            _reaplicar_prioridade(cached.get("resultados", []), instrumental, vivo)
            cached["fonte"] = "cache"
            cached["erro"] = None
            return cached

    query = _montar_query(termo, playback, instrumental, vivo)
    itens = _chamar_api(query)
    resultados = ranquear(itens, instrumental, vivo)
    _marcar_favoritos(resultados)

    payload = {
        "consulta": termo,
        "query_api": query,
        "pesquisado_em": time.strftime("%H:%M"),
        "resultados": resultados,
    }
    _gravar_cache(chave, payload)

    payload["fonte"] = "api"
    payload["erro"] = None
    return payload


# ---------------------------------------------------------------------------
# Favoritos (tabela 'playback')
# ---------------------------------------------------------------------------
def _ids_favoritos() -> list:
    conn = database.conectar()
    try:
        return [
            r["youtube_id"]
            for r in conn.execute("SELECT youtube_id FROM playback").fetchall()
            if r["youtube_id"]
        ]
    finally:
        conn.close()


def favoritar(youtube_id: str, titulo: str, url: str | None = None) -> dict:
    """Salva (ou re-salva) o vídeo como favorito. Devolve a linha."""
    if not youtube_id:
        raise ValueError("youtube_id obrigatório.")
    url = url or f"https://www.youtube.com/watch?v={youtube_id}"
    conn = database.conectar()
    try:
        conn.execute(
            "INSERT INTO playback (titulo, youtube_id, url, favorito) VALUES (?,?,?,1)"
            " ON CONFLICT(youtube_id) DO UPDATE SET titulo=excluded.titulo, url=excluded.url, favorito=1",
            (titulo.strip(), youtube_id, url),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, titulo, youtube_id, url, favorito FROM playback WHERE youtube_id=?",
            (youtube_id,),
        ).fetchone()
        return {
            "id": row["id"],
            "titulo": row["titulo"],
            "youtube_id": row["youtube_id"],
            "url": row["url"],
            "favorito": row["favorito"],
        }
    finally:
        conn.close()


_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?[^#\s]*v=|embed/|shorts/|v/)"
    r"|youtu\.be/)([A-Za-z0-9_-]{6,})"
)


def _extrair_youtube_id(url: str) -> str | None:
    """Extrai o id do vídeo de diversos formatos de link do YouTube, ou None."""
    if not url:
        return None
    m = _YOUTUBE_ID_RE.search(url.strip())
    if not m:
        return None
    vid = m.group(1)
    return vid if _VIDEO_ID.match(vid) else None


def salvar_por_url(url: str, titulo: str = "") -> dict:
    """
    Salva um playback a partir de um link colado.
      - link do YouTube  -> extrai o id e reusa o fluxo normal (player local).
      - outro link       -> guarda a URL e deduplica pela própria URL.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Informe o link.")
    yid = _extrair_youtube_id(url)
    if yid:
        return favoritar(yid, titulo or "Playback (link)", url)
    # Link não-YouTube: dedup próprio pela URL (o campo youtube_id é único e nulo por vez).
    titulo = (titulo or "Playback").strip()
    conn = database.conectar()
    try:
        linha = conn.execute(
            "SELECT id FROM playback WHERE url=? COLLATE NOCASE", (url,)
        ).fetchone()
        if linha:
            conn.execute(
                "UPDATE playback SET titulo=?, favorito=1 WHERE id=?",
                (titulo, linha["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO playback (titulo, youtube_id, url, favorito) "
                "VALUES (?, NULL, ?, 1)",
                (titulo, url),
            )
        conn.commit()
        row = conn.execute(
            "SELECT id, titulo, youtube_id, url, favorito FROM playback "
            "WHERE url=? COLLATE NOCASE",
            (url,),
        ).fetchone()
        return {
            "id": row["id"],
            "titulo": row["titulo"],
            "youtube_id": row["youtube_id"],
            "url": row["url"],
            "favorito": row["favorito"],
        }
    finally:
        conn.close()


def desfavoritar(youtube_id: str) -> bool:
    conn = database.conectar()
    try:
        cur = conn.execute("DELETE FROM playback WHERE youtube_id=?", (youtube_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remover_por_id(playback_id: int) -> bool:
    """Remove um playback pelo id (funciona também p/ links não-YouTube)."""
    conn = database.conectar()
    try:
        cur = conn.execute("DELETE FROM playback WHERE id=?", (playback_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def listar_favoritos() -> list:
    conn = database.conectar()
    try:
        rows = conn.execute(
            "SELECT id, titulo, youtube_id, url, favorito FROM playback "
            "ORDER BY LOWER(titulo), id"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "titulo": r["titulo"],
                "youtube_id": r["youtube_id"],
                "url": r["url"],
                "favorito": r["favorito"],
            }
            for r in rows
        ]
    finally:
        conn.close()