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
import time
import webbrowser

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
    except ErroProjecao:
        raise
    except Exception as e:
        log.exception("Falha ao abrir/projetar o arquivo")
        raise ErroProjecao(f"Falha ao projetar: {e}")
    finally:
        pythoncom.CoUninitialize()

    # O Windows pode abrir a projeção minimizada quando o PowerPoint é
    # acionado por um processo em segundo plano. Garante o modo tela cheia
    # (ppSlideShowFullScreen = 1) e tenta ativar a janela. Nunca quebra a
    # projeção: falhas aqui apenas são registradas (sem stack, em warning).
    try:
        pythoncom.CoInitialize()
        janela_slides = apresentacao.SlideShowWindow
        janela_slides.WindowState = 1
        try:
            janela_slides.Activate()
        except Exception:
            pass
    except Exception:
        log.warning("Não consegui garantir o primeiro plano do slideshow")
    finally:
        pythoncom.CoUninitialize()


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
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if not user32.SetForegroundWindow(hwnd):
        # O Windows restringe mudança de foreground vinda de background; um
        # toque inofensivo na tecla Alt libera a permissão.
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU pressiona e solta
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    if not _janela_em_tela_cheia(user32, hwnd):
        user32.keybd_event(0x7A, 0, 0, 0)  # VK_F11 (tela cheia no Chrome)
        time.sleep(0.05)
        user32.keybd_event(0x7A, 0, 2, 0)
    return True


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
    return True


def abrir_youtube(youtube_id: str, host_port: str | None = None) -> dict:
    """Abre um vídeo do YouTube em tela cheia suave (fallback: navegador)."""
    if not re.match(r"^[A-Za-z0-9_-]{6,}$", youtube_id or ""):
        raise ErroProjecao("Id de vídeo inválido.")
    player_url = f"http://127.0.0.1:{_porta_de(host_port)}/player/{youtube_id}"
    tela_cheia = _abrir_player(player_url)
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
            else:
                tela_cheia = False
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