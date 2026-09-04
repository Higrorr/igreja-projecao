"""
projetor.py
===========

Abre o arquivo selecionado no PowerPoint (via COM) e inicia a projeção
em tela cheia, ou abre um playback do YouTube no navegador.

O PowerPoint roda na máquina local para o projetor; a requisição chega
do celular pela rede, mas a execução acontece aqui no PC.
"""

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from html import escape as html_escape

from backend.database import database

log = logging.getLogger(__name__)

# HRESULTs de COM quando o servidor (PowerPoint) está ocupado/rejeita a chamada.
_RPC_E_SERVERCALL_REJECTED = -2147418111  # 0x80010005
_RPC_E_SERVERCALL_RETRYLATER = -2147418106  # 0x8001010A


class ErroProjecao(Exception):
    """Exceção com mensagem amigável para o usuário."""


def _registrar_historico(conn, tipo, referencia):
    conn.execute(
        "INSERT INTO historico (tipo, referencia) VALUES (?,?)", (tipo, referencia)
    )


def _retry(fn, tentativas: int = 25):
    """
    Executa fn() repetindo quando o PowerPoint está ocupado (ex.: alternando
    de um slideshow para outro), até ~5 segundos.

    pythoncom é importado aqui (não no topo) para que o app inicie mesmo que
    o pywin32 não esteja disponível.
    """
    import pythoncom

    for _ in range(tentativas):
        try:
            return fn()
        except pythoncom.com_error as e:
            if e.hresult not in (
                _RPC_E_SERVERCALL_REJECTED,
                _RPC_E_SERVERCALL_RETRYLATER,
            ):
                raise
            time.sleep(0.2)
    raise ErroProjecao("O PowerPoint não respondeu a tempo (ocupado).")


def _encerrar_tela(aplicacao) -> None:
    """
    Encerra qualquer slideshow em execução e fecha as apresentações abertas.
    Necessário porque o PowerPoint só abre uma nova apresentação quando não
    está no meio de uma projeção (bug: depois da 1ª, nada mais abria).
    """
    n = aplicacao.Presentations.Count
    for i in range(1, n + 1):
        try:
            pres = aplicacao.Presentations.Item(i)
            vw = pres.SlideShowWindow.View  # falha se não houver slideshow
            vw.Exit()
        except Exception:
            pass
    for i in range(aplicacao.Presentations.Count, 0, -1):
        try:
            aplicacao.Presentations.Item(i).Close()
        except Exception:
            pass


