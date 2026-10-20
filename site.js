"use strict";
const tagAliases = {
  portrait: [
    "portrait",
    "portraits",
    "retrato",
    "retratos",
    "foto",
    "photo",
    "fotografia",
  ],
  personal: [
    "personal",
    "dog",
    "perro",
    "sonrisa",
    "smile",
    "horse",
    "caballo",
  ],
  video: [
    "video",
    "videos",
    "charla",
    "charlas",
    "talk",
    "talks",
    "youtube",
    "studio",
    "campaign",
  ],
  "creative-technology": [
    "creative technology",
    "creative-technology",
    "tecnologia",
    "technology",
    "personalizacion",
    "personalization",
    "ai",
    "analytics",
    "saas",
    "telemetry",
    "dashboard",
  ],
  "social-impact": [
    "social impact",
    "social-impact",
    "impacto social",
    "humanitarian",
    "humanitario",
  ],
  community: [
    "community",
    "comunidad",
    "comunidades",
    "encuentro",
    "brussels",
    "parliament",
    "workshop",
  ],
  inclusion: ["inclusion", "inclusión", "incluir", "puentes", "bridges"],
  poverty: ["poverty", "pobreza"],
  music: ["music", "musica", "música", "piano"],
  press: ["press", "prensa", "interview", "entrevista"],
  entrepreneurship: [
    "entrepreneurship",
    "emprendimiento",
    "founder",
    "fundador",
    "frankfurt",
    "speaking",
    "stage",
    "keynote",
  ],
  cybersecurity: ["cybersecurity", "ciberseguridad", "security", "setoff"],
  energy: ["energy", "energia", "solar", "balcony", "balcon"],
  robotics: [
    "robotics",
    "robotica",
    "robótica",
    "3d printing",
    "impresion 3d",
    "drones",
    "drone",
    "naval",
    "maritime",
    "hardware",
    "autonomous",
    "vessel",
  ],
  medtech: ["medtech", "medical technology", "tecnologia medica"],
};
const normalize = (value) =>
  String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[-_]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
function matchesMedia(item, query, filter = "all") {
  const tags = item.tags || [];
  const haystack = normalize(
    [item.text || "", ...tags.flatMap((tag) => tagAliases[tag] || [tag])].join(
      " ",
    ),
  );
  return (
    (filter === "all" || tags.includes(filter)) &&
    normalize(query)
      .split(" ")
      .filter(Boolean)
      .every((word) => haystack.includes(word))
  );
}
if (typeof module !== "undefined")
  module.exports = { normalize, matchesMedia, tagAliases };
if (typeof document !== "undefined") {
  document.documentElement.classList.add("js");
  const menu = document.querySelector(".menu-toggle"),
    nav = document.querySelector("#navigation");
  if (menu && nav) {
    const closeMenu = () => {
      menu.setAttribute("aria-expanded", "false");
      nav.classList.remove("is-open");
    };
    menu.addEventListener("click", () => {
      const open = menu.getAttribute("aria-expanded") !== "true";
      menu.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
    nav.addEventListener("click", (e) => {
      if (e.target.closest("a")) closeMenu();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && menu.getAttribute("aria-expanded") === "true") {
        closeMenu();
        menu.focus();
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".header-inner")) closeMenu();
    });
    window
      .matchMedia("(min-width: 701px)")
      .addEventListener("change", closeMenu);
  }
  const projectCards = [
      ...document.querySelectorAll(".project-card[data-category]"),
    ],
    projectButtons = [...document.querySelectorAll("[data-project-filter]")];
  if (projectCards.length && projectButtons.length) {
    projectButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const selected = button.dataset.projectFilter;
        projectButtons.forEach((b) =>
          b.setAttribute("aria-pressed", String(b === button)),
        );
        projectCards.forEach((card) => {
          const cats = (card.dataset.category || "").split(" ");
          card.hidden = selected !== "all" && !cats.includes(selected);
        });
      });
    });
  }
  const cards = [...document.querySelectorAll(".media-card[data-tags]")],
    search = document.querySelector("#media-search");
  const filters = [...document.querySelectorAll("[data-filter]")],
    status = document.querySelector(".result-count"),
    empty = document.querySelector(".no-results");
  if (search && cards.length) {
    let filter = "all";
    const render = () => {
      let count = 0;
      cards.forEach((card) => {
        const visible = matchesMedia(
          { tags: card.dataset.tags.split(" "), text: card.textContent },
          search.value,
          filter,
        );
        card.hidden = !visible;
        if (visible) count++;
      });
      if (status)
        status.textContent =
          document.documentElement.lang === "es"
            ? count + " de " + cards.length + " medios"
            : count + " of " + cards.length + " items";
      if (empty) empty.hidden = count !== 0;
    };
    search.addEventListener("input", render);
    filters.forEach((button) =>
      button.addEventListener("click", () => {
        filter = button.dataset.filter;
        filters.forEach((b) =>
          b.setAttribute("aria-pressed", String(b === button)),
        );
        render();
      }),
    );
    render();
  }
}
