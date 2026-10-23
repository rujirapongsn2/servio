import { readFile } from "node:fs/promises";
import path from "node:path";

const teamsRoute = "/admin/teams/page";
const workflowRoute = "/admin/teams/[id]/workflow/page";
const oldModalCopy = "Digital employee map showing";

function requireFullPage(source) {
  if (!source.includes("/workflow") || source.includes(oldModalCopy)) {
    throw new Error("Teams bundle does not open the full-page Workflow.");
  }
}

async function checkBuild() {
  const directory = path.resolve(process.env.NEXT_DIST_DIR || ".next");
  const read = (file) => readFile(path.join(directory, file), "utf8");
  const routes = JSON.parse(await read("server/app-paths-manifest.json"));
  const { pages } = JSON.parse(await read("app-build-manifest.json"));
  for (const route of [teamsRoute, workflowRoute]) {
    if (!routes[route] || !pages[route]?.length) {
      throw new Error(`Missing built route ${route}.`);
    }
    await read(routes[route].startsWith("app/") ? `server/${routes[route]}` : routes[route]);
    for (const asset of pages[route]) {
      if (!asset.startsWith("static/") || asset.split("/").includes("..")) {
        throw new Error(`Invalid built asset ${asset}.`);
      }
      await read(asset);
    }
  }
  const teamsAsset = pages[teamsRoute].find((asset) => /\/app\/admin\/teams\/page-[^/]+\.js$/.test(asset));
  if (!teamsAsset) throw new Error("Missing Teams page bundle.");
  requireFullPage(await read(teamsAsset));
}

async function checkPublic(base, teamId) {
  const origin = new URL(base);
  if (!["http:", "https:"].includes(origin.protocol) || origin.username || origin.password) {
    throw new Error("Use an HTTP(S) URL without credentials.");
  }
  const get = async (url) => {
    const response = await fetch(url, { signal: AbortSignal.timeout(15000), redirect: "error" });
    if (response.status !== 200) throw new Error(`${url} returned HTTP ${response.status}.`);
    return response.text();
  };
  for (const pathname of ["/admin/teams", `/admin/teams/${teamId}/workflow`]) {
    const html = await get(new URL(pathname, origin));
    const scripts = [...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)].map((match) => {
      const url = new URL(match[1].replaceAll("&amp;", "&"), origin);
      if (url.origin !== origin.origin || !url.pathname.startsWith("/_next/static/")) {
        throw new Error(`Unexpected script URL ${url}.`);
      }
      return url;
    });
    const routeAsset = scripts.find((url) => pathname === "/admin/teams"
      ? /\/app\/admin\/teams\/page-[^/]+\.js$/.test(decodeURIComponent(url.pathname))
      : /\/app\/admin\/teams\/\[id\]\/workflow\/page-[^/]+\.js$/.test(decodeURIComponent(url.pathname)));
    if (!routeAsset) throw new Error(`Missing public route bundle for ${pathname}.`);
    for (const script of scripts) {
      const source = await get(script);
      if (pathname === "/admin/teams" && script === routeAsset) requireFullPage(source);
    }
  }
}

try {
  const args = process.argv.slice(2);
  let url;
  let teamId;
  while (args.length) {
    const option = args.shift();
    if (!["--url", "--team-id"].includes(option)) throw new Error(`Unknown option ${option}.`);
    const value = args.shift();
    if (!value || value.startsWith("--")) throw new Error(`Missing value for ${option}.`);
    if (option === "--url") url = value;
    else teamId = value;
  }
  if ((url || teamId) && (!url || !/^[1-9]\d*$/.test(teamId || ""))) {
    throw new Error("Public checks require --url URL --team-id POSITIVE_INTEGER.");
  }
  await checkBuild();
  if (url) await checkPublic(url, teamId);
  console.log(`Workflow release check passed${url ? ` for ${new URL(url).origin}` : ""}.`);
} catch (error) {
  console.error(`Workflow release check failed: ${error.message}`);
  process.exitCode = 1;
}
