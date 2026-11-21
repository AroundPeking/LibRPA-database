import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { parseStructure, reciprocalCell, brillouinZone, getSpecialPoints, structureScene, sceneSvg, structurePreview, structureFingerprint, groupStructureFiles, structureLabels, loadStructureFile } from "../database/structure.mjs";
import { renderMaterial } from "../database/details.mjs";

const dot = (a,b) => a.reduce((s,x,i) => s+x*b[i],0);
const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const det = a => dot(a[0],cross(a[1],a[2]));
const close = (a,b,tol=1e-8) => assert.ok(Math.abs(a-b) < tol, `${a} != ${b}`);
const cube = [[1,0,0],[0,1,0],[0,0,1]];
const mgoBytes = readFileSync(new URL("fixtures/structures/mgo.STRU", import.meta.url));
const mgo = parseStructure(mgoBytes.toString(), "stru");
const volume = faces => faces.reduce((s,f) => s + f.slice(1,-1).reduce((v,p,i) => v+Math.abs(dot(f[0],cross(p,f[i+2])))/6,0),0);

test("MgO fixture is the exact archived two-atom FCC input", () => {
  // data/calculations/3d/MgO/mgo-paper-fix_gap/inputs/STRU, archive 339cc4610e6de418f9794752e8a235d3caafc07d.
  assert.equal(createHash("sha256").update(mgoBytes).digest("hex"), "eba0d69606352a1b4d7eba14ad7f8d5ebc1771ce2ccdf97b7df4e94471cb436c");
  assert.deepEqual(mgo.sites.map(s=>s.element), ["Mg","O"]);
  close(mgo.cell[0][0], 2.1055*1.8897162*0.529177210903);
  mgo.sites[1].position.forEach(x=>close(x,mgo.cell[0][0]));
  const zone = brillouinZone(mgo.cell);
  assert.equal(zone.vertices.length,24);
  assert.equal(zone.faces.length,14);
  assert.equal(zone.faces.filter(f=>f.length===6).length,8);
  assert.equal(zone.faces.filter(f=>f.length===4).length,6);
  close(volume(zone.faces),Math.pow(2*Math.PI,3)/Math.abs(det(mgo.cell)));
});

test("FCC special points match the archived MgO band-path coordinates and boundary types", () => {
  const zone = brillouinZone(mgo.cell);
  const expected = { X: [.5,0,.5], W: [.5,.25,.75], K: [.375,.375,.75], L: [.5,.5,.5], U: [.625,.25,.625] };
  assert.deepEqual(zone.specialPoints.map(p=>p.label),["Γ","X","W","K","L","U"]);
  const faceCounts = { "Γ": 0, X: 1, W: 3, K: 2, L: 1, U: 2 };
  for (const p of zone.specialPoints) {
    if (p.label !== "Γ") assert.deepEqual(p.fractional,expected[p.label]);
    let incident = 0;
    for (const f of zone.faces) {
      const n = cross(f[1].map((v,i)=>v-f[0][i]),f[2].map((v,i)=>v-f[0][i]));
      const distance = Math.abs(dot(n,p.position)-dot(n,f[0]))/Math.hypot(...n);
      if (distance < 1e-8) incident++;
    }
    assert.equal(incident,faceCounts[p.label],p.label);
  }
});

test("special points use the rotated and signed input reciprocal basis", () => {
  const rotate = v => [Math.cos(.37)*v[0]-Math.sin(.37)*v[1],Math.sin(.37)*v[0]+Math.cos(.37)*v[1],v[2]];
  const original = getSpecialPoints(mgo.cell);
  const changed = getSpecialPoints(mgo.cell.map((v,i)=>rotate(v.map(x=>i===1?-x:x))));
  for (let i=0;i<original.length;i++) {
    assert.equal(changed[i].label,original[i].label);
    rotate(original[i].position).forEach((v,j)=>close(v,changed[i].position[j]));
    changed[i].fractional.forEach((v,j)=>close(v,original[i].fractional[j]*(j===1?-1:1)));
  }
});

