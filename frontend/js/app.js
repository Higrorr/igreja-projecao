/* app.js — Projeção de cultos (vanilla, sem dependências) */

(function () {
  "use strict";

  const campo = document.getElementById("campo");
  const form = document.getElementById("form-busca");
  const resultados = document.getElementById("resultados");
  const vazio = document.getElementById("vazio");
  const carregando = document.getElementById("carregando");
  const toast = document.getElementById("toast");
  const status = document.getElementById("status");
  const contagem = document.getElementById("contagem");
  const btnAtualizar = document.getElementById("btn-atualizar");

  let ultimaQuery = "";

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

  /* ---------- renderização ---------- */
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
      p.textContent = "Nada encontrado para \u201c" + ultimaQuery + "\u201d.";
      vazio.appendChild(p);
      vazio.hidden = false;
    }
  }

  /* ---------- busca ---------- */
  function buscar(q) {
    ultimaQuery = q.trim();
    if (!ultimaQuery) {
      resultados.textContent = "";
      vazio.hidden = false;
      vazio.textContent = "";
      const p = document.createElement("p");
      p.textContent = "Digite para buscar um capítulo, hino ou playback.";
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

  document.querySelectorAll(".dica-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      campo.value = chip.dataset.sugestao;
      buscar(campo.value);
      campo.focus();
    });
  });

  /* ---------- projeção (FASE 5) ---------- */
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
})();