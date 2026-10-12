"use strict";
function readMediaView(hash, filters = ["all"]) {
  if (!hash.startsWith("#media?")) return { query: "", filter: "all" };
  const params = new URLSearchParams(hash.slice(7));
  const filter = params.get("type") || "all";
  return { query: (params.get("q") || "").slice(0, 120), filter: filters.includes(filter) ? filter : "all" };
}
function mediaViewHash(query, filter = "all") {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim().slice(0, 120));
  if (filter !== "all") params.set("type", filter);
  return "#media" + (params.size ? "?" + params.toString() : "");
}
if (typeof module !== "undefined") module.exports = { readMediaView, mediaViewHash };
if (typeof document !== "undefined") {
  const section = document.querySelector("#media");
  const search = document.querySelector("#media-search");
  if (section && search) {
    const cards = [...section.querySelectorAll(".media-card[data-tags]")];
    const filters = [...section.querySelectorAll("[data-filter]")];
    const shortcuts = [...section.querySelectorAll("[data-project-query]")];
    const allowed = filters.map(button => button.dataset.filter);
    const status = section.querySelector(".result-count");
    const reset = section.querySelector("[data-media-reset]");
    const permalink = section.querySelector("[data-media-permalink]");
    const empty = section.querySelector(".no-results");
    const spanish = document.documentElement.lang === "es";
    let state = readMediaView(location.hash, allowed);
    search.value = state.query;
    const render = (write = false, push = false) => {
      let count = 0;
      cards.forEach(card => {
        const visible = matchesMedia({
          tags: card.dataset.tags.split(" "),
          text: [card.querySelector(".media-art, .media-cover")?.textContent,
            card.querySelector("h3")?.textContent, card.dataset.keywords || ""].join(" ")
        }, state.query, state.filter);
        card.hidden = !visible;
        if (visible) count++;
      });
      filters.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.filter === state.filter)));
      shortcuts.forEach(button => button.setAttribute("aria-pressed", String(normalize(button.dataset.projectQuery) === normalize(state.query) && state.filter === "all")));
      status.textContent = spanish ? count + " de " + cards.length + " medios" : count + " of " + cards.length + " items";
      empty.hidden = count !== 0;
      reset.disabled = !state.query && state.filter === "all";
      const hash = mediaViewHash(state.query, state.filter);
      permalink.href = hash;
      if (write && location.hash !== hash) history[push ? "pushState" : "replaceState"](null, "", hash);
    };
    search.addEventListener("input", () => { state.query = search.value.slice(0, 120); render(true); });
    filters.forEach(button => button.addEventListener("click", () => { state.filter = button.dataset.filter; render(true, true); }));
    shortcuts.forEach(button => button.addEventListener("click", () => {
      state = { query: button.dataset.projectQuery, filter: "all" };
      search.value = state.query;
      render(true, true);
    }));
    reset.addEventListener("click", () => {
      state = { query: "", filter: "all" }; search.value = ""; render(true, true); search.focus();
    });
    const restore = () => { state = readMediaView(location.hash, allowed); search.value = state.query; render(); };
    window.addEventListener("popstate", restore);
    window.addEventListener("hashchange", restore);
    render();
    if (location.hash.startsWith("#media?")) requestAnimationFrame(() => section.scrollIntoView({ behavior: "instant" }));
    // Only the independently reviewed catalogue is read. No research directory, remote image or embed is loaded.
    fetch("inbox/media/catalog.json").then(response => {
      if (!response.ok) throw new Error("catalogue unavailable");
      return response.json();
    }).then(catalog => {
      const byId = new Map(catalog.items.map(item => [item.id, item]));
      cards.forEach(card => {
        const item = byId.get(card.dataset.mediaId);
        if (!item) return;
        const details = document.createElement("details");
        details.className = "source-details";
        const summary = document.createElement("summary");
        summary.textContent = spanish ? "Fuente y contexto" : "Source & context";
        details.append(summary);
        const rows = [
          [spanish ? "Fuente" : "Source", item.publisher || (item.source_url ? new URL(item.source_url).hostname : (spanish ? "Fotografía aportada" : "User-supplied photograph"))],
          [spanish ? "Fecha de la fuente" : "Source date", item.published_at || (spanish ? "No indicada" : "Not supplied")],
          [spanish ? "Uso" : "Use", item.local_path ? (spanish ? "Aportada para este sitio; no es una licencia de redistribución." : "Supplied for this website; not a redistribution license.") : (spanish ? "Enlace al original. No se copia el material." : "Link to the original. Media is not copied.")]
        ];
        const list = document.createElement("dl");
        rows.forEach(([label, value]) => {
          const term = document.createElement("dt"), description = document.createElement("dd");
          term.textContent = label; description.textContent = value; list.append(term, description);
        });
        details.append(list);
        if (item.source_url && new URL(item.source_url).protocol === "https:") {
          const link = document.createElement("a");
          link.href = item.source_url; link.textContent = spanish ? "Abrir la fuente original ↗" : "Open original source ↗";
          details.append(link);
        }
        card.append(details);
      });
    }).catch(() => {
      const note = section.querySelector("[data-source-note]");
      if (note) note.textContent = spanish ? "El catálogo no se pudo cargar. Los enlaces originales siguen disponibles." : "Catalogue details could not load. Original source links still work.";
    });
  }
}