test("common primitive lattices have their own special points inside their zones", () => {
  const cases = [
    [cube,["Γ","X","M","R"]],
    [[[.5,.5,-.5],[-.5,.5,.5],[.5,-.5,.5]],["Γ","H","N","P"]],
    [[[0,0,4],[2,0,0],[0,2,0]],["Γ","X","M","Z","R","A"]],
    [[[0,0,4],[2,0,0],[0,3,0]],["Γ","X","Y","Z","S","T","U","R"]],
    [[[2,0,0],[1,Math.sqrt(3),0],[0,0,20]],["Γ","M","K","A","L","H"]],
    [[[2,0,0],[.3,3,0],[.1,.2,4]],["Γ"]],
  ];
  for(const [cell,labels] of cases) {
    const points=getSpecialPoints(cell), b=reciprocalCell(cell);
    assert.deepEqual(points.map(p=>p.label),labels);
    for(const p of points) {
      for(let i=-2;i<=2;i++) for(let j=-2;j<=2;j++) for(let k=-2;k<=2;k++) {
        const g=b[0].map((_,n)=>i*b[0][n]+j*b[1][n]+k*b[2][n]);
        assert.ok(dot(g,p.position)<=dot(g,g)/2+1e-8,p.label);
      }
    }
  }
});

test("reciprocal rows satisfy ai·bj = 2π δij for skew and left-handed cells", () => {
  for (const cell of [mgo.cell, [[1,0,0],[.3,2,0],[.2,.6,3]], [cube[1],cube[0],cube[2]]]) {
    const b=reciprocalCell(cell);
    cell.forEach((a,i)=>b.forEach((v,j)=>close(dot(a,v),i===j?2*Math.PI:0)));
  }
});

test("simple cubic and BCC have the analytic zone topology and reciprocal volume", () => {
  const cells = [cube, [[-.5,.5,.5],[.5,-.5,.5],[.5,.5,-.5]]];
  for (const [i,cell] of cells.entries()) {
    const z=brillouinZone(cell);
    assert.equal(z.faces.length,i?12:6);
    assert.equal(z.vertices.length,i?14:8);
    close(volume(z.faces),Math.pow(2*Math.PI,3)/Math.abs(det(cell)),1e-7);
  }
});

test("zone is unchanged by large integer shears of the same lattice", () => {
  const z=brillouinZone([[1,0,0],[7,1,0],[35,5,1]]);
  assert.equal(z.faces.length,6);
  assert.equal(z.vertices.length,8);
  z.vertices.forEach(v=>v.forEach(x=>close(Math.abs(x),Math.PI)));
});

test("anisotropic slab and triclinic zones conserve volume and obey lattice bisectors", () => {
  for (const cell of [[[3,0,0],[-1.5,2.598076211,0],[0,0,24]], [[3,.2,0],[1,2.5,.4],[.1,.2,4]]]) {
    const z=brillouinZone(cell), b=reciprocalCell(cell);
    close(volume(z.faces),Math.pow(2*Math.PI,3)/Math.abs(det(cell)),1e-7);
    for (let i=-3;i<=3;i++) for(let j=-3;j<=3;j++) for(let k=-3;k<=3;k++) {
      const g=b[0].map((_,n)=>i*b[0][n]+j*b[1][n]+k*b[2][n]);
      for(const v of z.vertices) assert.ok(dot(g,v)<=dot(g,g)/2+1e-8);
    }
    for(const v of z.vertices) assert.ok(z.vertices.some(w=>Math.hypot(...v.map((x,i)=>x+w[i]))<1e-7));
  }
});

