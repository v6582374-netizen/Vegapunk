import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const COMMIT = "c0b16ba603d3d110e3e39d587b0a1a3a310ea464";
const TREE = "12ede09996060fdc329362262759f3635c6bd30c";
const TRACKED_FILES = 296;
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const upstreamRoot = path.join(projectRoot, "skills-manager-upstream");
const manifestPath = path.join(projectRoot, "skills-manager-provenance.json");

async function listFiles(root, relative = "") {
  const entries = await fs.readdir(path.join(root, relative), { withFileTypes: true });
  const files = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const child = path.posix.join(relative, entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(root, child)));
    else if (entry.isFile()) files.push(child);
  }
  return files;
}

function gitBlob(buffer) {
  return createHash("sha1")
    .update(`blob ${buffer.length}\0`)
    .update(buffer)
    .digest("hex");
}

function disposition(upstreamPath) {
  if (upstreamPath.startsWith("src/")) {
    return {
      status: "adapted-runtime-copy",
      integrated_paths: [`src/skills-manager/${upstreamPath.slice(4)}`],
    };
  }
  if (/^src-tauri\/src\/(commands|models|services)\//.test(upstreamPath)) {
    return { status: "adapted-runtime-copy", integrated_paths: [upstreamPath] };
  }
  if (upstreamPath === "src-tauri/src/test_support.rs") {
    return { status: "adapted-test-support", integrated_paths: [upstreamPath] };
  }
  if (upstreamPath === "src-tauri/src/features.rs") {
    return { status: "preserved-dormant-upstream-module", integrated_paths: [upstreamPath] };
  }
  const mergedFiles = new Map([
    ["package.json", ["package.json"]],
    ["package-lock.json", ["package-lock.json"]],
    ["vite.config.ts", ["vite.config.ts"]],
    ["tsconfig.json", ["tsconfig.json"]],
    ["src-tauri/Cargo.toml", ["src-tauri/Cargo.toml"]],
    ["src-tauri/Cargo.lock", ["src-tauri/Cargo.lock"]],
    ["src-tauri/build.rs", ["src-tauri/build.rs"]],
    ["src-tauri/tauri.conf.json", ["src-tauri/tauri.conf.json"]],
    ["src-tauri/capabilities/default.json", ["src-tauri/capabilities/default.json"]],
    ["src-tauri/src/lib.rs", ["src-tauri/src/lib.rs"]],
  ]);
  if (mergedFiles.has(upstreamPath)) {
    return { status: "merged-into-host", integrated_paths: mergedFiles.get(upstreamPath) };
  }
  if (
    upstreamPath === "LICENSE" ||
    /^(PRIVACY|PRIVACY_CN|SECURITY|README|README_CN|CONTRIBUTING|DESIGN)\.md$/.test(upstreamPath)
  ) {
    return { status: "preserved-legal-or-documentation", integrated_paths: [] };
  }
  return { status: "preserved-upstream-support-file", integrated_paths: [] };
}

async function buildManifest() {
  const paths = await listFiles(upstreamRoot);
  const files = [];
  for (const upstreamPath of paths) {
    const contents = await fs.readFile(path.join(upstreamRoot, upstreamPath));
    files.push({
      path: upstreamPath,
      git_blob: gitBlob(contents),
      sha256: createHash("sha256").update(contents).digest("hex"),
      exact_copy: `skills-manager-upstream/${upstreamPath}`,
      ...disposition(upstreamPath),
    });
  }
  return {
    schema_version: 1,
    upstream: "https://github.com/jiweiyeah/Skills-Manager",
    commit: COMMIT,
    tree: TREE,
    tracked_files: TRACKED_FILES,
    files,
  };
}

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

async function verify() {
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  invariant(manifest.commit === COMMIT, `Unexpected commit: ${manifest.commit}`);
  invariant(manifest.tree === TREE, `Unexpected tree: ${manifest.tree}`);
  invariant(manifest.tracked_files === TRACKED_FILES, "Unexpected tracked file contract");
  invariant(manifest.files.length === TRACKED_FILES, `Manifest has ${manifest.files.length} files`);

  const actualPaths = await listFiles(upstreamRoot);
  invariant(actualPaths.length === TRACKED_FILES, `Exact copy has ${actualPaths.length} files`);
  invariant(new Set(manifest.files.map((entry) => entry.path)).size === TRACKED_FILES, "Duplicate manifest paths");
  invariant(
    JSON.stringify(actualPaths) === JSON.stringify(manifest.files.map((entry) => entry.path)),
    "Exact-copy paths differ from the manifest",
  );

  for (const entry of manifest.files) {
    const contents = await fs.readFile(path.join(upstreamRoot, entry.path));
    invariant(gitBlob(contents) === entry.git_blob, `Git blob mismatch: ${entry.path}`);
    invariant(
      createHash("sha256").update(contents).digest("hex") === entry.sha256,
      `SHA-256 mismatch: ${entry.path}`,
    );
    invariant(entry.status, `Missing disposition: ${entry.path}`);
    for (const integratedPath of entry.integrated_paths) {
      await fs.access(path.join(projectRoot, integratedPath));
    }
  }
}

if (process.argv.includes("--write")) {
  const manifest = await buildManifest();
  invariant(manifest.files.length === TRACKED_FILES, `Source copy has ${manifest.files.length} files`);
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
}

await verify();
console.log(`Verified Skills Manager ${COMMIT.slice(0, 12)}: ${TRACKED_FILES} files accounted for.`);
