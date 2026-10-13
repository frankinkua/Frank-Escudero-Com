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
  const show = document.querySelector(".highlights");
  if (show) {
    const track = show.querySelector(".slide-track"),
      slides = [...track.children],
      dotsBox = show.querySelector(".slide-dots"),
      count = show.querySelector(".slide-count"),
      play = show.querySelector(".slide-play"),
      reduce = window.matchMedia("(prefers-reduced-motion: reduce)"),
      live = document.createElement("p");
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    show.append(live);
    let index = 0,
      playing = !reduce.matches,
      held = false,
      onScreen = false,
      timer = null;
    const dots = slides.map((slide, i) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.setAttribute("aria-label", "Slide " + (i + 1) + ": " + slide.querySelector("h3").textContent);
      dot.addEventListener("click", () => {
        stop();
        go(i, true);
      });
      dotsBox.append(dot);
      return dot;
    });
    const step = () =>
      slides.length > 1 ? slides[1].offsetLeft - slides[0].offsetLeft : 1;
    const mark = (i) => {
      index = i;
      dots.forEach((dot, d) => dot.setAttribute("aria-current", String(d === i)));
      count.textContent = i + 1 + " / " + slides.length;
    };
    const go = (i, announce) => {
      i = (i + slides.length) % slides.length;
      track.scrollTo({
        left: i * step(),
        behavior: reduce.matches ? "auto" : "smooth",
      });
      mark(i);
      if (announce)
        live.textContent =
          "Slide " + (i + 1) + " of " + slides.length + ": " + slides[i].querySelector("h3").textContent;
    };
    const tick = () => {
      clearInterval(timer);
      timer =
        playing && !held && onScreen && !document.hidden
          ? setInterval(() => go(index + 1, false), 7000)
          : null;
    };
    const setPlaying = (on) => {
      playing = on;
      play.textContent = on ? "Pause" : "Play";
      play.setAttribute("aria-label", on ? "Pause slideshow" : "Play slideshow");
      tick();
    };
    const stop = () => setPlaying(false);
    play.addEventListener("click", () => setPlaying(!playing));
    show.querySelector(".slide-prev").addEventListener("click", () => {
      stop();
      go(index - 1, true);
    });
    show.querySelector(".slide-next").addEventListener("click", () => {
      stop();
      go(index + 1, true);
    });
    show.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      stop();
      go(index + (e.key === "ArrowRight" ? 1 : -1), true);
    });
    track.addEventListener("pointerdown", stop);
    track.addEventListener("wheel", (e) => {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) stop();
    }, { passive: true });
    let queued = false;
    track.addEventListener("scroll", () => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(() => {
        queued = false;
        const i = Math.round(track.scrollLeft / step());
        if (i !== index && i >= 0 && i < slides.length) mark(i);
      });
    }, { passive: true });
    const hold = (on) => {
      held = on;
      tick();
    };
    show.addEventListener("pointerenter", () => hold(true));
    show.addEventListener("pointerleave", () => hold(show.contains(document.activeElement)));
    show.addEventListener("focusin", () => hold(true));
    show.addEventListener("focusout", (e) => {
      if (!show.contains(e.relatedTarget)) hold(false);
    });
    document.addEventListener("visibilitychange", tick);
    reduce.addEventListener("change", () => setPlaying(!reduce.matches && playing));
    if ("IntersectionObserver" in window)
      new IntersectionObserver((entries) => {
        onScreen = entries[0].isIntersecting;
        tick();
      }, { threshold: 0.5 }).observe(track);
    else onScreen = true;
    mark(0);
    setPlaying(playing);
  }
  const journey = document.querySelector(".journey");
  if (journey) {
    const steps = [...document.querySelectorAll(".story-step")],
      label = document.querySelector("#scene-label"),
      reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    let queued = false;
    const update = () => {
      queued = false;
      if (reduce.matches) {
        journey.dataset.scene = "0";
        journey.style.setProperty("--progress", "0");
        label.textContent = steps[0].querySelector(".chapter").textContent;
        return;
      }
      const focus =
        window.innerWidth <= 700
          ? Math.min(window.innerHeight * 0.75, window.innerHeight - 50)
          : window.innerHeight * 0.55;
      let active = 0;
      steps.forEach((step, index) => {
        if (step.getBoundingClientRect().top <= focus) active = index;
      });
      journey.dataset.scene = String(active);
      journey.style.setProperty(
        "--progress",
        String(active / (steps.length - 1)),
      );
      label.textContent = steps[active].querySelector(".chapter").textContent;
    };
    const queue = () => {
      if (!queued) {
        queued = true;
        window.requestAnimationFrame(update);
      }
    };
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    reduce.addEventListener("change", queue);
    update();
  }
}
