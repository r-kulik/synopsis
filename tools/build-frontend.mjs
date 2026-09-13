import { build } from "esbuild";
import { cp, mkdir, readFile, writeFile } from "node:fs/promises";

await mkdir("frontend/vendor/katex", { recursive: true });
const bundle = await build({
  entryPoints: ["tools/markdown-entry.js"],
  outfile: "frontend/markdown.js",
  bundle: true,
  format: "esm",
  target: ["chrome110", "edge110"],
  minify: true,
  legalComments: "eof",
  metafile: true,
});
await cp("node_modules/katex/dist/fonts", "frontend/vendor/katex/fonts", {
  recursive: true,
});
await cp(
  "node_modules/katex/dist/katex.min.css",
  "frontend/vendor/katex/katex.min.css",
);
const packages = [
  ...new Set(
    Object.keys(bundle.metafile.inputs)
      .map((path) => path.match(/^(.*node_modules\/(?:@[^/]+\/)?[^/]+)\//)?.[1])
      .filter(Boolean),
  ),
].sort();
const licenses = [];
for (const root of packages) {
  const meta = JSON.parse(await readFile(`${root}/package.json`, "utf8"));
  let license = "";
  for (const file of [
    "license",
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "license.txt",
    "License",
  ]) {
    try {
      license = await readFile(`${root}/${file}`, "utf8");
      break;
    } catch {}
  }
  // remark-math's npm tarball omits the repository-root MIT license.
  if (!license && meta.name === "remark-math")
    license = await readFile("tools/licenses/remark-math.txt", "utf8");
  if (!license)
    throw new Error(`Missing license for bundled package: ${meta.name}`);
  licenses.push(`${meta.name} ${meta.version}\n${license}`);
}
await writeFile("frontend/vendor/LICENSES.txt", licenses.join("\n\n---\n\n"));
console.log("Built local Markdown/KaTeX/CodeMirror bundle and fonts.");
