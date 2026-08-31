"""
livros.py
=========

Conhecimento sobre os livros da Bíblia: nomes das pastas (sem acento) e
nomes de exibição (com acento), além de helpers de normalização e busca.

As pastas do acervo usam o nome "sem" acento (ex: "Genesis", "Jo"=Jó,
"Joao"=João). Este mapa espelha o que o gerador usou.
"""

import unicodedata

# nome_sem_acento -> nome_para_exibicao
SEM_PARA_ACENTO = {
    "Genesis": "Gênesis",
    "Exodo": "Êxodo",
    "Levitico": "Levítico",
    "Numeros": "Números",
    "Deuteronomio": "Deuteronômio",
    "Josue": "Josué",
    "Juizes": "Juízes",
    "Rute": "Rute",
    "1 Samuel": "1 Samuel",
    "2 Samuel": "2 Samuel",
    "1 Reis": "1 Reis",
    "2 Reis": "2 Reis",
    "1 Cronicas": "1 Crônicas",
    "2 Cronicas": "2 Crônicas",
    "Esdras": "Esdras",
    "Neemias": "Neemias",
    "Ester": "Ester",
    "Jo": "Jó",
    "Salmos": "Salmos",
    "Proverbios": "Provérbios",
    "Eclesiastes": "Eclesiastes",
    "Cantares": "Cantares",
    "Isaias": "Isaías",
    "Jeremias": "Jeremias",
    "Lamentacoes": "Lamentações",
    "Ezequiel": "Ezequiel",
    "Daniel": "Daniel",
    "Oseias": "Oséias",
    "Joel": "Joel",
    "Amos": "Amós",
    "Obadias": "Obadias",
    "Jonas": "Jonas",
    "Miqueias": "Miquéias",
    "Naum": "Naum",
    "Habacuque": "Habacuque",
    "Sofonias": "Sofonias",
    "Ageu": "Ageu",
    "Zacarias": "Zacarias",
    "Malaquias": "Malaquias",
    "Mateus": "Mateus",
    "Marcos": "Marcos",
    "Lucas": "Lucas",
    "Joao": "João",
    "Atos": "Atos",
    "Romanos": "Romanos",
    "1 Corintios": "1 Coríntios",
    "2 Corintios": "2 Coríntios",
    "Galatas": "Gálatas",
    "Efesios": "Efésios",
    "Filipenses": "Filipenses",
    "Colossenses": "Colossenses",
    "1 Tessalonicenses": "1 Tessalonicenses",
    "2 Tessalonicenses": "2 Tessalonicenses",
    "1 Timoteo": "1 Timóteo",
    "2 Timoteo": "2 Timóteo",
    "Tito": "Tito",
    "Filemom": "Filemom",
    "Hebreus": "Hebreus",
    "Tiago": "Tiago",
    "1 Pedro": "1 Pedro",
    "2 Pedro": "2 Pedro",
    "1 Joao": "1 João",
    "2 Joao": "2 João",
    "3 Joao": "3 João",
    "Judas": "Judas",
    "Apocalipse": "Apocalipse",
}


def normalizar(texto: str) -> str:
    """Remove acentos, lowercase e normaliza espaços."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


# Abreviaturas usuais de livros -> nome da pasta (sem acento).
# Ajuda quando o usuário digita "sl", "gn", "jn"... (sem correspondência
# direta com o nome da pasta, que é o nome por extenso).
ABREV_LIVRO = {
    "gn": "Genesis",
    "ex": "Exodo",
    "lv": "Levitico",
    "nm": "Numeros",
    "dt": "Deuteronomio",
    "js": "Josue",
    "jz": "Juizes",
    "rt": "Rute",
    "1sm": "1 Samuel",
    "2sm": "2 Samuel",
    "1rs": "1 Reis",
    "2rs": "2 Reis",
    "1cr": "1 Cronicas",
    "2cr": "2 Cronicas",
    "ed": "Esdras",
    "ne": "Neemias",
    "et": "Ester",
    "jo": "Jo",
    "jó": "Jo",
    "sl": "Salmos",
    "pv": "Proverbios",
    "ec": "Eclesiastes",
    "ct": "Cantares",
    "is": "Isaias",
    "jr": "Jeremias",
    "lm": "Lamentacoes",
    "ez": "Ezequiel",
    "dn": "Daniel",
    "os": "Oseias",
    "jl": "Joel",
    "am": "Amos",
    "ob": "Obadias",
    "jn": "Jonas",
    "mq": "Miqueias",
    "na": "Naum",
    "hc": "Habacuque",
    "sf": "Sofonias",
    "ag": "Ageu",
    "zc": "Zacarias",
    "ml": "Malaquias",
    "mt": "Mateus",
    "mc": "Marcos",
    "lc": "Lucas",
    "at": "Atos",
    "rm": "Romanos",
    "1co": "1 Corintios",
    "2co": "2 Corintios",
    "gl": "Galatas",
    "ef": "Efesios",
    "fp": "Filipenses",
    "cl": "Colossenses",
    "1ts": "1 Tessalonicenses",
    "2ts": "2 Tessalonicenses",
    "1tm": "1 Timoteo",
    "2tm": "2 Timoteo",
    "tt": "Tito",
    "fm": "Filemom",
    "hb": "Hebreus",
    "tg": "Tiago",
    "1pe": "1 Pedro",
    "2pe": "2 Pedro",
    "1jo": "1 Joao",
    "2jo": "2 Joao",
    "3jo": "3 Joao",
    "jd": "Judas",
    "ap": "Apocalipse",
}


def procurar_livro(token: str) -> str | None:
    """
    Resolve um token digitado para um livro do acervo.

    Regras:
      1. nome exato                     ("2 reis" -> "2 Reis")
      2. prefixo que é a fronteira do nome ("jo" -> "Jo"; "sal" -> "Salmos" se único)
      3. prefixo com candidato único    ("gen" -> "Genesis")
      4. abreviatura                    ("sl" -> "Salmos")

    Tokens numéricos ambíguos ("2", "1") retornam None em vez de inventar um
    livro (ex.: "2" não vira "2 Samuel" por acidente).
    """
    tok = normalizar(token)
    if not tok:
        return None
    for sem in SEM_PARA_ACENTO:
        if normalizar(sem) == tok:
            return sem
    candidatos = [sem for sem in SEM_PARA_ACENTO if normalizar(sem).startswith(tok)]
    if candidatos:
        fronteira = [s for s in candidatos if len(normalizar(s)) == len(tok)]
        if fronteira:
            return fronteira[0]
        if len(candidatos) == 1:
            return candidatos[0]
        return None  # ambíguo; deixar a resolução por prefixo mais longo decidir
    return ABREV_LIVRO.get(tok)


def candidatos_livro(token: str) -> list[str]:
    """Livros cujo nome contém o token (busca mais aberta)."""
    tok = normalizar(token)
    if not tok:
        return []
    return [sem for sem in SEM_PARA_ACENTO if tok in normalizar(sem)]


def nome_exibicao(sem: str) -> str:
    """Nome com acento a partir do nome da pasta."""
    return SEM_PARA_ACENTO.get(sem, sem)