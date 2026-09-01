"""
agenda.py
=========

Agenda de programação do culto: fichas com nome da pessoa e o item que ela
vai cantar/pregar. Tocar no nome projeta/abre o item referente.

Cada ficha tem um texto livre (ex.: "Hino 133", "Salmos 23", "A Ele a Glória").
Ao projetar, o texto é resolvido:
  1. Se a ficha tem vínculo (tipo + ref_id), projeta o item exato.
  2. Senão, tenta casar o texto no acervo (bíblia/harpa/playback).
  3. Se nada casar, projeta o próprio texto na tela (aviso/palavra).
"""

from backend.database import database
from backend.services import busca, projetor


def _linha(r) -> dict:
    return {
        "id": r["id"],
        "nome": r["nome"],
        "tipo": r["tipo"],
        "ref_id": r["ref_id"],
        "texto": r["texto"] or "",
        "ordem": r["ordem"],
        "editado_em": r["editado_em"],
    }


def rotulo_de(tipo: str, ref_id: int) -> str:
    """Rótulo amigável do item referenciado (para exibir na ficha)."""
    conn = database.conectar()
    try:
        if tipo == "harpa":
            r = conn.execute("SELECT numero, titulo FROM harpa WHERE id=?", (ref_id,)).fetchone()
            if r:
                t = r["titulo"] or ""
                return f"Harpa {r['numero']}" + (f" · {t}" if t else "")
        elif tipo == "biblia":
            r = conn.execute("SELECT livro, capitulo FROM biblia WHERE id=?", (ref_id,)).fetchone()
            if r:
                return f"{r['livro']} {r['capitulo']}"
        elif tipo == "playback":
            r = conn.execute("SELECT titulo FROM playback WHERE id=?", (ref_id,)).fetchone()
            if r:
                return r["titulo"]
            # playback removido: cai no fallback "texto"
    finally:
        conn.close()
    return ""


def listar() -> list:
    conn = database.conectar()
    try:
        rows = conn.execute(
            "SELECT * FROM agenda ORDER BY ordem, id"
        ).fetchall()
        return [_linha(r) for r in rows]
    finally:
        conn.close()


def criar(nome: str, texto: str = "", tipo: str | None = None, ref_id: int | None = None) -> dict:
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Falta o nome da pessoa.")
    texto = (texto or "").strip()
    # Se há vínculo mas sem rótulo, gera o rótulo do próprio item.
    if not texto and tipo and ref_id is not None:
        texto = rotulo_de(tipo, int(ref_id))
    ordem = None
    conn = database.conectar()
    try:
        row = conn.execute("SELECT MAX(ordem) m FROM agenda").fetchone()
        ordem = (row["m"] if row["m"] is not None else -1) + 1
        cur = conn.execute(
            "INSERT INTO agenda (nome, tipo, ref_id, texto, ordem) VALUES (?,?,?,?,?)",
            (nome, tipo, ref_id if ref_id is not None else None, texto, ordem),
        )
        conn.commit()
        linha = conn.execute("SELECT * FROM agenda WHERE id=?", (cur.lastrowid,)).fetchone()
        return _linha(linha)
    finally:
        conn.close()


_NAO_INFORMADO = object()


def atualizar(ficha_id: int, nome=_NAO_INFORMADO, texto=_NAO_INFORMADO,
              tipo=_NAO_INFORMADO, ref_id=_NAO_INFORMADO) -> dict:
    conn = database.conectar()
    try:
        linha = conn.execute("SELECT * FROM agenda WHERE id=?", (ficha_id,)).fetchone()
        if linha is None:
            raise KeyError("Ficha não encontrada.")
        novo_nome = nome.strip() if nome is not _NAO_INFORMADO else linha["nome"]
        novo_tipo = tipo if tipo is not _NAO_INFORMADO else linha["tipo"]
        novo_ref = ref_id if ref_id is not _NAO_INFORMADO else linha["ref_id"]
        novo_texto = (
            (texto.strip() if texto is not _NAO_INFORMADO else (linha["texto"] or ""))
        ).strip()
        # Rotulo automático quando há vínculo e nenhum texto informado.
        if not novo_texto and novo_tipo and novo_ref is not None:
            novo_texto = rotulo_de(novo_tipo, int(novo_ref))
        conn.execute(
            "UPDATE agenda SET nome=?, tipo=?, ref_id=?, texto=? WHERE id=?",
            (novo_nome, novo_tipo, novo_ref, novo_texto, ficha_id),
        )
        conn.commit()
        linha = conn.execute("SELECT * FROM agenda WHERE id=?", (ficha_id,)).fetchone()
        return _linha(linha)
    finally:
        conn.close()


def remover(ficha_id: int) -> bool:
    conn = database.conectar()
    try:
        cur = conn.execute("DELETE FROM agenda WHERE id=?", (ficha_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def reordenar(ids: list) -> None:
    """Define a ordem das fichas na sequência dada pelo celular."""
    conn = database.conectar()
    try:
        for ordem, ficha_id in enumerate(ids):
            conn.execute("UPDATE agenda SET ordem=? WHERE id=?", (ordem, ficha_id))
        conn.commit()
    finally:
        conn.close()


def _projetar_item(tipo: str, ref_id: int, host_port: str | None) -> dict:
    if tipo == "playback":
        return projetor.projetar("playback", ref_id, host_port)
    if tipo in ("biblia", "harpa"):
        return projetor.projetar(tipo, ref_id, host_port)
    raise KeyError("Tipo inválido.")


def projetar(ficha_id: int, host_port: str | None = None) -> dict:
    """Projeta a ficha (resolvendo o item). Busca um fallback quando o texto
    não casa com nada do acervo."""
    conn = database.conectar()
    try:
        linha = conn.execute(
            "SELECT * FROM agenda WHERE id=?", (ficha_id,)
        ).fetchone()
    finally:
        conn.close()
    if linha is None:
        raise KeyError("Ficha não encontrada.")

    tipo, ref_id, texto = linha["tipo"], linha["ref_id"], (linha["texto"] or "").strip()

    # 1) Vínculo explícito.
    if tipo and ref_id is not None:
        try:
            return _projetar_item(tipo, ref_id, host_port)
        except projetor.ErroProjecao:
            raise

    # 2) Tenta casar o texto no acervo.
    if texto:
        cand = _resolver_texto(texto)
        if cand:
            try:
                return _projetar_item(cand["tipo"], cand["id"], host_port)
            except projetor.ErroProjecao:
                raise

    # 3) Fallback: mostra o próprio texto (aviso / palavra / sem item).
    if texto:
        return projetor.abrir_mensagem(texto, host_port)

    raise projetor.ErroProjecao("Esta ficha não tem item nem texto.")


def _resolver_texto(texto: str) -> dict | None:
    """Melhor correspondência de `texto` no acervo (bíblia/harpa/playback)."""
    res = busca.buscar(texto, limite=4)
    for grupo in ("biblia", "harpa", "playback"):
        itens = res.get(grupo) or []
        if itens:
            return {"tipo": grupo, "id": itens[0]["id"], "titulo": itens[0].get("titulo")}
    return None