def _encerrar_projecao_powerpoint() -> None:
    """
    Encerra o slideshow do PowerPoint se ele estiver rodando e sai do
    PowerPoint (usado quando o playback é aberto: só uma projeção por vez).
    Não inicia o PowerPoint se ele não estiver aberto; falhas nunca quebram
    o playback.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return
    pythoncom.CoInitialize()
    try:
        try:
            aplicacao = win32com.client.GetActiveObject("PowerPoint.Application")
        except Exception:
            return  # PowerPoint não está rodando
        _encerrar_tela(aplicacao)
        try:
            aplicacao.Quit()
        except Exception:
            pass
    except Exception:
        log.exception("Falha ao encerrar a projeção do PowerPoint")
    finally:
        pythoncom.CoUninitialize()


def _abrir_ppt(caminho: str) -> None:
    if not caminho or not os.path.isfile(caminho):
        raise ErroProjecao("Arquivo não encontrado no disco.")

    # Exclusão mútua: abrir um slide fecha qualquer playback aberto.
    _fechar_player_anterior()

    try:
        import pythoncom
        import win32com.client  # import tardio (pywin32 só existe no Windows)
    except ImportError:
        raise ErroProjecao("pywin32 não instalado neste PC.")

    # O servidor Flask é multithread (1 requisição = 1 thread nova). O pywin32
    # inicializa o COM apenas na thread que importa o win32com.client pela 1ª
    # vez; sem isso, as demais requisições falham com "CoInitialize não foi
    # chamado" (bug: só a 1ª projeção funcionava). CoInitialize() é reentrante.
    pythoncom.CoInitialize()
    try:
        aplicacao = _retry(lambda: win32com.client.Dispatch("PowerPoint.Application"))
        aplicacao.Visible = True
    except ErroProjecao:
        raise
    except Exception:
        log.exception("Falha ao acessar o PowerPoint (Dispatch/Visible)")
        raise ErroProjecao(
            "Não foi possível abrir o PowerPoint. Ele está instalado neste PC?"
        )

    try:
        _encerrar_tela(aplicacao)
        apresentacao = _retry(
            lambda: aplicacao.Presentations.Open(
                caminho, ReadOnly=True, Untitled=False, WithWindow=True
            )
        )
        _retry(lambda: apresentacao.SlideShowSettings.Run())
        # O Windows pode abrir a projeção minimizada/atrás quando o PowerPoint é
        # acionado por um processo em segundo plano. Garante tela cheia
        # (ppSlideShowFullScreen = 1) e traz a janela do slideshow para o
        # primeiro plano (SW_RESTORE + SetForegroundWindow + Alt). Nunca quebra
        # a projeção: falhas aqui apenas viram warning.
        try:
            janela_slides = apresentacao.SlideShowWindow
            janela_slides.WindowState = 1  # ppSlideShowFullScreen
            try:
                janela_slides.Activate()
            except Exception:
                pass
            try:
                from ctypes import windll
                _ativar_hwnd_primeiro_plano(
                    windll.user32, janela_slides.HWND, fullscreen=False
                )
            except Exception:
                pass
        except Exception:
            log.warning("Não consegui garantir o primeiro plano do slideshow")
    except ErroProjecao:
        raise
    except Exception as e:
        log.exception("Falha ao abrir/projetar o arquivo")
        raise ErroProjecao(f"Falha ao projetar: {e}")
    finally:
        pythoncom.CoUninitialize()
    _registrar_tipo("slide")


# ---------------------------------------------------------------------------
# Player de tela cheia (playbacks do YouTube)
#
# Em vez de abrir na aba padrão do navegador, o vídeo é aberto numa janela do
# Edge/Chrome em tela cheia suave (sai com F11/Esc) apontando para a página
# local /player/<id> (embed limpo, sem a UI do YouTube).
#
# Flags usadas:
#   --start-fullscreen            : tela cheia normal (não trava como kiosk)
#   --autoplay-policy=no-user-gesture-required : toca com som sem precisar de
#                                 clique (o gesto foi feito no celular)
#   --user-data-dir=<tmp única>   : perfil isolado -> não bagunçam os favoritos
#                                 do Edge normal e a janela pode ser encerrada
#                                 de forma determinística quando trocar de vídeo
# ---------------------------------------------------------------------------
_CAMINHOS_NAVEGADOR = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# A janela atualmente aberta (somente uma por vez) + o perfil temporário dela.
_player = {"proc": None, "dir": None}

# Controle remoto da projeção.
#   _controle["tipo"]: "slide" | "player" | "preto" | None  (o que está na tela)
#   _controle["view"]: referência COM do SlideShowWindow.View (p/ avançar/voltar)
#   _controle["comando"]: comando pendente p/ o player consumir via polling
_controle = {"tipo": None, "view": None, "comando": None}

# Chaves de comando aceitas pelo player (play/pause).
_COMANDOS_PLAYER = ("play_pause", "recomecar")


def _registrar_tipo(tipo: str | None) -> None:
    _controle["tipo"] = tipo
    if tipo != "slide":
        # Ao sair de slide, descarta a referência COM do slideshow.
        _controle["view"] = None


def _qual_navegador() -> str | None:
    for caminho in _CAMINHOS_NAVEGADOR:
        if os.path.isfile(caminho):
            return caminho
    for nome in ("chrome", "msedge"):
        onde = shutil.which(nome)
        if onde:
            return onde
    return None


def _fechar_player_anterior() -> None:
    proc = _player.get("proc")
    pasta = _player.get("dir")
    if proc is not None and proc.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    if pasta:
        shutil.rmtree(pasta, ignore_errors=True)
    _player["proc"] = None
    _player["dir"] = None


def _porta_de(host_port: str | None) -> str:
    """Extrai a porta de 'host:porta' (da requisição). Padrão: 5000."""
    if host_port and ":" in host_port:
        return host_port.rsplit(":", 1)[1]
    return "5000"


def _primeira_janela_visivel(pid: int):
    """HWND da 1ª janela visível do processo, ou None."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    achadas: list = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        pid_janela = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_janela))
        if pid_janela.value == pid and user32.IsWindowVisible(hwnd):
            achadas.append(hwnd)
            return False
        return True

    user32.EnumWindows(_cb, 0)
    return achadas[0] if achadas else None


