"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const backendHtmlPath = path.join(root, "backend/index.html");
const rootHtmlPath = path.join(root, "index.html");
const siteJsPath = path.join(root, "site.js");
const stylesCssPath = path.join(root, "styles.css");
const catalogPath = path.join(root, "inbox/media/catalog.json");
const imagesDir = path.join(root, "inbox/media/images");

const backendHtml = fs.readFileSync(backendHtmlPath, "utf8");
const siteJsContent = fs.readFileSync(siteJsPath, "utf8");
const stylesCssContent = fs.readFileSync(stylesCssPath, "utf8");
const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
const core = require(siteJsPath);

// Helper parsers for DOM inspection
function parseThumbs(html) {
  const thumbsBlock = html.match(
    /<div class="theater-thumbs"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/,
  );
  if (!thumbsBlock) return [];
  const matches = [
    ...thumbsBlock[1].matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g),
  ];
  return matches.map(([, attrs, inner]) => {
    const getAttr = (name) => {
      const m = attrs.match(new RegExp(`${name}="([^"]*)"`, "i"));
      return m ? m[1] : null;
    };
    const spanText = inner.match(/<span>([^<]*)<\/span>/i)?.[1]?.trim();
    const imgMatch = inner.match(/<img\b([^>]*)>/i);
    const getImgAttr = (name) => {
      if (!imgMatch) return null;
      const m = imgMatch[1].match(new RegExp(`${name}="([^"]*)"`, "i"));
      return m ? m[1] : null;
    };
    return {
      src: getAttr("data-src"),
      width: getAttr("data-width"),
      height: getAttr("data-height"),
      title: getAttr("data-title"),
      desc: getAttr("data-desc"),
      category: getAttr("data-category"),
      proof: getAttr("data-proof"),
      number: getAttr("data-number"),
      spanNumber: spanText,
      imgSrc: getImgAttr("src"),
      imgWidth: getImgAttr("width"),
      imgHeight: getImgAttr("height"),
      imgAlt: getImgAttr("alt"),
      imgLoading: getImgAttr("loading"),
    };
  });
}

function parseCards(html) {
  const listBlock = html.match(
    /<ol class="project-list"[^>]*>([\s\S]*?)<\/ol>/,
  );
  if (!listBlock) return [];
  const matches = [...listBlock[1].matchAll(/<li\b([^>]*)>([\s\S]*?)<\/li>/g)];
  return matches.map(([, attrs, inner]) => {
    const getAttr = (name) => {
      const m = attrs.match(new RegExp(`${name}="([^"]*)"`, "i"));
      return m ? m[1] : null;
    };
    const numText = inner
      .match(/class="project-number">([^<]*)<\/span>/i)?.[1]
      ?.trim();
    const titleText = inner.match(/<h3>([^<]*)<\/h3>/i)?.[1]?.trim();
    const proofText = inner
      .match(/class="project-proof">([^<]*)<\/span>/i)?.[1]
      ?.trim();
    const eyebrowText = inner
      .match(/class="eyebrow">([^<]*)<\/span>/i)?.[1]
      ?.trim();
    const imgMatch = inner.match(/<img\b([^>]*)>/i);
    const getImgAttr = (name) => {
      if (!imgMatch) return null;
      const m = imgMatch[1].match(new RegExp(`${name}="([^"]*)"`, "i"));
      return m ? m[1] : null;
    };
    return {
      category: getAttr("data-category"),
      tags: getAttr("data-tags")
        ? getAttr("data-tags").split(/\s+/).filter(Boolean)
        : [],
      number: numText,
      title: titleText,
      proof: proofText,
      eyebrow: eyebrowText,
      imgSrc: getImgAttr("src"),
      imgWidth: getImgAttr("width"),
      imgHeight: getImgAttr("height"),
      imgAlt: getImgAttr("alt"),
      imgLoading: getImgAttr("loading"),
    };
  });
}

