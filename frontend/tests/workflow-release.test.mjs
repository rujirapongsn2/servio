import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { createServer } from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const script = fileURLToPath(new URL("../scripts/check-workflow-release.mjs", import.meta.url));
const teams = "static/chunks/app/admin/teams/page-teams.js";
const workflow = "static/chunks/app/admin/teams/[id]/workflow/page-workflow.js";

async function fixture(t, { source = 'router.push(`/admin/teams/${id}/workflow`)', omitRoute, omitAsset, directory = ".next" } = {}) {
  const cwd = await mkdtemp(path.join(os.tmpdir(), "workflow-release-"));
  t.after(() => rm(cwd, { recursive: true, force: true }));
  const files = {
    "server/app-paths-manifest.json": JSON.stringify({
      "/admin/teams/page": "app/admin/teams/page.js",
      ...(!omitRoute && { "/admin/teams/[id]/workflow/page": "app/admin/teams/[id]/workflow/page.js" }),
    }),
    "app-build-manifest.json": JSON.stringify({ pages: {
      "/admin/teams/page": [teams],
      "/admin/teams/[id]/workflow/page": [workflow],
    } }),
    "server/app/admin/teams/page.js": "server teams",
    "server/app/admin/teams/[id]/workflow/page.js": "server workflow",
    [teams]: source,
    [workflow]: "workflow workspace",
  };
  for (const [file, content] of Object.entries(files)) {
    if (file === omitAsset) continue;
    const target = path.join(cwd, directory, file);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, content);
  }
  return { cwd, files, directory };
}

function run({ cwd, directory }, args = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script, ...args], {
      cwd, env: { ...process.env, NEXT_DIST_DIR: directory },
    });
    let output = "";
    child.stdout.on("data", (chunk) => { output += chunk; });
    child.stderr.on("data", (chunk) => { output += chunk; });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, output }));
  });
}

test("accepts a built full-page Workflow", async (t) => {
  assert.equal((await run(await fixture(t))).code, 0);
});

test("honors NEXT_DIST_DIR", async (t) => {
  assert.equal((await run(await fixture(t, { directory: ".next-workflow-test" }))).code, 0);
});

test("rejects a missing full-page route", async (t) => {
  const result = await run(await fixture(t, { omitRoute: true }));
  assert.equal(result.code, 1);
  assert.match(result.output, /Missing built route/);
});

test("rejects a missing route asset", async (t) => {
  assert.equal((await run(await fixture(t, { omitAsset: workflow }))).code, 1);
});

test("rejects the old modal even when a Workflow route remains", async (t) => {
  const result = await run(await fixture(t, { source: '"/workflow"; "Digital employee map showing routing"' }));
  assert.equal(result.code, 1);
  assert.match(result.output, /does not open the full-page/);
});

test("rejects Teams that no longer link to Workflow", async (t) => {
  assert.equal((await run(await fixture(t, { source: "openModal()" }))).code, 1);
});

test("requires a positive team ID for public checks", async (t) => {
  const result = await run(await fixture(t), ["--url", "http://localhost", "--team-id", "0"]);
  assert.equal(result.code, 1);
  assert.match(result.output, /POSITIVE_INTEGER/);
});

test("checks public bundles without authentication and rejects old or broken assets", async (t) => {
  const build = await fixture(t);
  let mode = "valid";
  let authenticated = false;
  const server = createServer((request, response) => {
    authenticated ||= Boolean(request.headers.authorization || request.headers.cookie);
    const pathname = decodeURIComponent(request.url);
    if (pathname === "/admin/teams") {
      const src = mode === "external" ? "https://other.invalid/_next/static/bad.js" : `/_next/${teams}`;
      response.end(`<script src="${src}"></script>`);
    } else if (pathname === "/admin/teams/7/workflow") {
      response.end(`<script src="/_next/${workflow}"></script>`);
    } else if (pathname === `/_next/${teams}`) {
      response.end(mode === "old" ? "Digital employee map showing /workflow" : build.files[teams]);
    } else if (pathname === `/_next/${workflow}` && mode !== "missing") {
      response.end(build.files[workflow]);
    } else {
      response.statusCode = 404;
      response.end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const args = ["--url", `http://127.0.0.1:${server.address().port}`, "--team-id", "7"];
  assert.equal((await run(build, args)).code, 0);
  for (mode of ["old", "missing", "external"]) {
    const result = await run(build, args);
    assert.equal(result.code, 1, `${mode}: ${result.output}`);
  }
  assert.equal(authenticated, false);
});
