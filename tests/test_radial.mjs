import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { parseRadial, radialSvg, radialSection } from "../database/radial.mjs";

const fixture = `Element H\nRadius Cutoff(a.u.) 2\nLmax 1\nNumber of Sorbital--> 1\nNumber of Porbital--> 1\nSUMMARY  END\nMesh 5\ndr 0.5\nType L N\n0 0 0\n1 0.5 0 -0.1 0\nType L N\n0 1 0\n0 0.2 0.3 0.1 0\n`;

test("radial parser preserves all original l/N samples and grid", () => {
  const r = parseRadial(fixture);
  assert.equal(r.channels.length, 2);
  assert.deepEqual(r.channels[0].values, [1, 0.5, 0, -0.1, 0]);
  assert.equal(r.last_radius, 2);
  assert.equal(r.channels[1].l, 1);
  assert.equal(r.channels[0].endpoint, 0);
  assert.equal(r.channels[0].derivative[0], -1);
  assert.equal(r.channels[0].endpoint_slope, 0.4);
});
test("one l per plot, no smoothing, full samples retained", () => {
  const svg = radialSvg(parseRadial(fixture), 0);
  assert.equal((svg.match(/data-channel=/g) || []).length, 1);
  assert.match(svg, /l=0/);
  assert.match(svg, /original stored amplitude/);
  assert.match(radialSvg(parseRadial(fixture), 1, { tail: true, mode: "derivative" }), /finite difference/);
  assert.match(radialSvg(parseRadial(fixture), 1, { selected: [] }), /r \(bohr\)/);
  assert.doesNotMatch(radialSvg(parseRadial(fixture), 1, { selected: [] }), /data-channel=/);
});
test("malformed counts, duplicate N, nonfinite and truncated data are rejected", () => {
  for (const text of [fixture.replace("1 0.5 0 -0.1 0", "1 0.5 0 NaN 0"), fixture.replace("1 0.5 0 -0.1 0", "1 0.5"), fixture.replace("0 1 0", "0 0 0"), fixture.replace("Sorbital--> 1", "Sorbital--> 2")]) assert.throws(() => parseRadial(text));
});
test("header inconsistency is a labelled diagnostic mode, never a silent repair", () => {
  const mismatch = fixture.replace("Sorbital--> 1", "Sorbital--> 2");
  assert.throws(() => parseRadial(mismatch));
  const diagnostic = parseRadial(mismatch, { allowHeaderMismatch: true });
  assert.equal(diagnostic.header_mismatch, true);
  assert.equal(diagnostic.counts[0], 2);
  assert.equal(diagnostic.actual_counts[0], 1);
  assert.equal(diagnostic.channels.length, 2);
});