test("ABACUS coordinate modes convert into the same Å positions", () => {
  const source = mode => `LATTICE_CONSTANT\n2\nLATTICE_VECTORS\n1 0 0\n0 1 0\n0 0 1\nATOMIC_POSITIONS\n${mode}\nSi\n0\n1\n`;
  const direct=parseStructure(source("Direct")+".5 .5 .5 0 0 0 # flags", "stru");
  for(const [mode,coord] of [["Cartesian", ".5"],["Cartesian_au","1"],["Cartesian_angstrom","0.529177210903"]]) {
    const s=parseStructure(source(mode)+`${coord} ${coord} ${coord}`,"stru");
    assert.deepEqual(s,direct);
  }
});

test("FHI-aims mixed Cartesian and fractional sites, comments and D exponents", () => {
  const s=parseStructure("# example\nlattice_vector 2 0 0\nlattice_vector 0 3 0\nlattice_vector 0 0 4\natom_frac .5 .5 .5 Si\natom 1D0 1.5 2 O\ninitial_moment 0", "aims");
  assert.deepEqual(s.sites.map(s=>s.position),[[1,1.5,2],[1,1.5,2]]);
});

test("POSCAR selective dynamics and negative-volume scales", () => {
  const s=parseStructure("Si\n-8\n1 0 0\n0 1 0\n0 0 1\nSi\n1\nSelective dynamics\nDirect\n.5 .5 .5 T T T", "poscar");
  assert.deepEqual(s.cell,[[2,0,0],[0,2,0],[0,0,2]]);
  assert.deepEqual(s.sites[0].position,[1,1,1]);
});

test("unsupported, incomplete, nonfinite and singular structures fail explicitly", () => {
  for(const [text,format] of [["","stru"],["","cif"],["atom 0 0 0 H","aims"],["lattice_vector 1 0 0\nlattice_vector 2 0 0\nlattice_vector 0 0 1\natom 0 0 0 H","aims"],[mgoBytes.toString().replace("0.5 0.5 0.5", "NaN 0.5 0.5"),"stru"],[mgoBytes.toString().replace("Direct","Cartesian_angstrom_center_xy"),"stru"],[mgoBytes.toString().replace("O\n0.0\n1","O\n0.0\n2"),"stru"]]) assert.throws(()=>parseStructure(text,format));
});

test("scene wraps atoms and adds boundary images without changing input", () => {
  const s={cell:cube,sites:[{element:"Si",position:[1,0,0]}]}, before=JSON.stringify(s);
  const scene=structureScene(s);
  assert.equal(scene.atoms.length,8);
  assert.equal(scene.edges.length,12);
  assert.equal(JSON.stringify(s),before);
  assert.match(sceneSvg(scene),/aria-label="Crystal structure"/);
  assert.doesNotMatch(sceneSvg(scene),/NaN|Infinity/);
});

test("each downloadable structure has its own preview below the file row", () => {
  const files=[{path:"data/solid__STRU",label:"<solid>"},{path:"data/molecule__STRU"}];
  const html=structurePreview(files[0]);
  assert.match(html,/data-structure-path="data\/solid__STRU"/);
  assert.doesNotMatch(html,/<select/);
  assert.equal(structurePreview({path:"data/STRU.cif"}),"");
  const page=renderMaterial({id:"test",material:"MgO",dimension:"3d",summary:{},files:{inputs:files}},[]);
  assert.match(page,/structure-preview/);
  assert.match(page,/data-preview="data\/solid__STRU"/);
  assert.match(page,/&lt;solid&gt;/);
  assert.ok(page.indexOf('data-preview="data/solid__STRU"') < page.indexOf('data-structure-path="data/solid__STRU"'));
});

