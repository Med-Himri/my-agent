// Usage: node render.mjs <timeline.json> <out.mp4>
// Renders template.html frame by frame with headless Chromium and pipes JPEG frames into ffmpeg.
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const { chromium } = createRequire(import.meta.url)("playwright");
const [, , timelinePath, outPath] = process.argv;
const data = JSON.parse(readFileSync(timelinePath, "utf8"));
const FPS = data.fps || 30;
const here = path.dirname(fileURLToPath(import.meta.url));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(path.join(here, "template.html")).href);
await page.evaluate(d => window.setup(d), data);

// Preview mode: PREVIEW="1.5,10,20" saves still PNGs instead of rendering the video.
if (process.env.PREVIEW) {
  for (const t of process.env.PREVIEW.split(",").map(Number)) {
    await page.evaluate(x => window.renderAt(x), t);
    await page.screenshot({ path: outPath.replace(/\.mp4$/, "") + `_${t}.png` });
  }
  await browser.close();
  process.exit(0);
}

const ff = spawn("ffmpeg", ["-v", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
  "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", String(FPS), outPath],
  { stdio: ["pipe", "inherit", "inherit"] });

const frames = Math.ceil(data.total * FPS);
const t0 = Date.now();
for (let f = 0; f < frames; f++) {
  await page.evaluate(t => window.renderAt(t), f / FPS);
  const buf = await page.screenshot({ type: "jpeg", quality: 92 });
  if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
  if (f % 150 === 0) process.stderr.write(`frame ${f}/${frames} (${((Date.now() - t0) / 1000).toFixed(0)}s)\n`);
}
ff.stdin.end();
await new Promise((res, rej) => ff.on("close", c => (c === 0 ? res() : rej(new Error("ffmpeg exit " + c)))));
await browser.close();
process.stderr.write(`done: ${frames} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s\n`);
