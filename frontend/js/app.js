/* app.js — Projeção de cultos (vanilla, sem dependências) */

(function () {
  "use strict";

  const campo = document.getElementById("campo");
  const form = document.getElementById("form-busca");
  const abas = {
    acervo: document.getElementById("aba-acervo"),
    play: document.getElementById("aba-play"),
    agenda: document.getElementById("aba-agenda"),
  };
  const tabsBtns = {
    acervo: document.getElementById("tab-acervo"),
    play: document.getElementById("tab-play"),
    agenda: document.getElementById("tab-agenda"),
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
  const formLink = document.getElementById("form-link");
  const campoLink = document.getElementById("campo-link");

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
  // Registra o último controle tocado para piscá-lo em resposta à ação
  // (verde = sucesso, vermelho = erro) em vez de mostrar mensagem.
  var ultimoControle = null;
  document.addEventListener("pointerdown", function (e) {
    var el = e.target && e.target.closest ? e.target.closest("button, .controle-btn, .item-lista, .play-card") : null;
    if (el) ultimoControle = el;
  }, true);

  function mostrarToast(msg, tipo) {
    // Feedback sutil: pisca o próprio botão tocado em verde (ok) ou vermelho
    // (erro). Não mostra mais nenhuma mensagem persistente na tela.
    var alvo = ultimoControle;
    if (alvo) {
      var classe = tipo === "ok"
        ? "flash-ok"
        : tipo === "erro"
          ? "flash-erro"
          : "flash-info";
      alvo.classList.remove("flash-ok", "flash-erro", "flash-info");
      void alvo.offsetWidth; // reinicia a animação
      alvo.classList.add(classe);
      clearTimeout(mostrarToast._t);
      mostrarToast._t = setTimeout(function () {
        alvo.classList.remove("flash-ok", "flash-erro", "flash-info");
      }, 700);
    }
    if (toast) toast.hidden = true;
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
        : aba === "agenda"
          ? "…"
          : "Buscar música no YouTube…";

    if (aba === "play") { carregarPlaybacks(); }
    if (aba === "agenda") { carregarAgenda(); }

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
  tabsBtns.agenda.addEventListener("click", function () { ativarAba("agenda"); });

  /* ---------- abas retráteis (playbacks/canais) ---------- */
  (function () {
    var chave = "igreja_colapsaveis";
    var estado = {};
    try { estado = JSON.parse(localStorage.getItem(chave) || "{}"); } catch (e) {}

    document.querySelectorAll(".colapsavel").forEach(function (sec) {
      var titulo = sec.querySelector(".colapsavel-titulo");
      if (!titulo) return;
      var id = sec.id;

      function aplicar() {
        var aberto = true;
        if (id && Object.prototype.hasOwnProperty.call(estado, id)) {
          aberto = estado[id] !== false;
        }
        sec.classList.toggle("colapsavel-aberto", aberto);
        if (titulo) titulo.setAttribute("aria-expanded", aberto ? "true" : "false");
      }

      function alternar() {
        var aberto = sec.classList.toggle("colapsavel-aberto");
        if (titulo) titulo.setAttribute("aria-expanded", aberto ? "true" : "false");
        if (id) { estado[id] = aberto; localStorage.setItem(chave, JSON.stringify(estado)); }
      }

      titulo.addEventListener("click", alternar);
      titulo.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alternar(); }
      });
      aplicar();
    });
  })();

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
        removerFavoritoPlay(p.id);
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

      const ver = document.createElement("button");
      ver.type = "button";
      ver.className = "play-ver";
      ver.textContent = "👁";
      ver.title = "Ver/ouvir no celular antes de projetar";
      ver.addEventListener("click", function () { abrirPreview(p); });

      const editarNome = document.createElement("button");
      editarNome.type = "button";
      editarNome.className = "play-edit";
      editarNome.textContent = "✏️";
      editarNome.title = "Renomear playback";
      editarNome.addEventListener("click", function () { renomearPlayback(p); });

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
        removerFavoritoPlay(p.id);
      });

      linha.appendChild(fav);
      linha.appendChild(info);
      linha.appendChild(editarNome);
      linha.appendChild(ver);
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

  function removerFavoritoPlay(playbackId) {
    if (!confirm("Remover este playback dos salvos?")) return;
    fetch("/api/playback/" + playbackId, { method: "DELETE" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) {
          mostrarToast("Removido ✓", "ok");
          carregarPlaybacks();
        } else {
          mostrarToast(d.erro || "Falha ao remover.", "erro");
        }
      })
      .catch(function () {
        mostrarToast("Falha ao remover.", "erro");
      });
  }

  function renomearPlayback(p) {
    const novo = prompt("Novo nome do playback:", p.titulo || "");
    if (novo === null) return; // cancelado
    const nome = novo.trim();
    if (!nome || nome === (p.titulo || "").trim()) return;
    fetch("/api/playback/" + p.id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo: nome }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.id) {
          mostrarToast("Renomeado ✓", "ok");
          carregarPlaybacks();
        } else {
          mostrarToast(d.erro || "Falha ao renomear.", "erro");
        }
      })
      .catch(function () { mostrarToast("Falha ao renomear.", "erro"); });
  }

  /* ---------- prévia do playback no celular ---------- */
  const modalPreview = document.getElementById("modal-preview");
  const previewIframe = document.getElementById("preview-iframe");
  const previewTitulo = document.getElementById("preview-titulo");
  const btnPreviewProjetar = document.getElementById("btn-preview-projetar");
  let previewAtual = null;

  function fecharPreview() {
    if (!modalPreview) return;
    modalPreview.hidden = true;
    if (previewIframe) previewIframe.src = "";
    previewAtual = null;
  }

  function abrirPreview(p) {
    previewAtual = p;
    if (previewTitulo) previewTitulo.textContent = p.titulo || "Prévia";
    if (previewIframe) {
      if (p.youtube_id) {
        previewIframe.src =
          "https://www.youtube.com/embed/" + p.youtube_id +
          "?autoplay=1&rel=0&playsinline=1";
      } else if (p.url) {
        previewIframe.src = p.url;
      } else {
        previewIframe.src = "";
      }
    }
    if (modalPreview) modalPreview.hidden = false;
  }

  if (modalPreview) {
    modalPreview.querySelectorAll("[data-fechar-preview]").forEach(function (el) {
      el.addEventListener("click", fecharPreview);
    });
    if (btnPreviewProjetar) {
      btnPreviewProjetar.addEventListener("click", function () {
        const p = previewAtual;
        fecharPreview();
        if (p) projetar("playback", p.id);
      });
    }
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

  /* ---------- salvar playback por link ---------- */
  if (formLink) {
    formLink.addEventListener("submit", function (e) {
      e.preventDefault();
      const url = campoLink.value.trim();
      if (!url) {
        campoLink.focus();
        return;
      }
      const btn = formLink.querySelector("button");
      btn.disabled = true;
      fetch("/api/youtube/salvar_link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.id) {
            mostrarToast("Salvo ✓", "ok");
            campoLink.value = "";
            carregarPlaybacks();
          } else {
            mostrarToast(d.erro || "Falha ao salvar.", "erro");
          }
        })
        .catch(function () { mostrarToast("Falha ao salvar.", "erro"); })
        .finally(function () { btn.disabled = false; });
    });
  }

  /* ---------- agenda (programação do culto) ---------- */
  const agendaLista = document.getElementById("agenda-lista");
  const agendaVazio = document.getElementById("agenda-vazio");
  const formAgenda = document.getElementById("form-agenda");
  const campoNome = document.getElementById("campo-nome");

  // Galeria de busca por item, aberta ao tocar em "➕ Item" de uma ficha.
  let buscaItemAberta = null;  // id da ficha em edição de item, ou null
  let buscaItemTimer = null;

  function renderizarAgenda(lista) {
    agendaLista.textContent = "";
    agendaVazio.hidden = lista.length !== 0;

    lista.forEach(function (f) {
      const card = document.createElement("div");
      card.className = "agenda-card";

      const infos = document.createElement("div");
      infos.className = "play-info";
      const nome = document.createElement("span");
      nome.className = "play-nome";
      nome.textContent = f.nome;
      const item = document.createElement("span");
      item.className = "play-url" + (f.texto ? "" : " suave");
      item.textContent = f.texto || "Sem item — toque em ➕";
      infos.appendChild(nome);
      infos.appendChild(item);
      infos.addEventListener("click", function () {
        if (f.tipo && f.ref_id != null) {
          projetarFicha(f.id, f.nome);
        } else {
          abrirBuscaItem(f);
        }
      });

      const acoes = document.createElement("div");
      acoes.className = "agenda-acoes";

      const tocar = document.createElement("button");
      tocar.type = "button";
      tocar.className = "botao botao-acao";
      tocar.textContent = "▶";
      tocar.title = "Reproduzir";
      tocar.addEventListener("click", function () {
        if (f.tipo && f.ref_id != null) {
          projetarFicha(f.id, f.nome);
        } else {
          abrirBuscaItem(f);
        }
      });

      const addItem = document.createElement("button");
      addItem.type = "button";
      addItem.className = "botao botao-secundario";
      addItem.textContent = f.tipo ? "🔄 Item" : "➕";
      addItem.title = "Escolher/adicionar o item";
      addItem.addEventListener("click", function () {
        abrirBuscaItem(f);
      });

      const remover = document.createElement("button");
      remover.type = "button";
      remover.className = "play-remover";
      remover.textContent = "✕";
      remover.title = "Remover";
      remover.addEventListener("click", function () {
        removerFicha(f.id);
      });

      acoes.appendChild(tocar);
      acoes.appendChild(addItem);
      acoes.appendChild(remover);

      card.appendChild(infos);
      card.appendChild(acoes);
      agendaLista.appendChild(card);

      // A busca de item fica "embaixo" do card, quando aberta.
      if (buscaItemAberta === f.id) {
        card.appendChild(montarPainelBuscaItem(f));
      } else if (f.tipo && f.ref_id != null) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "botao botao-secundario agenda-desvincula";
        remove.textContent = "remover item";
        remove.addEventListener("click", function () {
          if (confirm("Remover o item de " + f.nome + "?")) {
            setItemFicha(f.id, null, null, "");
          }
        });
        card.appendChild(remove);
      }
    });
  }

  function montarPainelBuscaItem(f) {
    const painel = document.createElement("div");
    painel.className = "agenda-busca";
    painel.id = "painel-busca-" + f.id;

    const caixa = document.createElement("div");
    caixa.className = "agenda-busca-caixa";
    const input = document.createElement("input");
    input.className = "campo";
    input.type = "search";
    input.placeholder = "Buscar hino, bíblia ou playback salvo…";
    input.autocomplete = "off";
    caixa.appendChild(input);

    const fechar = document.createElement("button");
    fechar.type = "button";
    fechar.className = "botao botao-secundario";
    fechar.textContent = "✕";
    fechar.title = "Fechar";
    fechar.addEventListener("click", function () {
      buscaItemAberta = null;
      carregarAgenda();
    });
    caixa.appendChild(fechar);

    const resultados = document.createElement("div");
    resultados.className = "item-lista agenda-busca-res";

    painel.appendChild(caixa);
    painel.appendChild(resultados);

    function executar() {
      const q = input.value.trim();
      if (!q) { resultados.textContent = ""; return; }
      fetch("/api/pesquisa?q=" + encodeURIComponent(q) + "&limite=6")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          resultados.textContent = "";
          const linhas = [];
          ["harpa", "biblia", "playback"].forEach(function (g) {
            (d[g] || []).forEach(function (it) {
              linhas.push({ tipo: g, ref_id: it.id, rotulo: formatarItem(g, it) });
            });
          });
          if (!linhas.length) {
            const v = document.createElement("p");
            v.className = "vazio";
            v.textContent = "Nada encontrado.";
            resultados.appendChild(v);
            return;
          }
          linhas.forEach(function (it) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "card";
            const et = document.createElement("span");
            et.className = "card-etiqueta " + etiquetaClasse(it.tipo);
            et.textContent = etiquetaTexto(it.tipo);
            const p = document.createElement("span");
            p.className = "card-principal";
            p.textContent = it.rotulo;
            b.appendChild(et);
            b.appendChild(p);
            b.addEventListener("click", function () {
              setItemFicha(f.id, it.tipo, it.ref_id, it.rotulo);
            });
            resultados.appendChild(b);
          });
        })
        .catch(function () {
          resultados.textContent = "";
          const v = document.createElement("p");
          v.className = "vazio";
          v.textContent = "Falha na busca.";
          resultados.appendChild(v);
        });
    }

    input.addEventListener("input", function () {
      clearTimeout(buscaItemTimer);
      buscaItemTimer = setTimeout(executar, 300);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); clearTimeout(buscaItemTimer); executar(); }
    });
    setTimeout(function () { input.focus(); }, 0);
    return painel;
  }

  function formatarItem(g, it) {
    if (g === "harpa") return "Harpa " + it.numero + (it.titulo ? " · " + it.titulo : "");
    if (g === "biblia") return (it.livro_exibicao || it.livro) + " " + it.capitulo;
    return it.titulo;
  }

  function setItemFicha(fichaId, tipo, refId, rotulo) {
    const corpo = { tipo: tipo, ref_id: refId, texto: rotulo || "" };
    fetch("/api/agenda/" + fichaId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (r.ok) {
          mostrarToast("Item salvo ✓", "ok");
          buscaItemAberta = null;
          carregarAgenda();
        } else {
          mostrarToast(r.d.erro || "Falha ao salvar.", "erro");
        }
      })
      .catch(function () { mostrarToast("Falha ao salvar.", "erro"); });
  }

  function abrirBuscaItem(f) {
    buscaItemAberta = (buscaItemAberta === f.id) ? null : f.id;
    carregarAgenda();
  }

  function carregarAgenda() {
    fetch("/api/agenda")
      .then(function (r) { return r.json(); })
      .then(renderizarAgenda)
      .catch(function () {
        mostrarToast("Falha ao listar a agenda.", "erro");
      });
  }

  function projetarFicha(fichaId, nome) {
    mostrarToast("Reproduzindo " + nome + "…", "");
    fetch("/api/agenda/" + fichaId + "/projetar", { method: "POST" })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (r.ok) {
          mostrarToast("Renderizado ✓", "ok");
        } else {
          mostrarToast(r.d.erro || "Falha ao reproduzir.", "erro");
        }
      })
      .catch(function () {
        mostrarToast("Falha ao reproduzir.", "erro");
      });
  }

  function removerFicha(fichaId) {
    if (!confirm("Remover esta pessoa da agenda?")) return;
    fetch("/api/agenda/" + fichaId, { method: "DELETE" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) { mostrarToast("Removido ✓", "ok"); carregarAgenda(); }
      })
      .catch(function () { mostrarToast("Falha ao remover.", "erro"); });
  }

  formAgenda.addEventListener("submit", function (e) {
    e.preventDefault();
    const nome = campoNome.value.trim();
    if (!nome) { campoNome.focus(); return; }
    fetch("/api/agenda", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome }),
    })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      })
      .then(function (r) {
        if (r.ok) {
          campoNome.value = "";
          mostrarToast(nome + " adicionado ✓", "ok");
          carregarAgenda();
        } else {
          mostrarToast(r.d.erro || "Falha ao adicionar.", "erro");
        }
      })
      .catch(function () { mostrarToast("Falha ao adicionar.", "erro"); });
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

  /* ---------- controle remoto (tela preta / slides / play-pause) ---------- */
  (function () {
    var btnPreto = document.getElementById("btn-tela-preta");
    var iconePreto = document.getElementById("icone-preto");
    var btnProx = document.getElementById("btn-slide-prox");
    var btnAnt = document.getElementById("btn-slide-ant");
    var btnPause = document.getElementById("btn-player-pause");
    var iconePause = document.getElementById("icone-pause");
    var btnRecomecar = document.getElementById("btn-player-recomecar");
    var btnPrimeiroPlano = document.getElementById("btn-primeiro-plano");

    function acao(payload) {
      return fetch("/api/projecao/acao", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) mostrarToast(d.erro || "Não deu para executar.", "erro");
          return d;
        })
        .catch(function () { mostrarToast("Falha no controle.", "erro"); });
    }

    function marcarPreto(estaPreto) {
      if (estaPreto) {
        btnPreto.classList.add("preto-ativo");
        if (iconePreto) iconePreto.textContent = "◼";
      } else {
        btnPreto.classList.remove("preto-ativo");
        if (iconePreto) iconePreto.textContent = "⬛";
      }
    }

    function carregarEstadoPreto() {
      fetch("/api/status")
        .then(function (r) { return r.json(); })
        .then(function (d) { marcarPreto(!!d.projecao && d.projecao === "preto"); })
        .catch(function () {});
    }

    if (btnPreto) {
      btnPreto.addEventListener("click", function () {
        fetch("/api/projecao/tela_preta", { method: "POST" })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              marcarPreto(!!d.preto);
              mostrarToast(d.preto ? "Tela preta ✓" : "Tela preta desligada.", "ok");
            } else {
              mostrarToast(d.erro || "Falha na tela preta.", "erro");
            }
          })
          .catch(function () { mostrarToast("Falha na tela preta.", "erro"); });
      });
    }

    if (btnProx) {
      btnProx.addEventListener("click", function () { acao({ acao: "slide_proximo" }); });
    }
    if (btnAnt) {
      btnAnt.addEventListener("click", function () { acao({ acao: "slide_anterior" }); });
    }
    if (btnPause) {
      btnPause.addEventListener("click", function () { acao({ acao: "play_pause" }); });
    }
    if (btnRecomecar) {
      btnRecomecar.addEventListener("click", function () {
        acao({ acao: "recomecar" });
      });
    }
    if (btnPrimeiroPlano) {
      btnPrimeiroPlano.addEventListener("click", function () {
        fetch("/api/projecao/primeiro_plano", { method: "POST" })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              mostrarToast("Trago para frente ✓", "ok");
            } else {
              mostrarToast(d.erro || "Nada em projeção.", "erro");
            }
          })
          .catch(function () { mostrarToast("Falha ao trazer para frente.", "erro"); });
      });
    }

    carregarEstadoPreto();
  })();

  /* ---------- início ---------- */
  vazio.hidden = false;
  carregarStatus();
  carregarPlaybacks();
  carregarCanais();
  carregarAgenda();
})();