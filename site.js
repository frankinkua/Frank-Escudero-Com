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

  // 30-Picture Pass-Through Gallery & Theater
  const theater = document.querySelector(".gallery-theater");
  if (theater) {
    const mainImg = theater.querySelector(".theater-main-img"),
      counter = theater.querySelector(".theater-counter"),
      titleEl = theater.querySelector(".theater-title"),
      descEl = theater.querySelector(".theater-desc"),
      categoryEl = theater.querySelector(".theater-category"),
      proofEl = theater.querySelector(".theater-proof"),
      prevBtn = theater.querySelector(".theater-prev"),
      nextBtn = theater.querySelector(".theater-next"),
      thumbs = [...theater.querySelectorAll(".theater-thumb")],
      cards = [...document.querySelectorAll(".project-card")],
      filterBtns = [...document.querySelectorAll("[data-project-filter]")];

    let currentIndex = 0;
    const slides = thumbs.map((btn) => ({
      src: btn.dataset.src,
      alt: btn.dataset.alt,
      width: btn.dataset.width,
      height: btn.dataset.height,
      title: btn.dataset.title,
      desc: btn.dataset.desc,
      category: btn.dataset.category,
      proof: btn.dataset.proof,
      number: btn.dataset.number,
    }));

    function showSlide(index) {
      if (!slides.length) return;
      if (index < 0) index = slides.length - 1;
      if (index >= slides.length) index = 0;
      currentIndex = index;
      const s = slides[currentIndex];

      if (mainImg) {
        mainImg.style.opacity = "0.7";
        setTimeout(() => {
          mainImg.src = s.src;
          mainImg.alt = s.alt;
          mainImg.width = s.width;
          mainImg.height = s.height;
          mainImg.style.opacity = "1";
        }, 80);
      }
      if (counter) counter.textContent = `${s.number} / ${slides.length}`;
      if (titleEl) titleEl.textContent = s.title;
      if (descEl) descEl.textContent = s.desc;
      if (categoryEl) categoryEl.textContent = s.category;
      if (proofEl) proofEl.textContent = s.proof;

      thumbs.forEach((th, i) => {
        const isActive = i === currentIndex;
        th.setAttribute("aria-current", String(isActive));
        if (isActive) {
          th.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
            inline: "center",
          });
        }
      });
    }

    if (prevBtn) prevBtn.addEventListener("click", () => showSlide(currentIndex - 1));
    if (nextBtn) nextBtn.addEventListener("click", () => showSlide(currentIndex + 1));

    thumbs.forEach((th, i) => {
      th.addEventListener("click", () => showSlide(i));
    });

    // Keyboard navigation when user is looking at gallery or page
    document.addEventListener("keydown", (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName : "";
      if (activeTag === "INPUT" || activeTag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") {
        showSlide(currentIndex - 1);
      } else if (e.key === "ArrowRight") {
        showSlide(currentIndex + 1);
      }
    });

    // Simple touch swipe for theater
    let touchStartX = 0;
    const stage = theater.querySelector(".theater-stage");
    if (stage) {
      stage.addEventListener(
        "touchstart",
        (e) => {
          touchStartX = e.changedTouches[0].clientX;
        },
        { passive: true },
      );
      stage.addEventListener(
        "touchend",
        (e) => {
          const touchEndX = e.changedTouches[0].clientX;
          if (touchStartX - touchEndX > 45) {
            showSlide(currentIndex + 1);
          } else if (touchEndX - touchStartX > 45) {
            showSlide(currentIndex - 1);
          }
        },
        { passive: true },
      );
    }

    // Category filter for both cards and thumbs
    if (filterBtns.length) {
      filterBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          const filter = btn.dataset.projectFilter;
          filterBtns.forEach((b) =>
            b.setAttribute("aria-pressed", String(b === btn)),
          );
          cards.forEach((card) => {
            const cats = (card.dataset.category || "").split(" ");
            card.hidden = filter !== "all" && !cats.includes(filter);
          });
          thumbs.forEach((thumb) => {
            const cats = (thumb.dataset.category || "").toLowerCase();
            thumb.hidden = filter !== "all" && !cats.includes(filter);
          });
        });
      });
    }

    // Initialize first slide
    showSlide(0);
  }

  // Media Search & Filter in #media section
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