def _janela_em_tela_cheia(user32, hwnd) -> bool:
    import ctypes
    from ctypes import wintypes

    SM_CXSCREEN, SM_CYSCREEN = 0, 1
    largura = user32.GetSystemMetrics(SM_CXSCREEN)
    altura = user32.GetSystemMetrics(SM_CYSCREEN)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    # Tolerância de 2px: aceita a janela maximizada (que perde a barra de
    # título, ~1px) como "cobrindo a tela" — evita F11 desnecessário.
    return (r.right - r.left) >= largura - 2 and (r.bottom - r.top) >= altura - 2


def _forcar_topo(user32, hwnd) -> None:
    """
    Coloca a janela realmente por cima das outras, contornando a restrição do
    Windows que bloqueia o SetForegroundWindow vindo de processo em segundo
    plano. HWND_TOPMOST sobe a janela no topo da ordem Z; em seguida
    NOTOPMOST a devolve ao estado normal (topo sem ficar flutuando para sempre).
    """
    import time

    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    flags = SWP_NOSIZE | SWP_NOMOVE
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)  # HWND_TOPMOST
    time.sleep(0.05)
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)  # HWND_NOTOPMOST


def _ativar_hwnd_primeiro_plano(user32, hwnd, fullscreen: bool = True) -> bool:
    """
    Desminimiza (se minimizado), traz a janela para o primeiro plano e,
    opcionalmente, garante a tela cheia (aperta F11 se não estiver). Usado
    tanto para o navegador (playback) quanto para o PowerPoint (slides).
    """
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if not user32.SetForegroundWindow(hwnd):
        # O Windows restringe a mudança de foreground vinda de background; um
        # toque inofensivo na tecla Alt libera a permissão.
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU pressiona e solta
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
    _forcar_topo(user32, hwnd)
    time.sleep(0.3)
    if fullscreen and not _janela_em_tela_cheia(user32, hwnd):
        user32.keybd_event(0x7A, 0, 0, 0)  # VK_F11 (tela cheia no Chrome)
        time.sleep(0.05)
        user32.keybd_event(0x7A, 0, 2, 0)
    return True


def _traz_janela_pra_frente(pid: int, timeout_s: float = 8.0) -> bool:
    """
    Windows abre minimizada/atrás as janelas criadas por processos em segundo
    plano (caso do igreja.exe disparando o Chrome). Esta função desminimiza
    (apenas se realmente minimizada), traz a janela para frente e, se ela não
    estiver em tela cheia, aperta F11 para ativá-la. Não toca em janelas que
    já estão em fullscreen (evita desfazer a tela cheia com o toggle do F11).
    """
    import time
    from ctypes import windll

    user32 = windll.user32
    fim = time.time() + timeout_s
    hwnd = None
    while time.time() < fim:
        hwnd = _primeira_janela_visivel(pid)
        if hwnd is not None:
            break
        time.sleep(0.15)
    if hwnd is None:
        return False
    return _ativar_hwnd_primeiro_plano(user32, hwnd, fullscreen=True)


def _abrir_player(player_url: str) -> bool:
    """Abre player_url em tela cheia (Edge/Chrome). Devolve True se abriu."""
    # Exclusão mútua: abrir um playback fecha qualquer slide em projeção.
    _encerrar_projecao_powerpoint()
    navegador = _qual_navegador()
    if not navegador:
        webbrowser.open(player_url)
        return False
    _fechar_player_anterior()
    pasta = tempfile.mkdtemp(prefix="igreja_player_")
    # --app: janela limpa, sem abas/barras (ideal para projeção); sai com Alt+F4.
    # --start-fullscreen: tela cheia; caso não seja aplicado, o _traz_janela_pra_frente
    # completa com um F11 (sem depender de gesto do usuário).
    cmd = [
        navegador,
        "--app=" + player_url,
        "--start-fullscreen",
        "--no-first-run",
        "--no-default-browser-check",
        "--autoplay-policy=no-user-gesture-required",
        "--user-data-dir=" + pasta,
    ]
    try:
        _player["proc"] = subprocess.Popen(cmd)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        _player["proc"] = None
        _player["dir"] = None
        webbrowser.open(player_url)
        return False
    _player["dir"] = pasta
    _traz_janela_pra_frente(_player["proc"].pid)
    # A janela do navegador pode demorar a aparecer; um segundo realce, logo
    # após o início, garante que o playback fique em primeiro plano/tela cheia
    # de forma confiável. Roda em thread daemon para não travar a requisição.
    def _reforcar(pid):
        try:
            import time
            time.sleep(1.2)
            _traz_janela_pra_frente(pid, timeout_s=4.0)
        except Exception:
            pass

    threading.Thread(target=_reforcar, args=(_player["proc"].pid,), daemon=True).start()
    # Reset do comando pendente ao abrir um novo player.
    _controle["comando"] = None
    return True


