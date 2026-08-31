/* app.js — Projeção de cultos (vanilla, sem dependências) */

(function () {
  "use strict";

  const campo = document.getElementById("campo");
  const form = document.getElementById("form-busca");
  const abas = {
    acervo: document.getElementById("aba-acervo"),
    play: document.getElementById("aba-play"),
  };
  const tabsBtns = {
    acervo: document.getElementById("tab-acervo"),
    play: document.getElementById("tab-play"),
  };
  const resultados = document.getElementById("resultados");
  const vazio = document.getElementById("vazio");
  const carregando = document.getElementById("carregando");
  const toast = document.getElementById("toast");
  const status = document.getElementById("status");
  const contagem = document.getElementById("contagem");
  const btnAtualizar = document.getElementById("btn-atualizar");

  const listaPlay = document.getElementById("lista-play");
  const playVazio = document.getElementById("play-vazio");
  const playBadge = document.getElementById("play-badge");

  const listaCanais = document.getElementById("lista-canais");
  const canaisVazio = document.getElementById("canais-vazio");
  const canaisBadge = document.getElementById("canais-badge");
  const formCanal = document.getElementById("form-canal");
  const campoCanal = document.getElementById("campo-canal");

  const chips = document.querySelectorAll(".chip-toggle");
  const btnBuscarYt = document.getElementById("btn-buscar-yt");
  const ytSection = document.getElementById("yt");
  const ytLista = document.getElementById("yt-lista");
  const ytVazio = document.getElementById("yt-vazio");
  const ytFonte = document.getElementById("yt-fonte");

  const filtros = { playback: true, instrumental: true, vivo: false };

  let abaAtiva = "acervo";
  let ultimaQuery = "";
  let timerYt = null;

  /* ---------- helpers ---------- */
  function mostrarToast(msg, tipo) {
    toast.textContent = msg;
    toast.className = "toast " + (tipo || "");
    toast.hidden = false;
    clearTimeout(mostrarToast._t);
    mostrarToast._t = setTimeout(function () { toast.hidden = true; }, 2600);
  }

  function etiquetaTexto(tipo) {
    if (tipo === "biblia") return "Bíblia";
    if (tipo === "harpa") return "Harpa";
    return "Playback";
  }

  function etiquetaClasse(tipo) {
    if (tipo === "biblia") return "et-biblia";
    if (tipo === "harpa") return "et-harpa";
    return "et-play";
  }

  /* ---------- abas ---------- */
  function ativarAba(aba) {
    abaAtiva = aba;
    Object.keys(abas).forEach(function (k) {
      abas[k].hidden = k !== aba;
      tabsBtns[k].classList.toggle("ativa", k === aba);
      tabsBtns[k].setAttribute("aria-selected", k === aba ? "true" : "false");
    });
    campo.placeholder =
      aba === "acervo"
        ? "Bíblia ou hino (ex.: Salmos 23)"
        : "Buscar música no YouTube…";

    if (aba === "play") { carregarPlaybacks(); }

    const q = campo.value.trim();
    if (!q) return;
    if (aba === "acervo") {
      clearTimeout(timerYt);
      buscarLocal(q);
    } else {
      buscarYoutube(q, false);
    }
  }

  tabsBtns.acervo.addEventListener("click", function () { ativarAba("acervo"); });
  tabsBtns.play.addEventListener("click", function () { ativarAba("play"); });

  /* ---------- renderização (acervo local) ---------- */
  function botaoItem(grupo, item) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "card";

    const et = document.createElement("span");
    et.className = "card-etiqueta " + etiquetaClasse(grupo);
    et.textContent = etiquetaTexto(grupo);

    const p = document.createElement("span");
    p.className = "card-principal";

    const s = document.createElement("span");
    s.className = "card-secundario";

    if (grupo === "biblia") {
      p.textContent = item.livro_exibicao + " " + item.capitulo;
      s.textContent = item.arquivo.replace(/\.pptx$/i, "");
    } else if (grupo === "harpa") {
      p.textContent = "Harpa " + item.numero;
      s.textContent = item.titulo || item.arquivo.replace(/\.pptx$/i, "");
    } else {
      p.textContent = item.titulo;
      s.textContent = item.url || ("Playback " + item.id);
    }

    b.appendChild(et);
    b.appendChild(p);
    b.appendChild(s);
    b.addEventListener("click", function () { projetar(grupo, item.id); });
    return b;
  }

  function montarGrupo(grupo, itens) {
    const nomes = { biblia: "Bíblia", harpa: "Harpa", playback: "Playbacks" };
    const secao = document.createElement("section");
    secao.className = "grupo";

    const titulo = document.createElement("h2");
    titulo.className = "grupo-titulo";
    titulo.textContent = nomes[grupo];
    const badge = document.createElement("span");
    badge.className = "grupo-badge";
    badge.textContent = "(" + itens.length + ")";
    titulo.appendChild(badge);

    const lista = document.createElement("div");
    lista.className = "item-lista";
    itens.forEach(function (item) { lista.appendChild(botaoItem(grupo, item)); });

    secao.appendChild(titulo);
    secao.appendChild(lista);
    return secao;
  }

  function renderizar(dados) {
    resultados.textContent = "";
    let algum = false;
    ["biblia", "harpa", "playback"].forEach(function (grupo) {
      if (dados[grupo] && dados[grupo].length) {
        algum = true;
        resultados.appendChild(montarGrupo(grupo, dados[grupo]));
      }
    });
    vazio.hidden = algum || ultimaQuery !== "";
    if (!algum && ultimaQuery !== "") {
      vazio.textContent = "";
      const p = document.createElement("p");
      p.textContent = "Nada encontrado para \u201c" + ultimaQuery +
        "\u201d. Tente na aba Playbacks para buscar no YouTube.";
      vazio.appendChild(p);
      vazio.hidden = false;
    }
  }

  /* ---------- busca local (acervo) ---------- */
  function buscarLocal(q) {
    ultimaQuery = q.trim();
    if (!ultimaQuery) {
      resultados.textContent = "";
      vazio.hidden = false;
      vazio.textContent = "";
      const p = document.createElement("p");
      p.textContent = "Digite para buscar um capítulo ou hino.";
      vazio.appendChild(p);
      return;
    }
    carregando.hidden = false;
    vazio.hidden = true;
    fetch("/api/pesquisa?q=" + encodeURIComponent(ultimaQuery))
      .then(function (r) { return r.json(); })
      .then(renderizar)
      .catch(function () {
        mostrarToast("Falha na busca. Servidor online?", "erro");
      })
      .finally(function () { carregando.hidden = true; });
  }

  function buscar(q) {
    if (abaAtiva === "acervo") {
      buscarLocal(q);
    } else {
      buscarPlay(q);
    }
  }

  function buscarPlay(q) {
    ultimaQuery = q.trim();
    if (!ultimaQuery) {
      ytLista.textContent = "";
      ytSection.hidden = true;
      return;
    }
    clearTimeout(timerYt);
    timerYt = setTimeout(function () { buscarYoutube(ultimaQuery, false); }, 900);
  }

  let debounce;
  campo.addEventListener("input", function () {
    clearTimeout(debounce);
    debounce = setTimeout(function () { buscar(campo.value); }, 250);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    clearTimeout(debounce);
    buscar(campo.value);
  });

  document.querySelectorAll(".dica-chip:not(.chip-toggle)").forEach(function (chip) {
    chip.addEventListener("click", function () {
      campo.value = chip.dataset.sugestao;
      ativarAba("acervo");
      buscarLocal(campo.value);
      campo.focus();
    });
  });

  /* ---------- YouTube (pesquisa ao vivo + cache) ---------- */
  function paramsYoutube(termo, forcar) {
    const p = new URLSearchParams({ q: termo });
    p.set("playback", filtros.playback ? "1" : "0");
    p.set("instrumental", filtros.instrumental ? "1" : "0");
    p.set("vivo", filtros.vivo ? "1" : "0");
    p.set("forcar", forcar ? "1" : "0");
    return p.toString();
  }

  function buscarYoutube(termo, forcar) {
    fetch("/api/youtube?" + paramsYoutube(termo, forcar))
      .then(function (r) { return r.json(); })
      .then(renderYoutube)
      .catch(function () {
        ytSection.hidden = false;
        ytLista.textContent = "";
        ytFonte.textContent = "";
        ytVazio.textContent = "Falha ao consultar o YouTube.";
        ytVazio.hidden = false;
      });
  }

  function renderYoutube(dados) {
    ytSection.hidden = false;
    ytLista.textContent = "";
    ytFonte.textContent = "";

    if (dados.erro) {
      ytVazio.textContent = "⚠ " + dados.erro;
      ytVazio.hidden = false;
      return;
    }

    ytFonte.textContent = dados.fonte === "cache" ? "· cache" : "· ao vivo";

    const res = dados.resultados || [];
    if (!res.length) {
      ytVazio.textContent = "Nada encontrado no YouTube.";
      ytVazio.hidden = false;
      return;
    }

    ytVazio.hidden = true;
    res.forEach(function (v) {
      const card = document.createElement("div");
      card.className = "yt-card";

      const thumb = document.createElement("img");
      thumb.className = "yt-thumb";
      thumb.src = v.thumb || "";
      thumb.alt = "";
      thumb.loading = "lazy";

      const info = document.createElement("div");
      info.className = "yt-info";

      const titulo = document.createElement("span");
      titulo.className = "yt-titulo";
      titulo.textContent = v.titulo;

      const canal = document.createElement("span");
      canal.className = "yt-canal";
      canal.textContent = v.canal;
      if (v.prioridade) {
        const pri = document.createElement("span");
        pri.className = "yt-pri";
        pri.textContent = "★ priorizado";
        canal.appendChild(pri);
      }

      const tags = document.createElement("span");
      tags.className = "yt-tags";
      (v.tags || []).forEach(function (t) {
        const b = document.createElement("span");
        b.className = "yt-tag";
        b.textContent = t;
        tags.appendChild(b);
      });

      info.appendChild(titulo);
      info.appendChild(canal);
      info.appendChild(tags);

      const acoes = document.createElement("div");
      acoes.className = "yt-acoes";

      const abrir = document.createElement("button");
      abrir.type = "button";
      abrir.className = "botao botao-acao";
      abrir.textContent = "▶ ABRIR";
      abrir.addEventListener("click", function () { abrirYoutube(v); });

      const fav = document.createElement("button");
      fav.type = "button";
      fav.className = "botao botao-secundario" + (v.favorito ? " yt-fav-salvo" : "");
      fav.textContent = v.favorito ? "⭐ Salvo" : "☆ Salvar";
      fav.addEventListener("click", function () {
        alternarFavorito(v, fav);
      });

      acoes.appendChild(abrir);
      acoes.appendChild(fav);

      if (!v.prioridade) {
        const pri = document.createElement("button");
        pri.type = "button";
        pri.className = "botao botao-secundario";
        pri.textContent = "★ Priorizar";
        pri.title = "Colocar este canal no topo da busca";
        pri.addEventListener("click", function () {
          priorizarCanal(v.canal || "", v.channel_id || null, pri);
        });
        acoes.appendChild(pri);
      }

      card.appendChild(thumb);
      card.appendChild(info);
      card.appendChild(acoes);
      ytLista.appendChild(card);
    });
  }

  function abrirYoutube(v) {
    mostrarToast("Abrindo no navegador…", "");
    fetch("/api/youtube/abrir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ youtube_id: v.youtube_id }),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (r.ok) { mostrarToast("Abrindo ✓", "ok"); }
        else { mostrarToast(r.d.erro || "Falha ao abrir.", "erro"); }
      })
      .catch(function () {
        mostrarToast("Falha ao abrir.", "erro");
      });
  }

  function alternarFavorito(v, btn) {
    const endpoint = v.favorito ? "/api/youtube/desfavoritar" : "/api/youtube/favoritar";
    const body = { youtube_id: v.youtube_id, titulo: v.titulo, url: v.url };
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (!r.ok) {
          mostrarToast(r.d.erro || "Falha ao salvar.", "erro");
          return;
        }
        v.favorito = !v.favorito;
        btn.textContent = v.favorito ? "⭐ Salvo" : "☆ Salvar";
        btn.classList.toggle("yt-fav-salvo", v.favorito);
        mostrarToast(v.favorito ? "Salvo nos playbacks ✓" : "Removido ✓", "ok");
        carregarPlaybacks();
      })
      .catch(function () {
        mostrarToast("Falha ao salvar.", "erro");
      });
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      const t = chip.dataset.t;
      filtros[t] = !filtros[t];
      chip.classList.toggle("ativo", filtros[t]);
      if (abaAtiva !== "play") return;
      const atual = campo.value.trim();
      if (atual) {
        buscarYoutube(atual, true);
      }
    });
  });

  btnBuscarYt.addEventListener("click", function () {
    const atual = campo.value.trim();
    if (!atual) {
      mostrarToast("Digite o nome da música antes.", "erro");
      campo.focus();
      return;
    }
    ytVazio.textContent = "Buscando…";
    ytVazio.hidden = false;
    ytLista.textContent = "";
    buscarYoutube(atual, true);
  });

  /* ---------- projeção local ---------- */
  function projetar(tipo, id) {
    mostrarToast("Projetando…", "");
    fetch("/api/projetar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tipo: tipo, id: id }),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (r.ok) {
          mostrarToast("Projetado com sucesso ✓", "ok");
        } else {
          mostrarToast(r.d.erro || "Falha ao projetar.", "erro");
        }
      })
      .catch(function () {
        mostrarToast("Falha ao projetar. Servidor online?", "erro");
      });
  }

  /* ---------- playbacks salvos (favoritos) ---------- */
  function renderizarPlaybacks(lista) {
    listaPlay.textContent = "";
    playBadge.textContent = "(" + lista.length + ")";
    playVazio.hidden = lista.length !== 0;

    lista.forEach(function (p) {
      const linha = document.createElement("div");
      linha.className = "play-item";

      const fav = document.createElement("button");
      fav.type = "button";
      fav.className = "play-fav ativo";
      fav.textContent = "⭐";
      fav.title = "Remover dos salvos";
      fav.addEventListener("click", function () {
        removerFavoritoPlay(p.youtube_id);
      });

      const info = document.createElement("div");
      info.className = "play-info";
      const nome = document.createElement("span");
      nome.className = "play-nome";
      nome.textContent = p.titulo;
      const url = document.createElement("span");
      url.className = "play-url";
      url.textContent = p.url || ("youtu.be/" + p.youtube_id);
      info.appendChild(nome);
      info.appendChild(url);

      const tocar = document.createElement("button");
      tocar.type = "button";
      tocar.className = "play-tocar";
      tocar.textContent = "►";
      tocar.title = "Abrir no navegador";
      tocar.addEventListener("click", function () { projetar("playback", p.id); });

      const remover = document.createElement("button");
      remover.type = "button";
      remover.className = "play-remover";
      remover.textContent = "✕";
      remover.title = "Remover dos salvos";
      remover.addEventListener("click", function () {
        removerFavoritoPlay(p.youtube_id);
      });

      linha.appendChild(fav);
      linha.appendChild(info);
      linha.appendChild(tocar);
      linha.appendChild(remover);
      listaPlay.appendChild(linha);
    });
  }

  function carregarPlaybacks() {
    fetch("/api/playbacks")
      .then(function (r) { return r.json(); })
      .then(renderizarPlaybacks)
      .catch(function () {
        mostrarToast("Falha ao listar playbacks.", "erro");
      });
  }

  function removerFavoritoPlay(youtubeId) {
    if (!confirm("Remover este playback dos salvos?")) return;
    fetch("/api/youtube/desfavoritar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ youtube_id: youtubeId }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) {
          mostrarToast("Removido ✓", "ok");
          carregarPlaybacks();
        }
      })
      .catch(function () {
        mostrarToast("Falha ao remover.", "erro");
      });
  }

  /* ---------- canais priorizados ---------- */
  function renderizarCanais(lista) {
    listaCanais.textContent = "";
    canaisBadge.textContent = "(" + lista.length + ")";
    canaisVazio.hidden = lista.length !== 0;

    lista.forEach(function (c) {
      const linha = document.createElement("div");
      linha.className = "play-item";

      const fav = document.createElement("button");
      fav.type = "button";
      fav.className = "play-fav ativo";
      fav.textContent = "★";
      fav.title = "Prioritário na busca";

      const info = document.createElement("div");
      info.className = "play-info";
      const nome = document.createElement("span");
      nome.className = "play-nome";
      nome.textContent = c.nome;
      info.appendChild(nome);

      const remover = document.createElement("button");
      remover.type = "button";
      remover.className = "play-remover";
      remover.textContent = "✕";
      remover.title = "Remover da prioridade";
      remover.addEventListener("click", function () {
        removerCanalPrioridade(c.id);
      });

      linha.appendChild(fav);
      linha.appendChild(info);
      linha.appendChild(remover);
      listaCanais.appendChild(linha);
    });
  }

  function carregarCanais() {
    fetch("/api/canais/prioridade")
      .then(function (r) { return r.json(); })
      .then(renderizarCanais)
      .catch(function () {});
  }

  function priorizarCanal(nome, channelId, btn) {
    if (!nome) return;
    btn.disabled = true;
    fetch("/api/canais/prioridade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome, channel_id: channelId || "" }),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (r.ok) {
          btn.disabled = false;
          mostrarToast("Canal priorizado ✓", "ok");
          carregarCanais();
          if (ultimaQuery) {
            buscarYoutube(ultimaQuery, false);
          }
        } else {
          btn.disabled = false;
          mostrarToast(r.d.erro || "Falha ao priorizar.", "erro");
        }
      })
      .catch(function () {
        btn.disabled = false;
        mostrarToast("Falha ao priorizar.", "erro");
      });
  }

  function removerCanalPrioridade(canalId) {
    if (!confirm("Remover este canal da prioridade?")) return;
    fetch("/api/canais/prioridade/" + canalId, { method: "DELETE" })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        mostrarToast(r.ok ? "Removido ✓" : (r.d.erro || "Falha ao remover."),
                     r.ok ? "ok" : "erro");
        if (r.ok) {
          carregarCanais();
          if (ultimaQuery) {
            buscarYoutube(ultimaQuery, false);
          }
        }
      })
      .catch(function () {
        mostrarToast("Falha ao remover.", "erro");
      });
  }

  formCanal.addEventListener("submit", function (e) {
    e.preventDefault();
    const nome = campoCanal.value.trim();
    if (!nome) {
      campoCanal.focus();
      return;
    }
    priorizarCanal(nome, null, formCanal.querySelector("button"));
    campoCanal.value = "";
  });

  /* ---------- status / atualizar ---------- */
  function carregarStatus() {
    fetch("/api/status")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        contagem.textContent = "📖 " + d.biblia + " · 🎵 " + d.harpa;
        status.hidden = false;
      })
      .catch(function () {
        status.hidden = true;
      });
  }

  btnAtualizar.addEventListener("click", function () {
    btnAtualizar.disabled = true;
    btnAtualizar.textContent = "🔄 Escaneando…";
    fetch("/api/atualizar", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function () {
        mostrarToast("Acervo atualizado ✓", "ok");
        carregarStatus();
      })
      .catch(function () {
        mostrarToast("Falha ao atualizar.", "erro");
      })
      .finally(function () {
        btnAtualizar.disabled = false;
        btnAtualizar.textContent = "🔄 Atualizar";
      });
  });

  /* ---------- início ---------- */
  vazio.hidden = false;
  carregarStatus();
  carregarPlaybacks();
  carregarCanais();
})();