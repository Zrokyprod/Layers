import { copyFileSync, existsSync, lstatSync, mkdirSync, rmSync, symlinkSync } from "node:fs";
import { dirname, resolve } from "node:path";

const appRoot = process.cwd();
const nextDir = resolve(appRoot, ".next");
const routesManifest = resolve(nextDir, "routes-manifest.json");
const deterministicRoutesManifest = resolve(nextDir, "routes-manifest-deterministic.json");

if (existsSync(routesManifest) && !existsSync(deterministicRoutesManifest)) {
  copyFileSync(routesManifest, deterministicRoutesManifest);
}

if (!process.env.VERCEL) {
  process.exit(0);
}

const repoRoot = dirname(appRoot);
const rootNextDir = resolve(repoRoot, ".next");

if (repoRoot === appRoot || !existsSync(nextDir)) {
  process.exit(0);
}

if (existsSync(rootNextDir)) {
  const rootNextStat = lstatSync(rootNextDir);
  if (!rootNextStat.isSymbolicLink()) {
    process.exit(0);
  }
  rmSync(rootNextDir, { force: true });
}

mkdirSync(repoRoot, { recursive: true });
symlinkSync(nextDir, rootNextDir, "dir");
