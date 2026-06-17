#!/usr/bin/env node
/**
 * Rule 4 benchmark: @zroky-ai/sdk bundle gzipped < 30 KB.
 * Run: node scripts/bench_js_sdk_size.js
 */
const { createReadStream, statSync } = require("node:fs");
const { join } = require("node:path");
const { createGzip } = require("node:zlib");
const { pipeline } = require("node:stream/promises");
const { Writable } = require("node:stream");

const LIMIT_KB = 30;
const ENTRY = join(__dirname, "..", "dist", "index.mjs");

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

pipeline(createReadStream(ENTRY), createGzip({ level: 9 }), counter).then(() => {
  const rawKB = (raw / 1024).toFixed(2);
  const gzKB = (gzBytes / 1024).toFixed(2);
  console.log(`Bundle: ${rawKB} KB raw | ${gzKB} KB gzipped | limit: ${LIMIT_KB} KB`);

  if (gzBytes / 1024 > LIMIT_KB) {
    console.error(`FAIL: gzipped bundle ${gzKB} KB exceeds ${LIMIT_KB} KB limit (Rule 4)`);
    process.exit(1);
  }
  console.log("PASS: bundle size within Rule 4 limit");
}).catch((err) => {
  console.error(err);
  process.exit(1);
});
