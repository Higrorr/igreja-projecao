"""
scanner.py
==========

Percorre as pastas do acervo (Bíblia e Harpa), interpreta os nomes/caminhos
dos arquivos PPTX e atualiza o índice SQLite.

Fluxo:
    Ler pastas -> Interpretar nomes -> Comparar com o banco -> Atualizar

Regras:
  - detecta arquivos novos      (INSERT)
  - evita duplicações           (chave única por livro+capitulo / numero)
  - atualiza arquivos alterados (compara por data de modificação)
  - remove do índice arquivos que sumiram do disco

O algoritmo é O(n): varre o disco uma única vez, carrega o banco num dicionário
e só então faz INSERT/UPDATE/DELETE em lote.
"""

import os
import re
import sqlite3
import time

from backend import config
from backend.database import database


def _modificacao(caminho: str) -> float:
    """Data de modificação (epoch) de um arquivo; 0 se não existir."""
    try:
        return os.path.getmtime(caminho)
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Bíblia
# ---------------------------------------------------------------------------
def escanear_biblia(conn: sqlite3.Connection, pasta: str) -> dict:
    """
    Lê a pasta da Bíblia. Formato esperado:
        pasta/<Livro>/<Livro NN>.pptx     (ex: Genesis/Genesis 01.pptx)
    """
    t0 = time.time()
    if not os.path.isdir(pasta):
        return {"inseridos": 0, "atualizados": 0, "removidos": 0, "segundos": 0.0}

    banco = {
        (r["livro"], r["capitulo"]): r
        for r in conn.execute(
            "SELECT id, livro, capitulo, arquivo, caminho, modificacao FROM biblia"
        )
    }
    disco_caminhos = {}  # (livro, capitulo) -> caminho no disco
    a_inserir, a_atualizar = [], []
    total_arquivos = 0

    for livro in os.listdir(pasta):
        dir_livro = os.path.join(pasta, livro)
        if not os.path.isdir(dir_livro):
            continue
        for arquivo in os.listdir(dir_livro):
            if not arquivo.lower().endswith(".pptx"):
                continue
            # "Genesis 01.pptx" -> capitulo 1
            m = re.match(r"^.*?\s+(\d+)\.pptx$", arquivo, re.IGNORECASE)
            if not m:
                continue
            capitulo = int(m.group(1))
            caminho = os.path.join(dir_livro, arquivo)
            chave = (livro, capitulo)
            disco_caminhos[chave] = caminho
            total_arquivos += 1

            mod = _modificacao(caminho)
            existe = banco.get(chave)
            if existe is None:
                a_inserir.append((livro, capitulo, arquivo, caminho, mod))
            elif (
                existe["modificacao"] != mod
                or existe["caminho"] != caminho
                or existe["arquivo"] != arquivo
            ):
                a_atualizar.append((arquivo, caminho, mod, existe["id"]))

    if a_inserir:
        conn.executemany(
            "INSERT INTO biblia (livro, capitulo, arquivo, caminho, modificacao) "
            "VALUES (?,?,?,?,?)",
            a_inserir,
        )
    if a_atualizar:
        conn.executemany(
            "UPDATE biblia SET arquivo=?, caminho=?, modificacao=? WHERE id=?",
            a_atualizar,
        )

    # Remove do índice os arquivos que não existem mais no disco
    a_remover = [
        r["id"] for chave, r in banco.items() if chave not in disco_caminhos
    ]
    if a_remover:
        conn.executemany("DELETE FROM biblia WHERE id=?", [(i,) for i in a_remover])

    return {
        "inseridos": len(a_inserir),
        "atualizados": len(a_atualizar),
        "removidos": len(a_remover),
        "arquivos_no_disco": total_arquivos,
        "segundos": round(time.time() - t0, 2),
    }


# ---------------------------------------------------------------------------
# Harpa
# ---------------------------------------------------------------------------
def escanear_harpa(conn: sqlite3.Connection, pasta: str) -> dict:
    """
    Lê a pasta da Harpa. Formato esperado:
        pasta/<NNN - Nome>.pptx      (ex: 133 - NO ROL DO LIVRO.pptx)
    """
    t0 = time.time()
    if not os.path.isdir(pasta):
        return {"inseridos": 0, "atualizados": 0, "removidos": 0, "segundos": 0.0}

    banco = {
        r["numero"]: r
        for r in conn.execute(
            "SELECT id, numero, titulo, arquivo, caminho, modificacao FROM harpa"
        )
    }
    disco_caminhos = {}  # numero -> caminho no disco
    a_inserir, a_atualizar = [], []
    total_arquivos = 0

    for arquivo in os.listdir(pasta):
        if not arquivo.lower().endswith(".pptx"):
            continue
        caminho = os.path.join(pasta, arquivo)

        # "133 - NO ROL DO LIVRO.pptx" -> numero 133, titulo "NO ROL DO LIVRO"
        m = re.match(r"^\s*(\d+)\s*[-–]\s*(.*?)\.pptx$", arquivo, re.IGNORECASE)
        if not m:
            # aceita também o formato sem nome: "133.pptx"
            m2 = re.match(r"^\s*(\d+)\.pptx$", arquivo, re.IGNORECASE)
            if not m2:
                continue
            numero = int(m2.group(1))
            titulo = ""
        else:
            numero = int(m.group(1))
            titulo = m.group(2).strip()

        disco_caminhos[numero] = caminho
        total_arquivos += 1

        mod = _modificacao(caminho)
        existe = banco.get(numero)
        if existe is None:
            a_inserir.append((numero, titulo, arquivo, caminho, mod))
        elif (
            existe["modificacao"] != mod
            or existe["caminho"] != caminho
            or existe["arquivo"] != arquivo
            or existe["titulo"] != titulo
        ):
            a_atualizar.append((titulo, arquivo, caminho, mod, existe["id"]))

    if a_inserir:
        conn.executemany(
            "INSERT INTO harpa (numero, titulo, arquivo, caminho, modificacao) "
            "VALUES (?,?,?,?,?)",
            a_inserir,
        )
    if a_atualizar:
        conn.executemany(
            "UPDATE harpa SET titulo=?, arquivo=?, caminho=?, modificacao=? WHERE id=?",
            a_atualizar,
        )

    a_remover = [r["id"] for numero, r in banco.items() if numero not in disco_caminhos]
    if a_remover:
        conn.executemany("DELETE FROM harpa WHERE id=?", [(i,) for i in a_remover])

    return {
        "inseridos": len(a_inserir),
        "atualizados": len(a_atualizar),
        "removidos": len(a_remover),
        "arquivos_no_disco": total_arquivos,
        "segundos": round(time.time() - t0, 2),
    }


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def escanear_tudo() -> dict:
    """Executa o scanner completo e devolve um resumo."""
    t0 = time.time()
    database.criar_tabelas()
    conn = database.conectar()
    try:
        res_b = escanear_biblia(conn, config.BIBLIA_DIR)
        print(f"[scanner] bíblia: {res_b}", flush=True)
        res_h = escanear_harpa(conn, config.HARPA_DIR)
        print(f"[scanner] harpa : {res_h}", flush=True)
        conn.commit()
        totais = {
            "biblia": conn.execute("SELECT COUNT(*) c FROM biblia").fetchone()["c"],
            "harpa": conn.execute("SELECT COUNT(*) c FROM harpa").fetchone()["c"],
        }
        resumo = {
            "biblia": res_b,
            "harpa": res_h,
            "totais": totais,
            "segundos": round(time.time() - t0, 2),
        }
        print(f"[scanner] totais={totais} em {resumo['segundos']}s", flush=True)
        return resumo
    finally:
        conn.close()