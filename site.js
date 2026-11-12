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
  banking: [
    "banking",
    "banca",
    "fintech",
    "finance",
    "santander",
    "amex",
    "american express",
    "galicia",
    "bbva",
    "citi",
  ],
  infra: [
    "infra",
    "infrastructure",
    "systems",
    "sistemas",
    "cluster",
    "pflops",
    "rdma",
    "gpu",
    "sip",
    "voip",
    "telephony",
    "bare metal",
  ],
  hardware: [
    "hardware",
    "robotics",
    "robotica",
    "drones",
    "naval",
    "vessel",
    "hull",
    "watercraft",
  ],
  "non-profit": [
    "non profit",
    "non-profit",
    "ngo",
    "ong",
    "inkua",
    "civic",
    "teleton",
    "setoff",
    "volunteers",
  ],
  "coca-cola": [
    "coca cola",
    "coca-cola",
    "christmas",
    "navidad",
    "xmas",
    "santa",
    "papa noel",
    "holiday",
  ],
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

  // 20-Picture Pass-Through Gallery, Theater & Unified Search/Filter
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
      thumbsStrip = theater.querySelector(".theater-thumbs-strip"),
      thumbs = [...theater.querySelectorAll(".theater-thumb")],
      cards = [...document.querySelectorAll(".project-card")],
      filterBtns = [...document.querySelectorAll("[data-project-filter]")],
      searchInput = document.querySelector("#media-search"),
      statusEl = document.querySelector(".result-count");

    let currentIndex = 0;
    let activeFilter = "all";
    const slides = thumbs.map((btn, i) => {
      const card = cards[i];
      const rawTags = [
        card ? card.dataset.category : "",
        ...(card && card.dataset.tags ? card.dataset.tags.split(/\s+/) : []),
      ].filter(Boolean);
      const tags = [...new Set(rawTags)];
      const text = [
        btn.dataset.title || "",
        btn.dataset.desc || "",
        btn.dataset.category || "",
        btn.dataset.proof || "",
        card ? card.textContent : "",
      ].join(" ");
      return {
        src: btn.dataset.src,
        alt: btn.dataset.alt,
        width: btn.dataset.width,
        height: btn.dataset.height,
        title: btn.dataset.title,
        desc: btn.dataset.desc,
        category: btn.dataset.category,
        proof: btn.dataset.proof,
        number: btn.dataset.number,
        tags,
        text,
      };
    });

    let visibleIndices = slides.map((_, i) => i);

    function showSlide(index) {
      if (!slides.length) return;
      if (index < 0) index = slides.length - 1;
      if (index >= slides.length) index = 0;
      currentIndex = index;
      const s = slides[currentIndex];

      if (mainImg) {
        mainImg.style.opacity = "0.72";
        setTimeout(() => {
          mainImg.src = s.src;
          mainImg.alt = s.alt;
          mainImg.width = s.width;
          mainImg.height = s.height;
          mainImg.style.opacity = "1";
        }, 70);
      }
      if (counter) counter.textContent = `${s.number} / ${slides.length}`;
      if (titleEl) titleEl.textContent = s.title;
      if (descEl) descEl.textContent = s.desc;
      if (categoryEl) categoryEl.textContent = s.category;
      if (proofEl) proofEl.textContent = s.proof;

      thumbs.forEach((th, i) => {
        const isActive = i === currentIndex;
        th.setAttribute("aria-current", String(isActive));
        if (isActive && thumbsStrip) {
          const targetLeft =
            th.offsetLeft - thumbsStrip.clientWidth / 2 + th.clientWidth / 2;
          thumbsStrip.scrollTo({
            left: Math.max(0, targetLeft),
            behavior: "smooth",
          });
        }
      });

      cards.forEach((c, i) => {
        const isActive = i === currentIndex;
        c.classList.toggle("is-active", isActive);
        c.setAttribute("aria-current", String(isActive));
      });
    }

    function stepSlide(delta) {
      const pool = visibleIndices.length
        ? visibleIndices
        : slides.map((_, i) => i);
      const pos = pool.indexOf(currentIndex);
      if (pos === -1) {
        showSlide(pool[0]);
      } else {
        const nextPos = (pos + delta + pool.length) % pool.length;
        showSlide(pool[nextPos]);
      }
    }

    function applyFilters() {
      const query = searchInput ? searchInput.value : "";
      visibleIndices = [];
      slides.forEach((slide, i) => {
        const visible = matchesMedia(
          { tags: slide.tags, text: slide.text },
          query,
          activeFilter,
        );
        if (cards[i]) cards[i].hidden = !visible;
        if (thumbs[i]) thumbs[i].hidden = !visible;
        if (visible) visibleIndices.push(i);
      });

      if (statusEl) {
        if (!query.trim() && activeFilter === "all") {
          statusEl.textContent = `Showing all ${slides.length} verified artifacts`;
        } else if (visibleIndices.length === 0) {
          statusEl.textContent =
            "0 matching artifacts — clear filter or select All 20";
        } else {
          statusEl.textContent = `Showing ${visibleIndices.length} of ${slides.length} verified artifacts`;
        }
      }

      if (
        visibleIndices.length > 0 &&
        !visibleIndices.includes(currentIndex)
      ) {
        showSlide(visibleIndices[0]);
      }
    }

    if (prevBtn) prevBtn.addEventListener("click", () => stepSlide(-1));
    if (nextBtn) nextBtn.addEventListener("click", () => stepSlide(1));

    thumbs.forEach((th, i) => {
      th.addEventListener("click", () => showSlide(i));
    });

    cards.forEach((c, i) => {
      c.addEventListener("click", () => {
        showSlide(i);
        theater.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });

    document.addEventListener("keydown", (e) => {
      const activeTag = document.activeElement
        ? document.activeElement.tagName
        : "";
      if (activeTag === "INPUT" || activeTag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") {
        stepSlide(-1);
      } else if (e.key === "ArrowRight") {
        stepSlide(1);
      }
    });

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
            stepSlide(1);
          } else if (touchEndX - touchStartX > 45) {
            stepSlide(-1);
          }
        },
        { passive: true },
      );
    }

    if (filterBtns.length) {
      filterBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          activeFilter = btn.dataset.projectFilter || "all";
          filterBtns.forEach((b) =>
            b.setAttribute("aria-pressed", String(b === btn)),
          );
          applyFilters();
        });
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
    }

    showSlide(0);
    applyFilters();
  }

  // 5-Second Technical Demo Warning Modal with Case-Insensitive "demo" Dismiss
  function initDemoModal() {
    try {
      if (sessionStorage.getItem("frank_demo_dismissed") === "1") return;
    } catch (e) {}

    setTimeout(() => {
      try {
        if (sessionStorage.getItem("frank_demo_dismissed") === "1") return;
      } catch (e) {}
      if (document.getElementById("demo-modal-overlay")) return;

      const overlay = document.createElement("div");
      overlay.id = "demo-modal-overlay";
      overlay.className = "demo-modal-overlay";
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");
      overlay.setAttribute("aria-labelledby", "demo-modal-title");

      overlay.innerHTML = `
        <div class="demo-modal-dialog">
          <div class="demo-modal-header">
            <span class="demo-blinker">ATTENTION!!!</span>
            <span class="demo-badge-meta">[Technical Demo // Multi-Agent Sandbox]</span>
          </div>
          <h2 id="demo-modal-title">Agentic AI Experiment</h2>
          <p>
            This <strong>live technical demo</strong> shows how autonomous AI agents sort unstructured data, curate photography, and build production websites without human input.
          </p>
          <div class="demo-modal-callout">
            <strong>Active PII &amp; Agent Safety Research:</strong><br />
            This experiment processes Frank Escudero&rsquo;s real private data across thousands of agent runs tasked with withholding PII. In an empirical stress-test, boundary leaks will occur—and are actively measured to evaluate agent risk, impact, and containment.
          </div>
          <p>
            More than a portfolio, this benchmark proves modern multi-agent systems can run <strong>100% home-based, low-footprint, powerful, and completely free</strong>.
          </p>
          <div class="demo-dismiss-container">
            <label for="demo-unlock-input" class="demo-input-label">Type <code>demo</code> (case-insensitive) to dismiss and explore:</label>
            <div class="demo-input-group">
              <input type="text" id="demo-unlock-input" class="demo-unlock-input" placeholder="Type &quot;demo&quot; to dismiss..." spellcheck="false" autocomplete="off" />
              <button type="button" id="demo-unlock-btn" class="demo-unlock-btn">Unlock &amp; Dismiss ↗</button>
            </div>
            <div id="demo-input-error" class="demo-input-error" role="alert">Please type &ldquo;demo&rdquo; (e.g. demo, DEMO, DEmO) to dismiss.</div>
          </div>
        </div>
      `;

      document.body.appendChild(overlay);

      requestAnimationFrame(() => {
        overlay.classList.add("is-visible");
      });

      const input = overlay.querySelector("#demo-unlock-input");
      const btn = overlay.querySelector("#demo-unlock-btn");
      const err = overlay.querySelector("#demo-input-error");

      function dismiss() {
        if (!input) return;
        const val = input.value.trim().toLowerCase();
        if (val === "demo") {
          try {
            sessionStorage.setItem("frank_demo_dismissed", "1");
          } catch (e) {}
          overlay.classList.remove("is-visible");
          setTimeout(() => {
            if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
          }, 300);
        } else {
          err.style.display = "block";
          input.classList.add("input-shake");
          setTimeout(() => input.classList.remove("input-shake"), 400);
          input.focus();
        }
      }

      btn.addEventListener("click", dismiss);
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          dismiss();
        }
      });

      setTimeout(() => {
        try {
          input.focus();
        } catch (e) {}
      }, 100);
    }, 5000);
  }

  initDemoModal();
}