function getVisibleNonGalleryWords(html) {
  const withoutProjects = html.replace(
    /<section id="projects"[\s\S]*?<\/section>/,
    "",
  );
  const cleanText = withoutProjects
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<svg[\s\S]*?<\/svg>/gi, " ")
    .replace(/<[^>]+>/g, " ");
  return cleanText.trim().split(/\s+/).filter(Boolean);
}

describe("Tier 1: Feature Coverage (Structural & DOM Synchrony)", () => {
  const thumbs = parseThumbs(backendHtml);
  const cards = parseCards(backendHtml);

  it("has exactly 20 synchronized cases in .theater-thumbs (01 through 20) and .project-list (01 / through 20 /)", () => {
    assert.equal(thumbs.length, 20, "Must have exactly 20 theater thumbs");
    assert.equal(cards.length, 20, "Must have exactly 20 project cards");

    for (let i = 0; i < 20; i++) {
      const expectedNum = String(i + 1).padStart(2, "0");
      assert.equal(
        thumbs[i].number,
        expectedNum,
        `Thumb ${i} data-number should be ${expectedNum}`,
      );
      assert.equal(
        thumbs[i].spanNumber,
        expectedNum,
        `Thumb ${i} span text should be ${expectedNum}`,
      );
      assert.equal(
        cards[i].number,
        `${expectedNum} /`,
        `Card ${i} project-number should be ${expectedNum} /`,
      );
    }
  });

  it("enforces strict 1:1 index coupling between thumbnail i and card i across all metadata", () => {
    const validCategories = [
      "banking",
      "infra",
      "hardware",
      "non-profit",
      "portrait",
    ];

    for (let i = 0; i < 20; i++) {
      const th = thumbs[i];
      const cd = cards[i];

      // Exact media attributes
      assert.ok(th.src, `Thumb ${i} must have data-src`);
      assert.equal(
        th.src,
        cd.imgSrc,
        `Index ${i}: thumb data-src must match card img src`,
      );
      assert.equal(
        th.imgSrc,
        cd.imgSrc,
        `Index ${i}: thumb img src must match card img src`,
      );
      assert.equal(
        th.width,
        cd.imgWidth,
        `Index ${i}: thumb data-width must match card img width`,
      );
      assert.equal(
        th.height,
        cd.imgHeight,
        `Index ${i}: thumb data-height must match card img height`,
      );

      // Number coupling
      assert.equal(
        cd.number.replace(/\s*\/\s*$/, ""),
        th.number,
        `Index ${i}: card number must match thumb data-number`,
      );

      // Title coupling
      assert.ok(th.title, `Thumb ${i} must have data-title`);
      assert.equal(
        th.title,
        cd.title,
        `Index ${i}: thumb data-title must match card title`,
      );

      // Category validity
      assert.ok(
        validCategories.includes(cd.category),
        `Index ${i}: card category '${cd.category}' must be in ${validCategories.join(", ")}`,
      );

      // Category domain alignment between thumb and card
      if (cd.category === "infra") {
        assert.match(
          th.category,
          /Systems\s+&amp;\s+Infra/i,
          `Index ${i}: infra card category mismatch in thumb`,
        );
      } else if (cd.category === "hardware") {
        assert.match(
          th.category,
          /Robotics\s+&amp;\s+Hardware/i,
          `Index ${i}: hardware card category mismatch in thumb`,
        );
      } else if (cd.category === "non-profit") {
        assert.match(
          th.category,
          /Non-Profit\s+&amp;\s+Civic/i,
          `Index ${i}: non-profit card category mismatch in thumb`,
        );
      } else if (cd.category === "portrait") {
        assert.match(
          th.category,
          /Who\s+is\s+Frank\?/i,
          `Index ${i}: portrait card category mismatch in thumb`,
        );
      } else if (cd.category === "banking") {
        assert.match(
          th.category,
          /Flagship Global Scale|Creative Scale|Banking &amp; Scale|Automotive &amp; Finance/i,
          `Index ${i}: banking card category mismatch in thumb`,
        );
      }

      // Image lazy-loading and alt text integrity
      assert.equal(
        th.imgLoading,
        "lazy",
        `Thumb ${i} img must be loading="lazy"`,
      );
      assert.equal(
        cd.imgLoading,
        "lazy",
        `Card ${i} img must be loading="lazy"`,
      );
      assert.ok(
        th.imgAlt && th.imgAlt.length > 5,
        `Thumb ${i} must have meaningful alt text`,
      );
      assert.ok(
        cd.imgAlt && cd.imgAlt.length > 5,
        `Card ${i} must have meaningful alt text`,
      );
    }
  });

  it("provides filter pills for all categories with >0 matching cards per category", () => {
    const filterMatches = [
      ...backendHtml.matchAll(/data-project-filter="([^"]+)"/g),
    ].map((m) => m[1]);
    const expectedFilters = [
      "all",
      "banking",
      "infra",
      "hardware",
      "non-profit",
      "portrait",
    ];

    for (const f of expectedFilters) {
      assert.ok(
        filterMatches.includes(f),
        `Missing filter button for category: ${f}`,
      );
    }

    const categoryCounts = {};
    for (const cat of [
      "banking",
      "infra",
      "hardware",
      "non-profit",
      "portrait",
    ]) {
      const matching = cards.filter((c) => c.category === cat);
      assert.ok(
        matching.length > 0,
        `Category '${cat}' must have at least 1 card`,
      );
      categoryCounts[cat] = matching.length;
    }

    const totalCategorized = Object.values(categoryCounts).reduce(
      (a, b) => a + b,
      0,
    );
    assert.equal(
      totalCategorized,
      20,
      "Sum of categorized cards must equal exactly 20",
    );
  });

  it("contains zero-match fallback search string in site.js referencing 'All 20'", () => {
    assert.match(
      siteJsContent,
      /0 matching artifacts — clear filter or select All 20/,
      "site.js must include the zero-match fallback message referencing 'All 20'",
    );
  });

  it("verifies site.js interactive filter and search behavior against curated items", () => {
    assert.ok(core.matchesMedia, "site.js must export matchesMedia");
    assert.ok(core.normalize, "site.js must export normalize");

    // Search query matching specific cases
    const case1 = {
      tags: cards[0].tags,
      text: `${thumbs[0].title} ${thumbs[0].desc} ${cards[0].proof}`,
    };
    assert.ok(
      core.matchesMedia(case1, "coca-cola"),
      "matchesMedia should match 'coca-cola'",
    );
    assert.ok(
      core.matchesMedia(case1, "christmas"),
      "matchesMedia should match 'christmas'",
    );
    assert.ok(
      core.matchesMedia(case1, "", "banking"),
      "matchesMedia should match 'banking' filter",
    );
    assert.ok(
      !core.matchesMedia(case1, "", "infra"),
      "matchesMedia should not match 'infra' filter for banking item",
    );

    // AI cluster matching
    const aiIdx = cards.findIndex((c) => c.imgSrc.includes("ai-cluster-fabric"));
    assert.ok(aiIdx >= 0, "ai-cluster-fabric case must exist");
    const aiCase = {
      tags: cards[aiIdx].tags,
      text: `${thumbs[aiIdx].title} ${thumbs[aiIdx].desc} ${cards[aiIdx].proof}`,
    };
    assert.ok(
      core.matchesMedia(aiCase, "pflops"),
      "matchesMedia should match 'pflops'",
    );
    assert.ok(
      core.matchesMedia(aiCase, "rdma"),
      "matchesMedia should match 'rdma'",
    );
    assert.ok(
      core.matchesMedia(aiCase, "", "infra"),
      "matchesMedia should match 'infra' filter",
    );

    // Accent insensitivity and multilingual aliases
    assert.equal(core.normalize("MÚSICA"), "musica");
    assert.equal(core.normalize("Robótica"), "robotica");
    assert.ok(
      core.matchesMedia({ tags: ["portrait"], text: "" }, "retrato"),
      "portrait alias",
    );
    assert.ok(
      core.matchesMedia({ tags: ["hardware"], text: "" }, "robótica"),
      "accented hardware alias",
    );

    // Non-matching query returns false
    assert.ok(
      !core.matchesMedia(case1, "quantum_blockchain_hyperloop"),
      "non-matching query should fail",
    );
  });

  it("verifies responsive CSS layout contracts prevent visual overlap and squashing (M2 contracts)", () => {
    // Desktop 1440px theater caption docking
    assert.match(
      stylesCssContent,
      /\.theater-stage\s*\{[\s\S]*?flex-direction:\s*column/,
      "Theater stage must use flex column to avoid overlaying caption on stage imagery",
    );
    assert.match(
      stylesCssContent,
      /\.theater-caption\s*\{[\s\S]*?position:\s*relative/,
      "Theater caption must be relatively positioned to dock cleanly below stage image",
    );

    // Mobile 390px project-body 2-row layout to prevent proof badge squashing title
    assert.match(
      stylesCssContent,
      /\.project-body\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto/,
      "Project body must use 2-row grid on mobile to prevent title squashing",
    );
    assert.match(
      stylesCssContent,
      /\.project-proof\s*\{[\s\S]*?grid-column:\s*2/,
      "Project proof badge must occupy row 2 beneath title on mobile",
    );
  });
});

describe("Tier 2: Boundary & Corner Cases (Metrics & Mathematics)", () => {
  it("ensures visible non-gallery word count outside #projects is strictly within [770, 835]", () => {
    const words = getVisibleNonGalleryWords(backendHtml);
    const count = words.length;
    assert.ok(
      count >= 770,
      `Word count ${count} is below minimum bound of 770 words`,
    );
    assert.ok(
      count <= 835,
      `Word count ${count} exceeds maximum bound of 835 words`,
    );
  });

  it("ensures average data-desc length across the 20 cases is strictly within [14.5, 17.0]", () => {
    const thumbs = parseThumbs(backendHtml);
    assert.equal(thumbs.length, 20);

    let totalWords = 0;
    for (let i = 0; i < 20; i++) {
      const desc = thumbs[i].desc;
      assert.ok(desc && desc.trim().length > 0, `Thumb ${i} missing data-desc`);
      const words = desc.trim().split(/\s+/).filter(Boolean);
      assert.ok(
        words.length >= 8,
        `Thumb ${i} description too brief: ${words.length} words`,
      );
      assert.ok(
        words.length <= 25,
        `Thumb ${i} description too verbose: ${words.length} words`,
      );
      totalWords += words.length;
    }

    const average = totalWords / 20;
    assert.ok(
      average >= 14.5,
      `Average data-desc length ${average.toFixed(2)} is below minimum bound of 14.5 words/case`,
    );
    assert.ok(
      average <= 17.0,
      `Average data-desc length ${average.toFixed(2)} exceeds maximum bound of 17.0 words/case`,
    );
  });

  it("ensures root index.html is strictly 381 bytes and remains a blank placeholder", () => {
    const stats = fs.statSync(rootHtmlPath);
    assert.equal(
      stats.size,
      381,
      `Root index.html must be exactly 381 bytes, but found ${stats.size}`,
    );

    const rootContent = fs.readFileSync(rootHtmlPath, "utf8");
    assert.match(
      rootContent,
      /<title>Frank Escudero<\/title>/i,
      "Root index.html should have expected title",
    );
    assert.match(
      rootContent,
      /<body>\s*<\/body>/,
      "Root index.html should have an empty body (permanent blank placeholder)",
    );
    assert.doesNotMatch(
      rootContent,
      /<section id="projects"/,
      "Root index.html must not contain portfolio sections",
    );
  });

  it("verifies zero stale '30' labels across HTML, JS, and CSS", () => {
    const staleRegex =
      /(\b30[- ]?(artifact|picture|item|verified)|select all 30|index 01[–-]30|all 30|\/ 30\b)/i;

    const filesToCheck = [
      { path: backendHtmlPath, name: "backend/index.html" },
      { path: siteJsPath, name: "site.js" },
      { path: stylesCssPath, name: "styles.css" },
    ];

    for (const { path: filePath, name } of filesToCheck) {
      const content = fs.readFileSync(filePath, "utf8");
      const match = content.match(staleRegex);
      assert.equal(
        match,
        null,
        `Found stale '30' label in ${name}: '${match ? match[0] : ""}'`,
      );
    }
  });
});

describe("Tier 3: Cross-Feature Combinations (Media Uniqueness & Catalog Integrity)", () => {
  it("uses exactly 20 distinct WebP images inside the gallery with zero duplicates", () => {
    const thumbs = parseThumbs(backendHtml);
    const cards = parseCards(backendHtml);

    const thumbWebps = thumbs.map((t) => path.basename(t.src));
    const cardWebps = cards.map((c) => path.basename(c.imgSrc));

    assert.equal(
      new Set(thumbWebps).size,
      20,
      "Gallery thumbs must have 20 distinct WebP images",
    );
    assert.equal(
      new Set(cardWebps).size,
      20,
      "Gallery cards must have 20 distinct WebP images",
    );
    assert.deepEqual(
      thumbWebps,
      cardWebps,
      "Gallery thumbs and cards must reference identical image sequences",
    );
  });

  it("uses exactly 7 distinct WebP images across pre-gallery sections with zero pre-gallery duplication", () => {
    const aboutMatch =
      backendHtml.match(
        /<section[^>]+id="about"[\s\S]*?<\/section>/,
      )?.[0] || "";
    const instMatch =
      backendHtml.match(
        /<section[^>]+id="institutions"[\s\S]*?<\/section>/,
      )?.[0] || "";
    const npMatch =
      backendHtml.match(
        /<section[^>]+id="non-profit"[\s\S]*?<\/section>/,
      )?.[0] || "";

    const preGalleryHtml = aboutMatch + instMatch + npMatch;
    const preGalleryWebps = [
      ...preGalleryHtml.matchAll(/src="([^"]+\.webp)"/g),
    ].map((m) => path.basename(m[1]));

    assert.equal(
      preGalleryWebps.length,
      7,
      "Must have exactly 7 WebP images across pre-gallery sections",
    );
    assert.equal(
      new Set(preGalleryWebps).size,
      7,
      "Pre-gallery images must have zero repetition",
    );

    const expectedPreGallery = [
      "frank-brussels-parliament.webp",
      "frank-speaking-frankfurt.webp",
      "frank-alpine-portrait.webp",
      "coca-cola-christmas-hero.webp",
      "campaign-telephony-dashboard.webp",
      "inkua-workshop-workbook.webp",
      "setoff-brussels-workshop.webp",
    ];
    assert.deepEqual(
      preGalleryWebps,
      expectedPreGallery,
      "Pre-gallery images match expected set",
    );
  });

  it("maintains exactly 22 WebPs on disk in inbox/media/images and 23 items in catalog.json", () => {
    const diskWebps = fs
      .readdirSync(imagesDir)
      .filter((f) => f.endsWith(".webp"));
    assert.equal(
      diskWebps.length,
      22,
      "Must have exactly 22 WebP images on disk in inbox/media/images",
    );
    assert.equal(
      catalog.items.length,
      23,
      "Catalog must contain exactly 23 items",
    );

    const localCatalogItems = catalog.items.filter((it) => it.local_path);
    assert.equal(
      localCatalogItems.length,
      22,
      "Catalog must have exactly 22 local image items",
    );

    const refOnlyItems = catalog.items.filter(
      (it) => it.rights_status === "reference_only",
    );
    assert.equal(
      refOnlyItems.length,
      1,
      "Catalog must have exactly 1 reference_only item",
    );
    assert.equal(refOnlyItems[0].id, "setoff-2023");
  });

  it("verifies cryptographic SHA-256 integrity for every WebP on disk against catalog.json", () => {
    const diskWebps = fs
      .readdirSync(imagesDir)
      .filter((f) => f.endsWith(".webp"));

    for (const file of diskWebps) {
      const relPath = `inbox/media/images/${file}`;
      const buf = fs.readFileSync(path.join(imagesDir, file));
      const hash = crypto.createHash("sha256").update(buf).digest("hex");

      const item = catalog.items.find((it) => it.local_path === relPath);
      assert.ok(item, `File on disk ${file} must have catalog entry`);
      assert.equal(
        hash,
        item.sha256,
        `SHA-256 hash mismatch for ${file}: expected ${item.sha256}, got ${hash}`,
      );
    }
  });

  it("guarantees zero orphaned WebP files (every file on disk is referenced on the website)", () => {
    const diskWebps = fs
      .readdirSync(imagesDir)
      .filter((f) => f.endsWith(".webp"));

    for (const file of diskWebps) {
      assert.ok(
        backendHtml.includes(file),
        `Orphaned WebP on disk not referenced in backend/index.html: ${file}`,
      );
    }
  });

  it("guarantees absence of withdrawn stencil artwork hashes and prohibited portrait identifiers", () => {
    const withdrawnHashes = [
      "93e6963975eff97d555961d84e3253df51333bb4b46197ab23bcbe250cad8ef1",
      "3c9d465ee764613371faa7e0cd1d14ae6214f0d0189401d1885a54196e7797cc",
    ];

    // Check catalog items
    for (const it of catalog.items) {
      assert.ok(
        !withdrawnHashes.includes(it.sha256),
        `Withdrawn stencil hash found in catalog: ${it.sha256}`,
      );
    }

    // Check disk files
    const diskWebps = fs
      .readdirSync(imagesDir)
      .filter((f) => f.endsWith(".webp"));
    for (const file of diskWebps) {
      const buf = fs.readFileSync(path.join(imagesDir, file));
      const hash = crypto.createHash("sha256").update(buf).digest("hex");
      assert.ok(
        !withdrawnHashes.includes(hash),
        `Withdrawn stencil hash on disk in ${file}: ${hash}`,
      );
    }

    // Check prohibited identifiers
    const prohibitedNames = [
      "frank-portrait-studio",
      "frank-inkua-portrait",
      "frank-frankfurt-founders",
      "frank-team-portrait",
      "mobile-metrics-ui",
    ];

    for (const name of prohibitedNames) {
      assert.ok(
        !backendHtml.includes(name),
        `Prohibited name found in backend/index.html: ${name}`,
      );
      assert.ok(
        !diskWebps.some((f) => f.includes(name)),
        `Prohibited file found on disk: ${name}`,
      );
      assert.ok(
        !catalog.items.some(
          (it) => it.id === name || (it.local_path && it.local_path.includes(name)),
        ),
        `Prohibited identifier found in catalog: ${name}`,
      );
    }
  });
});

describe("Tier 4: Real-World Workflow & Build Packaging", () => {
  const dest = path.join(root, "_site");

  it("executes scripts/build.cjs cleanly into _site, verifies asset packaging and exclusions, and removes _site", () => {
    // Ensure clean state before build
    if (fs.existsSync(dest)) {
      fs.rmSync(dest, { recursive: true, force: true });
    }

    try {
      const buildOutput = execSync("node scripts/build.cjs", {
        cwd: root,
        encoding: "utf8",
      });
      assert.match(
        buildOutput,
        /Built approved site files only/,
        "Build script should report clean packaging",
      );

      // Verify required site files exist in _site
      const requiredBuiltFiles = [
        "backend/index.html",
        "styles.css",
        "site.js",
        "index.html",
        "inbox/media/catalog.json",
        "inbox/media/tag-aliases.json",
        ".nojekyll",
      ];
      for (const rel of requiredBuiltFiles) {
        assert.ok(
          fs.existsSync(path.join(dest, rel)),
          `Missing built file in _site: ${rel}`,
        );
      }

      // Verify all 22 approved WebPs are copied to _site
      const builtImagesDir = path.join(dest, "inbox/media/images");
      assert.ok(fs.existsSync(builtImagesDir), "Built images dir must exist");
      const builtWebps = fs
        .readdirSync(builtImagesDir)
        .filter((f) => f.endsWith(".webp"));
      assert.equal(
        builtWebps.length,
        22,
        "_site must contain exactly 22 WebPs",
      );

      // Verify exclusions
      assert.ok(
        !fs.existsSync(path.join(dest, "inbox/Photos-1-001")),
        "Raw Photos-1-001 must NEVER be copied into _site",
      );
      assert.ok(
        !fs.existsSync(path.join(dest, ".agents")),
        "Agent metadata .agents must NEVER be copied into _site",
      );
      assert.ok(
        !fs.existsSync(path.join(dest, ".git")),
        ".git must NEVER be copied into _site",
      );
    } finally {
      // Clean removal of _site
      if (fs.existsSync(dest)) {
        fs.rmSync(dest, { recursive: true, force: true });
      }
      assert.ok(!fs.existsSync(dest), "_site must be cleanly removed");
    }
  });

  it("enforces strict external domain whitelisting to approved hosts only", () => {
    const approvedHosts = new Set([
      "github.com",
      "www.linkedin.com",
      "setoff-project.eu",
    ]);

    const externalUrls = [
      ...backendHtml.matchAll(/\b(?:href|src)="(https?:[^"]+)"/g),
    ].map((m) => m[1]);

    assert.ok(
      externalUrls.length > 0,
      "Should have at least 1 external link (GitHub, LinkedIn, SETOFF)",
    );

    for (const url of externalUrls) {
      const parsed = new URL(url);
      assert.ok(
        approvedHosts.has(parsed.hostname),
        `Unapproved external domain found in HTML: ${parsed.hostname} (${url})`,
      );
    }
  });

  it("preserves all owner-reported career figures and statutory qualifications intact", () => {
    const text = backendHtml.replace(/<[^>]+>/g, " ");

    // Owner-reported figures
    assert.match(
      text,
      /180M\s*\+/,
      "Must include '180M+' dynamic visuals figure",
    );
    assert.match(
      text,
      /40M\s*\+/,
      "Must include '40M+' personalised videos figure",
    );
    assert.match(
      text,
      /20M\s*\+/,
      "Must include '20M+' interactive calls figure",
    );
    assert.match(
      text,
      /25M\s*\+/,
      "Must include '25M+' Coca-Cola holiday figure",
    );
    assert.match(
      text,
      /[-−]94\s*%/,
      "Must include '-94%' VoIP spend reduction figure",
    );
    assert.match(
      backendHtml,
      /€9\.0M\s+(?:to|→)\s+(?:&lt;|<)€0\.5M\/yr/,
      "Must include '€9.0M to <€0.5M/yr' VoIP run-rate figure",
    );

    // Statutory qualifications
    assert.match(
      backendHtml,
      /Owner-reported,\s+not\s+independently\s+audited/,
      "Must include 'Owner-reported, not independently audited' qualification",
    );
    assert.match(
      backendHtml,
      /Not\s+independently\s+audited/,
      "Must include 'Not independently audited' qualification",
    );

    // Verify catalog metrics evidence types
    assert.equal(catalog.metrics.length, 4, "Catalog must have 4 metrics");
    for (const m of catalog.metrics) {
      assert.equal(
        m.evidence_type,
        "owner_report",
        `Metric ${m.id} evidence_type must be owner_report`,
      );
    }
  });
});
