"""
projetor.py
===========

Abre o arquivo selecionado no PowerPoint (via COM) e inicia a projeção
em tela cheia, ou abre um playback do YouTube no navegador.

O PowerPoint roda na máquina local para o projetor; a requisição chega
do celular pela rede, mas a execução acontece aqui no PC.
"""

import os
import webbrowser

from backend.database import database


class ErroProjecao(Exception):
    """Exceção com mensagem amigável para o usuário."""


def _registrar_historico(conn, tipo, referencia):
    conn.execute(
        "INSERT INTO historico (tipo, referencia) VALUES (?,?)", (tipo, referencia)
    )


def _abrir_ppt(caminho: str) -> None:
    if not caminho or not os.path.isfile(caminho):
        raise ErroProjecao("Arquivo não encontrado no disco.")

    try:
        import win32com.client  # import tardio (pywin32 só existe no Windows)
    except ImportError:
        raise ErroProjecao("pywin32 não instalado neste PC.")

    try:
        aplicacao = win32com.client.Dispatch("PowerPoint.Application")
        aplicacao.Visible = True
    except Exception:
        raise ErroProjecao(
            "Não foi possível abrir o PowerPoint. Ele está instalado neste PC?"
        )

    try:
        apresentacao = aplicacao.Presentations.Open(
            caminho, ReadOnly=True, Untitled=False, WithWindow=True
        )
        apresentacao.SlideShowSettings.Run()  # inicia a projeção em tela cheia
    except Exception as e:
        raise ErroProjecao(f"Falha ao projetar: {e}")


def projetar(tipo: str, item_id: int) -> dict:
    """Projeta o item. tipo: 'biblia' | 'harpa' | 'playback'."""
    conn = database.conectar()
    try:
        if tipo == "playback":
            row = conn.execute(
                "SELECT titulo, url, youtube_id FROM playback WHERE id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise ErroProjecao("Playback não encontrado.")
            url = row["url"] or (
                "https://www.youtube.com/watch?v=" + row["youtube_id"]
                if row["youtube_id"] else None
            )
            if not url:
                raise ErroProjecao("Playback sem endereço.")
            webbrowser.open(url)
            _registrar_historico(conn, "playback", row["titulo"])
            conn.commit()
            return {"ok": True, "titulo": row["titulo"]}

        if tipo in ("biblia", "harpa"):
            tabela = "biblia" if tipo == "biblia" else "harpa"
            if tipo == "biblia":
                row = conn.execute(
                    "SELECT livro, capitulo, caminho FROM biblia WHERE id=?", (item_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT numero, titulo, caminho FROM harpa WHERE id=?", (item_id,)
                ).fetchone()
            if row is None:
                raise ErroProjecao("Item não encontrado no índice.")

            _abrir_ppt(row["caminho"])
            if tipo == "biblia":
                referencia = f"{row['livro']} {row['capitulo']}"
            else:
                referencia = f"Harpa {row['numero']}"
            _registrar_historico(conn, tipo, referencia)
            conn.commit()
            return {"ok": True, "referencia": referencia}

        raise ErroProjecao("Tipo desconhecido.")
    finally:
        conn.close()