const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path"),
  crypto = require("node:crypto");
const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const catalog = JSON.parse(
  fs.readFileSync(path.join(root, "inbox/media/catalog.json"), "utf8"),
);
const core = require(
  path.join(
    root,
    fs.existsSync(path.join(root, "media.js")) ? "media.js" : "site.js",
  ),
);
test("all local files and fragments exist; no duplicated IDs", () => {
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length);
  for (const [, url] of html.matchAll(/\b(?:href|src)="([^"]+)"/g)) {
    if (url.startsWith("#")) assert.ok(ids.includes(url.slice(1)), url);
    else if (!/^[a-z]+:/i.test(url))
      assert.ok(fs.existsSync(path.join(root, url)), url);
  }
  for (const file of [
    "styles.css",
    ...(fs.existsSync(path.join(root, "media.css")) ? ["media.css"] : []),
  ]) {
    const css = fs.readFileSync(path.join(root, file), "utf8");
    for (const [, asset] of css.matchAll(/url\(["']?([^"')]+)["']?\)/g))
      assert.ok(fs.existsSync(path.join(root, asset)), asset);
    assert.match(css, /prefers-reduced-motion/);
  }
});
test("accessible structure and no unsolicited remote runtime or fake contact form", () => {
  assert.equal((html.match(/<h1\b/g) || []).length, 1);
  assert.match(html, /aria-controls="navigation"/);
  assert.match(html, /type="search"/);
  assert.doesNotMatch(html, /<(?:script|img)[^>]+src="https?:|alert\(|<form\b/);
  for (const [img] of html.matchAll(/<img\b[^>]*>/g)) {
    assert.match(img, /alt="[^"]+"/);
    assert.match(img, /width="\d+"/);
    assert.match(img, /height="\d+"/);
  }
});
test("catalogue preserves evidence, rights and exact local media checksums", () => {
  assert.equal(catalog.schema_version, 1);
  const ids = new Set();
  const urls = new Set();
  for (const item of catalog.items) {
    assert.ok(item.id && !ids.has(item.id));
    ids.add(item.id);
    assert.ok(
      item.identity_evidence && item.rights_evidence && item.tags.length,
    );
    assert.match(item.retrieved_at, /^2026-10-11$/);
    if (item.source_url) {
      assert.equal(new URL(item.source_url).protocol, "https:");
      assert.ok(!urls.has(item.source_url), "duplicate canonical source");
      urls.add(item.source_url);
    }
    if (item.local_path) {
      assert.ok(["user_supplied", "licensed"].includes(item.rights_status));
      assert.ok(
        !path.isAbsolute(item.local_path) &&
          !item.local_path.split("/").includes(".."),
      );
      const buf = fs.readFileSync(path.join(root, item.local_path));
      assert.equal(
        crypto.createHash("sha256").update(buf).digest("hex"),
        item.sha256,
      );
    } else assert.equal(item.rights_status, "reference_only");
  }
  for (const [, src] of html.matchAll(/<img[^>]+src="(inbox\/[^"]+)"/g))
    assert.ok(catalog.items.some((item) => item.local_path === src));
});
test("tag search is multilingual, accent-insensitive, composable and literal", () => {
  assert.equal(core.normalize("MÚSICA"), "musica");
  assert.ok(core.matchesMedia({ tags: ["portrait"], text: "" }, "retrato"));
  assert.ok(core.matchesMedia({ tags: ["music"], text: "" }, "música"));
  assert.ok(
    core.matchesMedia(
      { tags: ["video", "community"], text: "" },
      "charla comunidad",
    ),
  );
  assert.ok(!core.matchesMedia({ tags: ["video"], text: "" }, "portrait"));
  assert.ok(!core.matchesMedia({ tags: ["portrait"], text: "" }, "", "video"));
  assert.ok(!core.matchesMedia({ tags: ["portrait"], text: "" }, "<script>"));
});
test("canonical video sources and numerical bounds remain explicit", () => {
  if (catalog.subject === "Daniel Cerezo") {
    assert.match(html, /watch\?v=rmEGBKXrxNs/);
    assert.match(html, /daniel_cerezo_la_hipocresia_de_la_inclusion_social/);
    assert.doesNotMatch(html, /Villa 21|Viaje a mi interior|VUI0K4rIZU0/);
  }
  if (catalog.metrics) {
    assert.equal(
      catalog.metrics.find((m) => m.id === "voip-after").comparator,
      "<",
    );
    assert.equal(
      catalog.metrics.find((m) => m.id === "voip-before").value,
      9000000,
    );
    assert.ok(((9000000 - 500000) / 9000000) * 100 > 94.4);
    assert.match(html, /Not\s+independently\s+audited/);
  }
});