def abrir_mensagem(texto: str, host_port: str | None = None) -> dict:
    """
    Projeta um texto livre em tela cheia (útil p/ avisos, pregações, etc.).
    Usa uma página local simples (reprojetada e encerrada com Alt+F4).
    """
    texto = (texto or "").strip()
    if not texto:
        raise ErroProjecao("Texto vazio.")
    pagina = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{height:100vh;margin:0;display:flex;align-items:center;"
        "justify-content:center;background:#000;color:#fff;font-family:sans-serif;"
        "text-align:center;padding:4vw;}p{font-size:clamp(2rem,7vw,6rem);"
        "line-height:1.3;margin:0;}</style></head><body><p>"
        + html_escape(texto) + "</p></body></html>"
    )
    import base64
    pasta = tempfile.mkdtemp(prefix="igreja_msg_")
    caminho = os.path.join(pasta, "msg.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(pagina)
    url = "file:///" + caminho.replace("\\", "/")
    tela_cheia = _abrir_player(url)
    _registrar_tipo("player")
    # O _abrir_player cria o próprio profile; o limpeza dos arquivos da msg
    # fica a cargo do _fechar_player_anterior (que remove a pasta do player).
    return {"ok": True, "url": url, "modo": "tela cheia" if tela_cheia else "navegador"}


def tela_preta(host_port: str | None = None) -> dict:
    """
    Projeta/alterna uma tela totalmente preta (para quando não há nada na
    projeção). Fecha playbacks/slides ativos (exclusão mútua).
    """
    # Se já está preto, fecha (tela escura volta a refletir o próximo item).
    if _controle.get("tipo") == "preto":
        _fechar_player_anterior()
        _registrar_tipo(None)
        return {"ok": True, "preto": False}

    pagina = (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "html,body{height:100vh;margin:0;background:#000;}"
        "</style></head><body></body></html>"
    )
    pasta = tempfile.mkdtemp(prefix="igreja_preto_")
    caminho = os.path.join(pasta, "preto.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(pagina)
    url = "file:///" + caminho.replace("\\", "/")
    tela_cheia = _abrir_player(url)
    _registrar_tipo("preto")
    return {"ok": True, "preto": True, "modo": "tela cheia" if tela_cheia else "navegador"}


def pegar_comando_player() -> dict:
    """Devolve o comando pendente para o player consumir (polling)."""
    cmd = _controle.get("comando")
    _controle["comando"] = None  # consome
    if cmd in _COMANDOS_PLAYER:
        return {"comando": cmd}
    return {"comando": None}


def tipo_projecao() -> str | None:
    """Tipo do que está na tela: 'slide' | 'player' | 'preto' | None."""
    return _controle.get("tipo")


def acao_projecao(acao: str, host_port: str | None = None) -> dict:
    """
    Executa uma ação remota sobre a projeção atual.
      'slide_proximo' / 'slide_anterior' : avança/volta no slideshow (PPT)
      'play_pause'                        : alterna play/pause do playback
    """
    if acao in ("slide_proximo", "slide_anterior"):
        if _controle.get("tipo") != "slide":
            raise ErroProjecao("Nenhum slide em projeção.")
        _navegar_slide(1 if acao == "slide_proximo" else -1)
        return {"ok": True, "acao": acao}

    if acao == "play_pause":
        if _controle.get("tipo") not in ("player", "preto"):
            raise ErroProjecao("Nenhum playback em projeção.")
        _controle["comando"] = "play_pause"
        return {"ok": True, "acao": acao}

    if acao == "recomecar":
        if _controle.get("tipo") not in ("player", "preto"):
            raise ErroProjecao("Nenhum playback em projeção.")
        _controle["comando"] = "recomecar"
        return {"ok": True, "acao": acao}

    raise ErroProjecao(f"Ação desconhecida: {acao}")


def primeiro_plano() -> dict:
    """
    Traz a projeção atual (PowerPoint ou player) para o primeiro plano em tela
    cheia, sob demanda — usado quando o operador nota que a tela ficou atrás de
    outra janela no PC do projetor.
    """
    tipo = _controle.get("tipo")
    from ctypes import windll
    user32 = windll.user32

    if tipo in ("player", "preto"):
        proc = _player.get("proc")
        if proc is None or proc.poll() is not None:
            raise ErroProjecao("Nenhum playback em projeção.")
        _traz_janela_pra_frente(proc.pid)
        return {"ok": True, "tipo": tipo}

    if tipo == "slide":
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            raise ErroProjecao("pywin32 não instalado neste PC.")
        pythoncom.CoInitialize()
        try:
            aplicacao = win32com.client.GetActiveObject("PowerPoint.Application")
            pres = None
            for i in range(1, aplicacao.Presentations.Count + 1):
                p = aplicacao.Presentations.Item(i)
                try:
                    if p.SlideShowWindow is not None:
                        pres = p
                        break
                except Exception:
                    continue
            if pres is None or pres.SlideShowWindow is None:
                raise ErroProjecao("Slideshow não está em execução.")
            janela = _retry(lambda: pres.SlideShowWindow)
            hwnd = _retry(lambda: janela.HWND)
        except ErroProjecao:
            raise
        except Exception:
            log.exception("Falha ao trazer o PowerPoint para o primeiro plano")
            raise ErroProjecao("Falha ao trazer o PowerPoint para frente.")
        finally:
            pythoncom.CoUninitialize()
        try:
            _ativar_hwnd_primeiro_plano(user32, hwnd, fullscreen=False)
        except Exception:
            log.warning("Não consegui ativar a janela do slideshow")
        return {"ok": True, "tipo": tipo}

    raise ErroProjecao("Nada em projeção para trazer para frente.")


def _navegar_slide(delta: int) -> None:
    """
    Avança (+) ou volta (-) no slideshow do PowerPoint. Re-adquire a referência
    COM na thread atual para evitar problemas após CoUninitialize.
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        raise ErroProjecao("pywin32 não instalado neste PC.")
    pythoncom.CoInitialize()
    try:
        aplicacao = win32com.client.GetActiveObject("PowerPoint.Application")
        pres = None
        for i in range(1, aplicacao.Presentations.Count + 1):
            p = aplicacao.Presentations.Item(i)
            try:
                if p.SlideShowWindow is not None:
                    pres = p
                    break
            except Exception:
                continue
        if pres is None or pres.SlideShowWindow is None:
            raise ErroProjecao("Slideshow não está em execução.")
        view = _retry(lambda: pres.SlideShowWindow.View)
        if delta > 0:
            _retry(lambda: view.Next())
        else:
            _retry(lambda: view.Previous())
    except ErroProjecao:
        raise
    except Exception:
        log.exception("Falha ao navegar nos slides")
        raise ErroProjecao("Falha ao navegar nos slides.")
    finally:
        pythoncom.CoUninitialize()


def abrir_youtube(youtube_id: str, host_port: str | None = None) -> dict:
    """Abre um vídeo do YouTube em tela cheia suave (fallback: navegador)."""
    if not re.match(r"^[A-Za-z0-9_-]{6,}$", youtube_id or ""):
        raise ErroProjecao("Id de vídeo inválido.")
    player_url = f"http://127.0.0.1:{_porta_de(host_port)}/player/{youtube_id}"
    tela_cheia = _abrir_player(player_url)
    _registrar_tipo("player")
    conn = database.conectar()
    try:
        _registrar_historico(conn, "playback", youtube_id)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "url": player_url, "modo": "tela cheia" if tela_cheia else "navegador"}


def projetar(tipo: str, item_id: int, host_port: str | None = None) -> dict:
    """Projeta o item. tipo: 'biblia' | 'harpa' | 'playback'."""
    conn = database.conectar()
    try:
        if tipo == "playback":
            row = conn.execute(
                "SELECT titulo, url, youtube_id FROM playback WHERE id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise ErroProjecao("Playback não encontrado.")
            if row["youtube_id"]:
                player_url = (
                    f"http://127.0.0.1:{_porta_de(host_port)}/player/"
                    + row["youtube_id"]
                )
                tela_cheia = _abrir_player(player_url)
            elif row["url"]:
                # Link não-YouTube: abre em tela cheia no navegador também.
                tela_cheia = _abrir_player(row["url"])
            else:
                tela_cheia = False
            if tela_cheia:
                _registrar_tipo("player")
            if row["url"] and not tela_cheia:
                webbrowser.open(row["url"])
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