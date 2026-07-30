import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import postcss from "postcss";

const COMMIT = "c0b16ba603d3d110e3e39d587b0a1a3a310ea464";
const TREE = "12ede09996060fdc329362262759f3635c6bd30c";
const TRACKED_FILES = 296;
const UPSTREAM_COMMANDS = 86;
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const upstreamRoot = path.join(projectRoot, "skills-manager-upstream");
const manifestPath = path.join(projectRoot, "skills-manager-provenance.json");
const SUPPLEMENTAL_INTEGRATED_FILES = [
  {
    path: "src/skills-manager/services/cloudSyncWorkflow.ts",
    upstream_commit: "4165c6f",
    upstream_path: "src/services/cloudSyncWorkflow.ts",
  },
];

const ADAPTATIONS = [
  {
    id: "frontend-runtime-relocation",
    upstream_scope: ["src/**/*"],
    integrated_scope: ["src/skills-manager/**/*"],
    reason: "Embed the complete React application inside the existing OpenWorker frontend.",
    behavioral_impact: "Imports use the @skills-manager namespace while module behavior remains upstream-equivalent.",
    regression_coverage: ["npm run build", "npm run skills-manager:test", "per-file integrated SHA-256 verification"],
    upstream_sync_strategy: "Copy the new upstream src tree first, reapply only the namespace rewrite, then regenerate this manifest.",
  },
  {
    id: "embedded-memory-router",
    upstream_scope: ["src/App.tsx BrowserRouter"],
    integrated_scope: ["src/skills-manager/App.tsx MemoryRouter"],
    reason: "The module is mounted below OpenWorker's existing browser URL and cannot own document history.",
    behavioral_impact: "Skills Manager navigation stays internal to its workspace without changing OpenWorker routes.",
    regression_coverage: ["npm run build", "user-owned visual navigation acceptance"],
    upstream_sync_strategy: "Reapply the BrowserRouter-to-MemoryRouter substitution after each upstream App.tsx update.",
  },
  {
    id: "workspace-scoped-theme",
    upstream_scope: ["src/hooks/useTheme.tsx document.documentElement mutations"],
    integrated_scope: ["src/skills-manager/hooks/useTheme.tsx .skills-manager-root mutations"],
    reason: "The embedded module shares a document with OpenWorker.",
    behavioral_impact: "Theme and font variables affect only the Skills Manager workspace.",
    regression_coverage: ["npm run build", "CSS scope verification", "user-owned visual theme acceptance"],
    upstream_sync_strategy: "Keep upstream theme resolution logic and retarget only its DOM mutation root.",
  },
  {
    id: "react-18-file-tree-ref",
    upstream_scope: ["src/components/editor/FileTree.tsx nullable React 19 ref typing"],
    integrated_scope: ["src/skills-manager/components/editor/FileTree.tsx React 18 ref typing"],
    reason: "OpenWorker currently compiles against React 18 types.",
    behavioral_impact: "No runtime behavior changes; the editor ref type matches the host compiler.",
    regression_coverage: ["npm run build"],
    upstream_sync_strategy: "Drop this adaptation when the host moves to React 19; otherwise reapply the type-only change.",
  },
  {
    id: "scoped-tailwind-4-bundle",
    upstream_scope: ["src/index.css", "Tailwind 4 source scanning"],
    integrated_scope: ["src/skills-manager/index.css", "public/skills-manager.css"],
    reason: "The host uses Tailwind 3 while the copied module requires Tailwind 4.",
    behavioral_impact: "The generated module stylesheet is isolated below .skills-manager-root and does not reset host UI.",
    regression_coverage: ["npm run skills-manager:css", "structured CSS scope verification", "generated CSS SHA-256 verification"],
    upstream_sync_strategy: "Regenerate public/skills-manager.css from the exact upstream src/index.css after every upstream sync.",
  },
  {
    id: "tauri-host-merge",
    upstream_scope: ["src-tauri/src/commands/**/*", "src-tauri/src/models/**/*", "src-tauri/src/services/**/*"],
    integrated_scope: ["src-tauri/src/commands/**/*", "src-tauri/src/models/**/*", "src-tauri/src/services/**/*", "src-tauri/src/lib.rs"],
    reason: "A Tauri process supports one host builder, command handler, plugin set, and application lifecycle.",
    behavioral_impact: "All upstream Skills Manager commands and services execute inside OpenWorker's existing Tauri process.",
    regression_coverage: ["all 86 upstream invoke commands are verified in the host handler", "cargo check", "cargo test"],
    upstream_sync_strategy: "Merge upstream Rust modules, register every new command and plugin, then rerun handler coverage and Rust tests.",
  },
  {
    id: "host-ownership-boundaries",
    upstream_scope: ["Skills Manager mutable Skill APIs and ~/.skills-manager storage"],
    integrated_scope: ["OpenWorker read-only load_skill and ~/.config/coworker storage"],
    reason: "The existing OpenWorker loader and Skills Manager mutation service own different persistence contracts.",
    behavioral_impact: "OpenWorker retains read-only loading while all copied management mutations continue through upstream services.",
    regression_coverage: ["npm test", "cargo test"],
    upstream_sync_strategy: "Preserve both ownership paths and reject upstream merges that redirect OpenWorker state into Skills Manager storage.",
  },
  {
    id: "dormant-incomplete-features-module",
    upstream_scope: ["src-tauri/src/features.rs"],
    integrated_scope: ["src-tauri/src/features.rs preserved but unregistered"],
    reason: "The pinned upstream module references a missing LicenseInfo type and has no callers.",
    behavioral_impact: "The exact source remains auditable without introducing an uncompilable dead module into the host crate.",
    regression_coverage: ["exact Git tree verification", "cargo check"],
    upstream_sync_strategy: "Re-evaluate registration when upstream supplies the missing model or begins calling the module.",
  },
  {
    id: "pinned-module-updater-version",
    upstream_scope: ["src-tauri/src/commands/updater.rs package version lookup"],
    integrated_scope: ["src-tauri/src/commands/updater.rs Skills Manager 2.1.7 constant"],
    reason: "OpenWorker and the embedded Skills Manager module have independent release versions.",
    behavioral_impact: "Skills Manager GitHub releases are compared against module version 2.1.7 instead of OpenWorker 0.1.6.",
    regression_coverage: ["update_check_uses_the_pinned_skills_manager_version"],
    upstream_sync_strategy: "Update this constant together with the pinned upstream commit and provenance record.",
  },
  {
    id: "restore-cloud-sync-workflow",
    upstream_scope: ["upstream history 4165c6f src/services/cloudSyncWorkflow.ts"],
    integrated_scope: ["src/skills-manager/services/cloudSyncWorkflow.ts"],
    reason: "Pinned commit c0b16ba contains the workflow test but accidentally omits its implementation.",
    behavioral_impact: "The copied cloud pull-push-conflict workflow is executable and its inherited tests run.",
    regression_coverage: ["src/skills-manager/services/__tests__/cloudSyncWorkflow.test.ts", "npm run skills-manager:test"],
    upstream_sync_strategy: "Prefer the file from a future upstream commit once restored there; until then retain the exact 4165c6f implementation.",
  },
  {
    id: "wechat-validation-alignment",
    upstream_scope: ["src/services/feedbackContact.ts"],
    integrated_scope: ["src/skills-manager/services/feedbackContact.ts"],
    reason: "The pinned frontend regex conflicts with its own test and the upstream Rust validator.",
    behavioral_impact: "WeChat IDs may begin with an underscore, matching backend validation.",
    regression_coverage: ["validateFeedbackContact accepts wechat ids starting with underscore", "validate_feedback_request_should_accept_wechat_starting_with_underscore"],
    upstream_sync_strategy: "Remove the patch after upstream accepts underscore-prefixed IDs in the frontend regex.",
  },
  {
    id: "broken-projection-classification",
    upstream_scope: ["src-tauri/src/services/linker.rs symlink status classification"],
    integrated_scope: ["src-tauri/src/services/linker.rs", "src-tauri/src/commands/sync.rs"],
    reason: "Ticket 02 found Kiro and Trae projections whose symlink targets no longer exist.",
    behavioral_impact: "Missing symlink targets are observable as Broken sync issues while real wrong-target content remains protected.",
    regression_coverage: ["ticket_02_broken_kiro_and_trae_gh_axi_projections_remain_sync_issues"],
    upstream_sync_strategy: "Retain the missing-target classification unless upstream adopts equivalent broken-projection handling.",
  },
  {
    id: "inventory-edge-case-fixtures",
    upstream_scope: ["Ticket 02 local source inventory"],
    integrated_scope: ["src-tauri/src/services/scanner.rs regression fixtures"],
    reason: "Observed Cursor manifest drift and malformed frontmatter must not make local Skills disappear or appear from stale metadata.",
    behavioral_impact: "Directory contents remain authoritative and tolerant scanning keeps malformed-frontmatter Skills discoverable.",
    regression_coverage: ["ticket_02_cursor_manifest_drift_does_not_create_or_hide_skills", "ticket_02_malformed_codebase_memory_frontmatter_remains_discoverable"],
    upstream_sync_strategy: "Carry the fixtures forward and resolve any upstream scanner change that breaks these inventory contracts.",
  },
  {
    id: "parallel-rust-test-home-isolation",
    upstream_scope: ["src-tauri/src/test_support.rs", "src-tauri/src/commands/usage.rs"],
    integrated_scope: ["shared panic-safe with_temp_home helper"],
    reason: "A second lock-free HOME helper forced the entire crate test suite to run serially.",
    behavioral_impact: "Tests safely restore HOME and USERPROFILE after success or panic and can run with Cargo's default parallelism.",
    regression_coverage: ["cargo test with no RUST_TEST_THREADS override"],
    upstream_sync_strategy: "Keep all environment-mutating tests on the single shared helper and do not restore the crate-wide serial override.",
  },
  {
    id: "complete-upstream-frontend-test-gate",
    upstream_scope: ["all 29 src/**/*.test.ts files"],
    integrated_scope: ["package.json skills-manager:test"],
    reason: "The initial host script exercised only one of the copied upstream frontend test files.",
    behavioral_impact: "Every inherited node:test suite runs in the integration gate while Vitest continues to exclude node:test files.",
    regression_coverage: ["npm run skills-manager:test"],
    upstream_sync_strategy: "Keep the recursive test glob so newly added upstream node:test files enter the gate automatically.",
  },
];

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