test("real Al physical orbitals retain all three l groups and eight radial functions", () => {
  const p = new URL("../data/elements/Al/orbitals/8d7e5a192b52a13b21df4cc2999fad022fb1e0de4b6d080c857b65b6085c4785.orb", import.meta.url);
  const r = parseRadial(readFileSync(p, "utf8"));
  assert.equal(r.mesh, 1001);
  assert.equal(r.channels.length, 8);
  assert.deepEqual([...new Set(r.channels.map(c => c.l))], [0, 1, 2]);
});
test("同一 l 的 N 开关不改变原编号或引入其他 l", () => {
  const text = fixture.replace("Sorbital--> 1", "Sorbital--> 2") + "Type L N\n0 0 1\n0.8 0.3 -0.2 0.05 0\n";
  const radial = parseRadial(text);
  const svg = radialSvg(radial, 0, { selected: [1] });
  assert.deepEqual([...svg.matchAll(/data-channel="(\d+)"/g)].map(match => Number(match[1])), [1]);
  assert.match(svg, /original N=1/);
  assert.doesNotMatch(svg, /original N=0|l=1/);
  assert.equal((svg.match(/<path data-channel=/g) || []).length, 1);
  assert.equal(([...svg.matchAll(/<path data-channel="1" d="([^"]+)"/g)][0][1].match(/[ML]/g) || []).length, radial.mesh);
});
test("导数尾部仅取原网格最后 20%，无插值或平滑曲线路径", () => {
  const radial = parseRadial(fixture);
  const raw = radialSvg(radial, 0);
  const tail = radialSvg(radial, 0, { tail: true, mode: "derivative" });
  const points = svg => [...svg.matchAll(/<path data-channel="0" d="([^"]+)"/g)][0][1];
  assert.equal((points(raw).match(/[ML]/g) || []).length, radial.mesh);
  assert.equal((points(tail).match(/[ML]/g) || []).length, radial.mesh - Math.floor((radial.mesh - 1) * 0.8));
  assert.doesNotMatch(points(raw), /[CQSA]/);
  assert.doesNotMatch(points(tail), /[CQSA]/);
  assert.match(tail, /last 20% of original grid/);
  assert.match(tail, /finite difference/);
});
for (const [element, headerElement, hash, mesh] of [
  ["F", "O", "c3b51d5c5f8553e32bac249341edaa4f3abdfd58e7def0678dddfbd457dd926b", 801],
  ["Li", "Ne", "5f05d62bec8b22ae065ca065242776898c5587711fcfc4826a67b57eaf570c87", 1001],
]) test(`${element} 原 ABF 的错误头只允许显式诊断，保留 800 个原通道`, () => {
  const bytes = readFileSync(new URL(`../data/elements/${element}/auxiliary/${hash}.abfs`, import.meta.url));
  assert.equal(createHash("sha256").update(bytes).digest("hex"), hash);
  const text = bytes.toString("utf8");
  assert.throws(() => parseRadial(text));
  const radial = parseRadial(text, { allowHeaderMismatch: true });
  assert.equal(radial.element, headerElement);
  assert.notEqual(radial.element, element);
  assert.equal(radial.header_mismatch, true);
  assert.equal(radial.mesh, mesh);
  assert.deepEqual(radial.counts, { 0: 10, 1: 10, 2: 10, 3: 9, 4: 8, 5: 7, 6: 6, 7: 5 });
  assert.deepEqual(radial.actual_counts, Object.fromEntries(Array.from({ length: 8 }, (_, l) => [l, 100])));
  assert.equal(radial.channels.length, 800);
  for (let l = 0; l < 8; l += 1) {
    assert.deepEqual(radial.channels.filter(channel => channel.l === l).map(channel => channel.n), Array.from({ length: 100 }, (_, n) => n));
    const svg = radialSvg(radial, l);
    const paths = [...svg.matchAll(/<path data-channel="(\d+)" d="([^"]+)"/g)];
    assert.equal(paths.length, 100);
    assert.ok(paths.every(match => (match[2].match(/[ML]/g) || []).length === mesh));
    assert.match(svg, new RegExp(`${headerElement} l=${l}`));
    assert.match(svg, /original N=99/);
    assert.match(svg, /Header metadata differs from the parsed channel blocks/);
    assert.match(svg, /preserves the source header and every stored sample/);
  }
  assert.equal(createHash("sha256").update(bytes).digest("hex"), hash);
});
test("plot section distinguishes physical NAO/ABF and explains display scope", () => {
  const html = radialSection({ element: "Al", files: [{ role: "nao", path: "data/elements/Al/orbitals/a.orb", sha256: "a".repeat(64) }, { role: "abf", path: "data/elements/Al/auxiliary/a.abfs", sha256: "b".repeat(64) }] });
  assert.match(html, /Physical NAO/);
  assert.match(html, /Auxiliary basis/);
  assert.match(html, /without smoothing/i);
  assert.match(html, /Click to load radial plots/);
  assert.match(html, /Periodic overlap, RI conditioning, EXX\/GW accuracy, and basis completeness are separate/);
});
