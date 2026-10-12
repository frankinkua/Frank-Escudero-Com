const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const {readMediaView,mediaViewHash}=require("../assets/explorer.js");
const root=path.join(__dirname,"..");
const html=fs.readFileSync(path.join(root,"index.html"),"utf8");
const catalogue=JSON.parse(fs.readFileSync(path.join(root,"inbox/media/catalog.json"),"utf8"));
test("media views round-trip accents, punctuation and filters",()=>{
 const hash=mediaViewHash("inclusión & música","video");
 assert.deepEqual(readMediaView(hash,["all","video"]),{query:"inclusión & música",filter:"video"});
 assert.equal(mediaViewHash("","all"),"#media");
 assert.deepEqual(readMediaView("#work",["all"]),{query:"",filter:"all"});
});
test("unknown filters and oversized query strings are bounded",()=>{
 assert.equal(readMediaView("#media?type=unsafe&q=hello",["all"]).filter,"all");
 assert.equal(readMediaView("#media?q="+"a".repeat(1000)).query.length,120);
 assert.equal(readMediaView(mediaViewHash("<img onerror=alert(1)>")).query,"<img onerror=alert(1)>");
});
test("every displayed media card maps to the independently reviewed catalogue",()=>{
 const ids=[...html.matchAll(/data-media-id="([^"]+)"/g)].map(m=>m[1]);
 assert.ok(ids.length>=4);
 assert.equal(ids.length,new Set(ids).size);
 for(const id of ids) assert.ok(catalogue.items.some(item=>item.id===id),id);
 assert.match(html,/data-media-reset/);assert.match(html,/data-media-permalink/);
 assert.match(html,/assets\/explorer.js/);assert.match(html,/assets\/explorer.css/);
});
test("explorer uses safe DOM text and never loads raw research or remote thumbnails",()=>{
 const js=fs.readFileSync(path.join(root,"assets/explorer.js"),"utf8");
 assert.doesNotMatch(js,/innerHTML|insertAdjacentHTML|fetch\(["']https?:|jules-/);
 assert.match(js,/fetch\("inbox\/media\/catalog.json"\)/);
 assert.doesNotMatch(js,/createElement\("img"\)|createElement\("iframe"\)/);
});
