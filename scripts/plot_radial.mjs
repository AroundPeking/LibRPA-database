#!/usr/bin/env node
// Uses the same strict parser and SVG renderer as the web basis viewer.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { parseRadial, radialSvg } from "../database/radial.mjs";

const [source, directory, ...flags] = process.argv.slice(2);
if (!source || !directory || flags.some(f => !["--tail", "--derivative", "--diagnostic-header"].includes(f))) {
  console.error("Usage: node scripts/plot_radial.mjs SOURCE.orb OUTPUT_DIRECTORY [--tail] [--derivative] [--diagnostic-header]");
  process.exitCode = 2;
} else {
  try {
    const bytes = await readFile(resolve(source));
    const sha = createHash("sha256").update(bytes).digest("hex");
    const radial = parseRadial(new TextDecoder("utf-8", { fatal: true }).decode(bytes), { allowHeaderMismatch: flags.includes("--diagnostic-header") });
    const output = resolve(directory);
    await mkdir(output, { recursive: true });
    const mode = flags.includes("--derivative") ? "derivative" : "raw";
    const tail = flags.includes("--tail");
    for (const l of new Set(radial.channels.map(c => c.l))) {
      const file = resolve(output, `radial-${sha.slice(0, 12)}-l${l}-${mode}${tail ? "-tail" : ""}.svg`);
      await writeFile(file, radialSvg(radial, l, { mode, tail }), { flag: "wx" });
      console.log(file);
    }
    const audit = { source_sha256: sha, element: radial.element, declared_counts: radial.counts, actual_counts: radial.actual_counts, header_mismatch: radial.header_mismatch, mesh: radial.mesh, dr_bohr: radial.dr, declared_cutoff_bohr: radial.cutoff, last_radius_bohr: radial.last_radius, mode, tail, samples_smoothed: false, samples_renormalized: false, scientific_acceptance_reassessed: false, channels: radial.channels.map(({ l, n, peak, endpoint, endpoint_slope, relative_endpoint }) => ({ l, original_n: n, peak, endpoint, endpoint_slope, relative_endpoint })) };
    await writeFile(resolve(output, `radial-${sha.slice(0, 12)}-${mode}${tail ? "-tail" : ""}.json`), JSON.stringify(audit, null, 2) + "\n", { flag: "wx" });
  } catch (error) {
    console.error(`Radial plotting stopped: ${error.message}. Original bytes were not changed.`);
    process.exitCode = 1;
  }
}
