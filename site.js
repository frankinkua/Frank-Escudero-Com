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
  personal: ["personal", "dog", "perro", "sonrisa", "smile"],
  video: ["video", "videos", "charla", "charlas", "talk", "talks", "youtube"],
  "creative-technology": [
    "creative technology",
    "creative-technology",
    "tecnologia",
    "technology",
    "personalizacion",
    "personalization",
  ],
  "social-impact": [
    "social impact",
    "social-impact",
    "impacto social",
    "humanitarian",
    "humanitario",
  ],
  community: ["community", "comunidad", "comunidades", "encuentro"],
  inclusion: ["inclusion", "inclusión", "incluir", "puentes", "bridges"],
  poverty: ["poverty", "pobreza"],
  music: ["music", "musica", "música", "piano"],
  press: ["press", "prensa", "interview", "entrevista"],
  entrepreneurship: [
    "entrepreneurship",
    "emprendimiento",
    "founder",
    "fundador",
  ],
  cybersecurity: ["cybersecurity", "ciberseguridad", "security"],
  energy: ["energy", "energia", "solar", "balcony", "balcon"],
  robotics: ["robotics", "robotica", "robótica", "3d printing", "impresion 3d"],
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
}
