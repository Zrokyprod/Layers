#!/usr/bin/env node
/**
 * Rule 4 benchmark: @zroky/sdk bundle gzipped < 30 KB.
 * Run: node scripts/bench_js_sdk_size.js
 */
import { createReadStream, statSync } from "node:fs";
import { createGzip } from "node:zlib";
import { pipeline } from "node:stream/promises";
import { Writable } from "node:stream";

const LIMIT_KB = 30;
const ENTRY = new URL("../dist/index.mjs", import.meta.url).pathname;

let raw;
try {
  raw = statSync(ENTRY).size;
} catch {
  console.error("dist/index.mjs not found — run `npm run build` first.");
  process.exit(1);
}

let gzBytes = 0;
const counter = new Writable({
  write(chunk, _enc, cb) {
    gzBytes += chunk.length;
    cb();
  },
});

await pipeline(createReadStream(ENTRY), createGzip({ level: 9 }), counter);

const rawKB = (raw / 1024).toFixed(2);
const gzKB = (gzBytes / 1024).toFixed(2);
console.log(`Bundle: ${rawKB} KB raw | ${gzKB} KB gzipped | limit: ${LIMIT_KB} KB`);

if (gzBytes / 1024 > LIMIT_KB) {
  console.error(`FAIL: gzipped bundle ${gzKB} KB exceeds ${LIMIT_KB} KB limit (Rule 4)`);
  process.exit(1);
}
console.log("PASS: bundle size within Rule 4 limit");
