"use strict";
const fs = require("node:fs"),
  path = require("node:path");
const root = path.resolve(__dirname, ".."),
  dest = path.join(root, "_site");
if (fs.existsSync(dest))
  throw new Error(
    "_site already exists: use a fresh checkout or explicitly remove only this generated build.",
  );
fs.mkdirSync(dest);
const copy = (file) => {
  const target = path.join(dest, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.cpSync(path.join(root, file), target, { recursive: true });
};
for (const file of [
  "index.html",
  "styles.css",
  "site.js",
  "assets",
  "CNAME",
  "privacy/index.html",
  "oauth/index.html",
])
  if (fs.existsSync(path.join(root, file))) copy(file);
copy("inbox/media/catalog.json");
copy("inbox/media/tag-aliases.json");
const catalog = JSON.parse(
  fs.readFileSync(path.join(root, "inbox/media/catalog.json"), "utf8"),
);
for (const item of catalog.items)
  if (item.local_path) {
    if (
      !["user_supplied", "licensed"].includes(item.rights_status) ||
      !/^inbox\/media\/(images|video|documents)\/[a-z0-9._-]+$/i.test(
        item.local_path,
      )
    )
      throw new Error("Unsafe media publication: " + item.id);
    copy(item.local_path);
  }
fs.writeFileSync(path.join(dest, ".nojekyll"), "");
console.log(
  "Built approved site files only. Jules draft folders and repository metadata are excluded.",
);
