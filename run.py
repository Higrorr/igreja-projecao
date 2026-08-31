"""
run.py
======

Ponto de entrada para o executável compilado (PyInstaller).

Sobe o servidor Flask numa thread (daemon) e mostra uma pequena janela de
controle com o endereço que o celular deve acessar e um botão "Parar".

A janela usa Tkinter (embutido no CPython, zero dependências). Se por algum
motivo não abrir, o servidor continua rodando em segundo plano.

A porta pode ser sobrescrita com a variável de ambiente IGREJA_PORT.
"""

import os
import socket
import threading


def _ip_local() -> str:
    """IP v4 desta máquina na rede local (melhor esforço)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(1.0)
            s.connect(("8.8.8.8", 80))  # não envia pacotes; só descobre a rota
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def _manter_vivo() -> None:
    """Mantém o processo vivo caso a janela de controle não consiga abrir."""
    import time
    while True:
        time.sleep(3600)


def _janela_controle(porta: int) -> None:
    import tkinter as tk

    ip = _ip_local()
    url = f"http://{ip}:{porta}"

    try:
        root = tk.Tk()
    except Exception as e:  # sem interface disponível: segue só em servidor
        try:
            print(f"[igreja] janela de controle indisponível: {e}", file=__import__("sys").stderr)
        except Exception:
            pass
        _manter_vivo()
        return

    root.title("Projeção · Igreja")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    try:
        root.eval("tk::PlaceWindow . center")
    except Exception:
        pass

    def parar() -> None:
        try:
            root.destroy()
        finally:
            os._exit(0)

    tk.Label(root, text="Servidor rodando", font=("Segoe UI", 13, "bold")).pack(
        pady=(20, 0)
    )

    def copiar_url(_=None) -> None:
        root.clipboard_clear()
        root.clipboard_append(url)

    lbl_url = tk.Label(
        root,
        text=url,
        fg="#2b6cb0",
        cursor="hand2",
        font=("Consolas", 15, "bold"),
    )
    lbl_url.bind("<Button-1>", copiar_url)
    lbl_url.pack(pady=(4, 0))

    tk.Label(
        root,
        text="Abra este endereço no celular (mesma rede Wi-Fi).\n"
             "Clique no endereço para copiar.",
        fg="#8a93a6",
        font=("Segoe UI", 9),
        justify="center",
    ).pack(pady=(8, 6))

    tk.Button(
        root,
        text="Parar servidor",
        command=parar,
        font=("Segoe UI", 11),
        padx=18,
        pady=6,
    ).pack(pady=(4, 18))

    root.protocol("WM_DELETE_WINDOW", parar)
    root.mainloop()


def main() -> None:
    porta = int(os.environ.get("IGREJA_PORT", "5000"))

    from backend.app import app
    from backend.database import database

    database.criar_tabelas()  # garante as tabelas (incl. youtube_cache) na 1ª execução

    threading.Thread(
        target=app.run,
        kwargs={
            "host": "0.0.0.0",
            "port": porta,
            "debug": False,
            "use_reloader": False,
        },
        daemon=True,
    ).start()

    _janela_controle(porta)

    # Janela fechada: encerra o processo (e a thread do servidor junto).
    os._exit(0)


if __name__ == "__main__":
    main()