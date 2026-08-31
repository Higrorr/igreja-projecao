"""
pegar_biblia.py
===============

Baixa os arquivos JSON das traduções da Bíblia em dominío público usadas no
projeto, a partir da release do repositório GitHub "damarals/biblias":

    https://github.com/damarals/biblias

As traduções baixadas são:
  - ALM1911 (Almeida 1911) - domínio público
  - TB      (Tradução Brasileira) - domínio público

O arquivo gerado é uma lista de 66 livros no formato:
    [ {"abbrev": "Gn", "chapters": [["vers.1", "vers.2", ...], ...]}, ... ]

Uso:
    python pegar_biblia.py            # baixa as duas traduções padrão
    python pegar_biblia.py --sigla TB # baixa apenas a Tradução Brasileira

Os arquivos são salvos em dados/ (que não vai para o controle de versão).
"""

import os
import sys
import argparse
import urllib.request
import urllib.error

# As duas traduções que queremos, com os nomes de arquivo na release.
# A chave é a sigla; o valor é o nome do arquivo na release do repositório.
TRADUCOES = {
    "ALM1911": "ALM1911.json",
    "TB": "TB.json",
}

URL_BASE = "https://github.com/damarals/biblias/releases/latest/download"


def baixar(sigla: str, destino_dir: str) -> str:
    """Baixa o JSON da sigla informada e devolve o caminho do arquivo salvo."""
    nome_arquivo = TRADUCOES[sigla]
    url = f"{URL_BASE}/{nome_arquivo}"
    destino = os.path.join(destino_dir, nome_arquivo)

    print(f"[{sigla}] Baixando {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            dados = resp.read()
    except urllib.error.HTTPError as e:
        print(f"[{sigla}] ERRO HTTP {e.code} ao baixar {url}")
        raise
    except urllib.error.URLError as e:
        print(f"[{sigla}] ERRO de conexão: {e.reason}")
        raise

    os.makedirs(destino_dir, exist_ok=True)
    with open(destino, "wb") as f:
        f.write(dados)

    # Validação rápida: o arquivo precisa ser JSON e ter 66 livros.
    import json
    with open(destino, encoding="utf-8") as f:
        livros = json.load(f)
    if not isinstance(livros, list) or len(livros) != 66:
        print(f"[{sigla}] ATENÇÃO: o arquivo não contém 66 livros "
              f"(encontrados {len(livros) if isinstance(livros, list) else 'n/a'}).")

    total_caps = sum(len(b["chapters"]) for b in livros)
    print(f"[{sigla}] OK -> {destino} ({len(livros)} livros, "
          f"{total_caps} capítulos, {os.path.getsize(destino)/1024:.0f} KB)")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa os JSON da Bíblia (domínio público).")
    parser.add_argument(
        "--sigla",
        nargs="+",
        choices=list(TRADUCOES),
        default=list(TRADUCOES),
        help="Siglas a baixar (padrão: todas).",
    )
    parser.add_argument(
        "--destino",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados"),
        help="Pasta de destino (padrão: dados/ ao lado da pasta scripts/).",
    )
    args = parser.parse_args()

    for sigla in args.sigla:
        baixar(sigla, args.destino)

    print("\nPronto! Use o script preparar_biblia.py para gerar os PPTX.")


if __name__ == "__main__":
    sys.exit(main())
