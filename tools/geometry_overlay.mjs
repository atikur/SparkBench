// Supervision aid: draw a labelled pixel grid (and optional markers) over a frame and save full-size and zoomed crops.
// Usage: node grid.mjs <frame> <outDir> [markersJson] [cropsJson]
//   markersJson: {"red":[x,y],"green":[x,y],"oled":[[x,y],...]}  cropsJson: [{"name":"a","x":..,"y":..,"w":..,"h":..,"scale":3}]
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
const [frame, outDir, markersArg, cropsArg] = process.argv.slice(2);
const markers = markersArg ? JSON.parse(markersArg) : null;
const crops = cropsArg ? JSON.parse(cropsArg) : [];
mkdirSync(outDir, { recursive: true });
const PORT = 9335, CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-first-run", "--allow-file-access-from-files", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(outDir, "profile")}`, "--window-size=1920,1080", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function targets() { for (let i = 0; i < 50; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/json/list`); if (r.ok) return r.json(); } catch {} await sleep(200); } throw new Error("Chrome did not start"); }
const page = (await targets()).find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl); await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise((res, rej) => { const n = ++id; pending.set(n, m => m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result)); ws.send(JSON.stringify({ id: n, method, params })); });
let grid = "";
for (let x = 0; x <= 1920; x += 20) if (x % 100) grid += `<line x1="${x}" y1="0" x2="${x}" y2="1080" stroke="#ffffff30" stroke-width="1"/>`;
for (let y = 0; y <= 1080; y += 20) if (y % 100) grid += `<line x1="0" y1="${y}" x2="1920" y2="${y}" stroke="#ffffff30" stroke-width="1"/>`;
for (let x = 0; x <= 1920; x += 100) grid += `<line x1="${x}" y1="0" x2="${x}" y2="1080" stroke="${x % 500 ? '#ffffff80' : '#ffd60a'}" stroke-width="1"/><text x="${x + 3}" y="14" fill="#ffd60a" font-size="13" font-family="sans-serif">${x}</text><text x="${x + 3}" y="1074" fill="#ffd60a" font-size="13" font-family="sans-serif">${x}</text>`;
for (let y = 0; y <= 1080; y += 100) grid += `<line x1="0" y1="${y}" x2="1920" y2="${y}" stroke="${y % 500 ? '#ffffff80' : '#ffd60a'}" stroke-width="1"/><text x="3" y="${y - 3}" fill="#ffd60a" font-size="13" font-family="sans-serif">${y}</text><text x="1880" y="${y - 3}" fill="#ffd60a" font-size="13" font-family="sans-serif">${y}</text>`;
let marks = "";
if (markers) {
  const circ = (p, col) => `<circle cx="${p[0]}" cy="${p[1]}" r="9" fill="none" stroke="${col}" stroke-width="2"/><circle cx="${p[0]}" cy="${p[1]}" r="2" fill="${col}"/><circle cx="${p[0]}" cy="${p[1]}" r="30" fill="none" stroke="${col}" stroke-width="1" stroke-dasharray="4 3"/>`;
  if (markers.red) marks += circ(markers.red, "#ff3b30");
  if (markers.green) marks += circ(markers.green, "#34c759");
  if (markers.oled) marks += `<polygon points="${markers.oled.map(p => p.join(',')).join(' ')}" fill="none" stroke="#0a84ff" stroke-width="2"/>` + markers.oled.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="#0a84ff"/><text x="${p[0] + 6}" y="${p[1] - 6}" fill="#0a84ff" font-size="14" font-family="sans-serif">${i}</text>`).join("");
}
const html = `<!doctype html><html><body style="margin:0;background:#000"><img src="file://${resolve(frame)}" width="1920" height="1080" style="position:absolute;left:0;top:0"><svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" style="position:absolute;left:0;top:0">${grid}${marks}</svg></body></html>`;
writeFileSync(join(outDir, "page.html"), html);
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: "file://" + join(outDir, "page.html") });
await sleep(800);
async function shot(name, clip) { const { data } = await send("Page.captureScreenshot", { format: "png", clip }); writeFileSync(join(outDir, name), Buffer.from(data, "base64")); console.log("saved", name); }
await shot("grid-full.png", { x: 0, y: 0, width: 1920, height: 1080, scale: 1 });
for (const c of crops) await shot(`crop-${c.name}.png`, { x: c.x, y: c.y, width: c.w, height: c.h, scale: c.scale || 3 });
try { await send("Browser.close"); } catch {}
ws.close(); chrome.kill();