test("a file that repeats an earlier structure keeps its row but not a second preview", () => {
  const one={path:"data/scf/STRU",sha256:"a".repeat(64),label:"scf / STRU"};
  const again={path:"data/band/STRU",sha256:"a".repeat(64),label:"band / STRU"};
  const other={path:"data/atom/STRU",sha256:"b".repeat(64),label:"atom / STRU"};
  const groups=groupStructureFiles([one,again,other]);
  assert.deepEqual(groups.map(g=>g.preview),[true,false,true]);
  assert.equal(groups[1].sameAs.name,"scf / STRU");
  assert.equal(groups[1].sameAs.reason,"sha256");
  // A non-structure input is passed through untouched.
  assert.equal(groupStructureFiles([{path:"data/INPUT",sha256:"c".repeat(64)}])[0].preview,false);

  const page=renderMaterial({id:"test",material:"MoS2",dimension:"2d",summary:{},files:{inputs:[one,again,other]}},[]);
  assert.equal((page.match(/data-structure-path=/g)||[]).length,2);
  assert.equal((page.match(/class="structure-duplicate"/g)||[]).length,1);
  assert.match(page,/Same structure as <code>scf \/ STRU<\/code>/);
  // Two files both labelled "STRU" must be distinguishable in the pointer.
  const sameName = [
    {path:"data/c/inputs/calculation__STRU",sha256:"a".repeat(64),label:"STRU"},
    {path:"data/c/inputs/calculation__pbe_path__STRU",sha256:"a".repeat(64),label:"STRU"},
  ];
  const names = structureLabels(sameName);
  assert.notEqual(names.get(sameName[0].path), names.get(sameName[1].path));
  assert.match(renderMaterial({id:"t",material:"B",dimension:"2d",summary:{},files:{inputs:sameName}},[]), /Same structure as <code>calculation \/ STRU<\/code>/);
  assert.match(page,/band \/ STRU/,"the repeated file is still named in the pointer");
  assert.match(page,/data-preview="data\/band\/STRU"/,"its download row survives");
  // Both rows are still listed in display order.
  assert.ok(page.indexOf("data-preview=\"data/scf/STRU\"") < page.indexOf("data-preview=\"data/band/STRU\""));
});

test("the preview fingerprint ignores site order and sub-1e-4 noise only", () => {
  const base={cell:[[3,0,0],[0,3,0],[0,0,30]],sites:[{element:"Mo",position:[0,0,1]},{element:"S",position:[0,0,2]}]};
  const reordered={cell:base.cell,sites:[...base.sites].reverse()};
  const nudged={cell:[[3.00001,0,0],[0,3,0],[0,0,30]],sites:base.sites};
  const vacuum={cell:[[3,0,0],[0,3,0],[0,0,40]],sites:base.sites};
  const permuted={cell:[base.cell[1],base.cell[0],base.cell[2]],sites:base.sites};
  assert.equal(structureFingerprint(base),structureFingerprint(reordered));
  assert.equal(structureFingerprint(base),structureFingerprint(nudged));
  // A different cell is never treated as the same crystal.
  assert.notEqual(structureFingerprint(base),structureFingerprint(vacuum));
  assert.notEqual(structureFingerprint(base),structureFingerprint(permuted));
  assert.deepEqual(JSON.parse(JSON.stringify(base)).sites.length,2,"fingerprinting does not mutate its input");
});

test("source is parsed only after SHA verification; mirror retries the same identity", async () => {
  const file={path:"data/STRU",sha256:createHash("sha256").update(mgoBytes).digest("hex"),tier:"referenced",external_url:"https://huggingface.co/STRU",external_url_backup:"https://hf-mirror.com/STRU"};
  const calls=[];
  const fetcher=async url=>{calls.push(url);return new Response(calls.length===1?"corrupt":mgoBytes);};
  assert.deepEqual(await loadStructureFile(file,fetcher),mgo);
  assert.deepEqual(calls,[file.external_url,file.external_url_backup]);
  await assert.rejects(loadStructureFile(file,async()=>new Response("corrupt")),/SHA-256 mismatch/);
  await assert.rejects(loadStructureFile({...file,sha256:null},fetcher),/Missing structure SHA/);
});
