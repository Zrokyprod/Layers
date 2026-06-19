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

if (repoRoot === appRoot || !existsSync(nextDir)) {
  process.exit(0);
}

function exposeToRepoRoot(name) {
  const source = resolve(appRoot, name);
  const target = resolve(repoRoot, name);

  if (!existsSync(source)) {
    return;
  }

  if (existsSync(target)) {
    const targetStat = lstatSync(target);
    if (!targetStat.isSymbolicLink()) {
      return;
    }
    rmSync(target, { force: true });
  }

  symlinkSync(source, target, "dir");
}

mkdirSync(repoRoot, { recursive: true });
exposeToRepoRoot(".next");
exposeToRepoRoot("node_modules");