function gitObject(type, contents) {
  return createHash("sha1")
    .update(`${type} ${contents.length}\0`)
    .update(contents)
    .digest("hex");
}

function gitBlob(contents) {
  return gitObject("blob", contents);
}

function sha256(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

function gitSortKey(entry) {
  return Buffer.from(`${entry.name}${entry.isDirectory() ? "/" : ""}`);
}

async function readTrackedContents(absolutePath, stats) {
  if (stats.isSymbolicLink()) return Buffer.from(await fs.readlink(absolutePath));
  return fs.readFile(absolutePath);
}

async function scanGitTree(root, relative = "") {
  const entries = await fs.readdir(path.join(root, relative), { withFileTypes: true });
  entries.sort((a, b) => Buffer.compare(gitSortKey(a), gitSortKey(b)));

  const chunks = [];
  const files = [];
  for (const entry of entries) {
    const child = path.posix.join(relative, entry.name);
    const absolutePath = path.join(root, child);
    const stats = await fs.lstat(absolutePath);
    let mode;
    let objectId;

    if (stats.isDirectory()) {
      const subtree = await scanGitTree(root, child);
      mode = "40000";
      objectId = subtree.tree;
      files.push(...subtree.files);
    } else {
      invariant(stats.isFile() || stats.isSymbolicLink(), `Unsupported tracked entry: ${child}`);
      const contents = await readTrackedContents(absolutePath, stats);
      mode = stats.isSymbolicLink() ? "120000" : stats.mode & 0o111 ? "100755" : "100644";
      objectId = gitBlob(contents);
      files.push({ path: child, mode, contents, git_blob: objectId });
    }

    chunks.push(Buffer.from(`${mode} ${entry.name}\0`), Buffer.from(objectId, "hex"));
  }

  const contents = Buffer.concat(chunks);
  return { tree: gitObject("tree", contents), files };
}

function disposition(upstreamPath) {
  if (upstreamPath === "src/index.css") {
    return {
      status: "adapted-runtime-and-generated-css",
      integrated_paths: ["src/skills-manager/index.css", "public/skills-manager.css"],
    };
  }
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

async function describeIntegratedFiles(integratedPaths) {
  return Promise.all(
    integratedPaths.map(async (integratedPath) => {
      const absolutePath = path.join(projectRoot, integratedPath);
      const stats = await fs.lstat(absolutePath);
      invariant(stats.isFile() || stats.isSymbolicLink(), `Integration target is not a file: ${integratedPath}`);
      const contents = await readTrackedContents(absolutePath, stats);
      return { path: integratedPath, sha256: sha256(contents) };
    }),
  );
}

function generateHandlerCommands(source, sourcePath) {
  const marker = "generate_handler![";
  const start = source.indexOf(marker);
  invariant(start >= 0, `Missing generate_handler! in ${sourcePath}`);
  const bodyStart = start + marker.length;
  const bodyEnd = source.indexOf("]", bodyStart);
  invariant(bodyEnd >= 0, `Unterminated generate_handler! in ${sourcePath}`);
  return source
    .slice(bodyStart, bodyEnd)
    .replace(/\/\/.*$/gm, "")
    .split(",")
    .map((command) => command.trim())
    .filter(Boolean);
}

async function verifyHandlerCoverage() {
  const upstreamPath = "skills-manager-upstream/src-tauri/src/lib.rs";
  const hostPath = "src-tauri/src/lib.rs";
  const [upstreamSource, hostSource] = await Promise.all([
    fs.readFile(path.join(projectRoot, upstreamPath), "utf8"),
    fs.readFile(path.join(projectRoot, hostPath), "utf8"),
  ]);
  const upstreamCommands = generateHandlerCommands(upstreamSource, upstreamPath);
  const hostCommands = generateHandlerCommands(hostSource, hostPath);
  const hostSet = new Set(hostCommands);
  const missing = upstreamCommands.filter((command) => !hostSet.has(command));

  invariant(upstreamCommands.length === UPSTREAM_COMMANDS, `Expected ${UPSTREAM_COMMANDS} upstream commands, found ${upstreamCommands.length}`);
  invariant(new Set(upstreamCommands).size === upstreamCommands.length, "Duplicate upstream invoke commands");
  invariant(new Set(hostCommands).size === hostCommands.length, "Duplicate host invoke commands");
  invariant(missing.length === 0, `Host handler is missing upstream commands: ${missing.join(", ")}`);

  return {
    upstream_count: upstreamCommands.length,
    host_count: hostCommands.length,
    upstream_commands: upstreamCommands,
  };
}

function insideKeyframes(rule) {
  let parent = rule.parent;
  while (parent) {
    if (parent.type === "atrule" && parent.name.toLowerCase().endsWith("keyframes")) return true;
    parent = parent.parent;
  }
  return false;
}

async function verifyScopedCss() {
  const cssPath = "public/skills-manager.css";
  const css = await fs.readFile(path.join(projectRoot, cssPath), "utf8");
  const root = postcss.parse(css, { from: cssPath });
  let checkedSelectors = 0;

  root.walkRules((rule) => {
    if (insideKeyframes(rule)) return;
    for (const selector of rule.selectors) {
      checkedSelectors += 1;
      invariant(selector.trim().startsWith(".skills-manager-root"), `Unscoped Skills Manager selector: ${selector}`);
    }
  });

  invariant(checkedSelectors > 0, "Generated Skills Manager CSS has no scoped selectors");
  return { path: cssPath, root_selector: ".skills-manager-root", checked_selectors: checkedSelectors };
}

async function buildManifest(handlerCoverage, cssScope) {
  const audit = await scanGitTree(upstreamRoot);
  invariant(audit.tree === TREE, `Exact-copy Git tree mismatch: expected ${TREE}, found ${audit.tree}`);
  invariant(audit.files.length === TRACKED_FILES, `Exact copy has ${audit.files.length} tracked files`);

  const files = [];
  for (const file of audit.files) {
    const integration = disposition(file.path);
    files.push({
      path: file.path,
      mode: file.mode,
      git_blob: file.git_blob,
      sha256: sha256(file.contents),
      exact_copy: `skills-manager-upstream/${file.path}`,
      ...integration,
      integrated_files: await describeIntegratedFiles(integration.integrated_paths),
    });
  }

  const supplementalDigests = await describeIntegratedFiles(
    SUPPLEMENTAL_INTEGRATED_FILES.map((entry) => entry.path),
  );

  return {
    schema_version: 2,
    upstream: "https://github.com/jiweiyeah/Skills-Manager",
    commit: COMMIT,
    tree: TREE,
    tracked_files: TRACKED_FILES,
    adaptations: ADAPTATIONS,
    verification: {
      handler_coverage: handlerCoverage,
      css_scope: cssScope,
    },
    supplemental_integrated_files: SUPPLEMENTAL_INTEGRATED_FILES.map((entry, index) => ({
      ...entry,
      sha256: supplementalDigests[index].sha256,
    })),
    files,
  };
}

const handlerCoverage = await verifyHandlerCoverage();
const cssScope = await verifyScopedCss();
const expectedManifest = await buildManifest(handlerCoverage, cssScope);

if (process.argv.includes("--write")) {
  await fs.writeFile(manifestPath, `${JSON.stringify(expectedManifest, null, 2)}\n`);
}

const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
invariant(
  JSON.stringify(manifest) === JSON.stringify(expectedManifest),
  "Skills Manager provenance is stale; run npm run skills-manager:verify -- --write",
);

console.log(
  `Verified Skills Manager ${COMMIT.slice(0, 12)}: ${TRACKED_FILES} files, Git tree ${TREE.slice(0, 12)}, ${handlerCoverage.upstream_count} commands, ${cssScope.checked_selectors} scoped selectors.`,
);
