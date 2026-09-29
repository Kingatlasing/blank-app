"""Builds the self-contained Three.js HTML page used to preview a model.

Three.js + OrbitControls are vendored into `vendor/` (fetched from the
official npm package, MIT licensed) instead of loaded from a CDN import map
at runtime. A CDN import map (the more common approach) silently breaks in
any environment that blocks that CDN host — the viewer renders a blank,
black canvas with no visible error, which looks exactly like "nothing
generated" even though the model data itself is fine.

The two vendored files are embedded as JS string literals and turned into
real ES modules client-side via `Blob` + `URL.createObjectURL` + dynamic
`import()` (`_LOADER`, below) — genuine module resolution, not textual
concatenation. Concatenating three.js and OrbitControls.js into one scope
was tried first and breaks: OrbitControls declares its own top-level
`_ray`/`_plane`/etc. helpers that collide with three.js's own internal
module-scope names once both are minified/unminified into the same scope.
Real `import`/`export` resolves by the *exported* name regardless of
internal renaming, so it doesn't have that problem, and blob URLs need no
network access — this works fully offline."""

from __future__ import annotations

import json
from pathlib import Path

Voxel = tuple[int, int, int, str]

_VENDOR_DIR = Path(__file__).parent / "vendor"
_THREE_JS = (_VENDOR_DIR / "three.module.min.js").read_text(encoding="utf-8")
_ORBIT_JS = (_VENDOR_DIR / "OrbitControls.js").read_text(encoding="utf-8")

# Turns the two vendored sources into real, isolated ES modules at runtime
# via blob URLs (no CDN, no network) and awaits them before the rest of the
# page's <script type="module"> body runs — top-level await is allowed
# there, so everything below can keep using `THREE.Foo` / `OrbitControls`
# exactly as a static `import` would have provided them.
_LOADER = """
const THREE_SRC = __THREE_SRC__;
const ORBIT_SRC = __ORBIT_SRC__;
const threeBlobUrl = URL.createObjectURL(new Blob([THREE_SRC], { type: "text/javascript" }));
const orbitPatched = ORBIT_SRC.replace("from 'three'", `from '${threeBlobUrl}'`);
const orbitBlobUrl = URL.createObjectURL(new Blob([orbitPatched], { type: "text/javascript" }));
const THREE = await import(threeBlobUrl);
const { OrbitControls } = await import(orbitBlobUrl);
"""


def _inject_loader(html: str) -> str:
    # substituted last so nothing in the (large) vendored source is ever
    # itself scanned for a __PLACEHOLDER__ token
    loader = _LOADER.replace("__THREE_SRC__", json.dumps(_THREE_JS))
    loader = loader.replace("__ORBIT_SRC__", json.dumps(_ORBIT_JS))
    return html.replace("__LOADER__", loader)


_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; overflow: hidden; background: #1b1f2a; }
  #info {
    position: absolute; top: 8px; left: 12px; color: #cfe8ff; font: 13px monospace;
    background: rgba(10,14,24,0.55); padding: 6px 10px; border-radius: 6px; pointer-events: none;
  }
</style>
</head>
<body>
<div id="info">__COUNT__ voxels — drag to orbit, scroll to zoom</div>
<script type="module">
__LOADER__

const VOXELS = __VOXELS__;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1b1f2a);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 2000);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio || 1);
document.body.appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const sun = new THREE.DirectionalLight(0xffffff, 0.75);
sun.position.set(40, 60, 30);
scene.add(sun);
const fill = new THREE.DirectionalLight(0x88aaff, 0.25);
fill.position.set(-30, 10, -30);
scene.add(fill);

// bounding box -> center camera / controls target
let minX=Infinity,minY=Infinity,minZ=Infinity,maxX=-Infinity,maxY=-Infinity,maxZ=-Infinity;
for (const v of VOXELS) {
  minX=Math.min(minX,v.x); maxX=Math.max(maxX,v.x);
  minY=Math.min(minY,v.y); maxY=Math.max(maxY,v.y);
  minZ=Math.min(minZ,v.z); maxZ=Math.max(maxZ,v.z);
}
if (!isFinite(minX)) { minX=minY=minZ=0; maxX=maxY=maxZ=1; }
const cx=(minX+maxX)/2, cy=(minY+maxY)/2, cz=(minZ+maxZ)/2;
const spanX=maxX-minX+1, spanY=maxY-minY+1, spanZ=maxZ-minZ+1;
const span = Math.max(spanX, spanY, spanZ, 1);

const geometry = new THREE.BoxGeometry(1, 1, 1);
// no `vertexColors: true` here: that flag expects a per-vertex `color`
// geometry attribute, which this BoxGeometry never has, and WebGL treats
// an enabled-but-unbound attribute as all-zero — that silently zeroed out
// every voxel's color (multiplying the correct per-instance color by 0),
// rendering solid black regardless of the real instanceColor data below.
// InstancedMesh.setColorAt's per-instance color applies automatically
// without this flag.
const material = new THREE.MeshLambertMaterial({ color: 0xffffff });
const mesh = new THREE.InstancedMesh(geometry, material, VOXELS.length);

const dummy = new THREE.Object3D();
const color = new THREE.Color();
for (let i = 0; i < VOXELS.length; i++) {
  const v = VOXELS[i];
  dummy.position.set(v.x - cx, v.y - cy, v.z - cz);
  dummy.updateMatrix();
  mesh.setMatrixAt(i, dummy.matrix);
  color.set(v.color);
  mesh.setColorAt(i, color);
}
if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
scene.add(mesh);

// thin edge lines per-voxel-group would be expensive; add a single wireframe
// ground grid instead so scale/orientation stays readable.
// divisions capped independent of model size — otherwise a large model's
// grid lines pack together so densely they read as a solid gray plane
// instead of a reference grid
const gridSize = Math.max(span * 2, 16);
const grid = new THREE.GridHelper(gridSize, Math.min(gridSize, 24), 0x3a4358, 0x272e3d);
grid.position.set(0, -spanY / 2 - 0.5, 0);
scene.add(grid);

camera.position.set(span * 1.4, span * 1.1, span * 1.4);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.update();

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
</script>
</body>
</html>
"""


def build_viewer_html(voxels: list[Voxel]) -> str:
    payload = [{"x": x, "y": y, "z": z, "color": c} for x, y, z, c in voxels]
    html = _TEMPLATE.replace("__VOXELS__", json.dumps(payload))
    html = html.replace("__COUNT__", str(len(voxels)))
    return _inject_loader(html)


_MESH_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; overflow: hidden; background: #1b1f2a; }
  #info {
    position: absolute; top: 8px; left: 12px; color: #cfe8ff; font: 13px monospace;
    background: rgba(10,14,24,0.55); padding: 6px 10px; border-radius: 6px; pointer-events: none;
  }
</style>
</head>
<body>
<div id="info">__COUNT__ triangles — drag to orbit, scroll to zoom</div>
<script type="module">
__LOADER__

const VERTS = __VERTS__;   // flat [x,y,z, x,y,z, ...]
const FACES = __FACES__;   // flat [i,j,k, i,j,k, ...]
const COLOR = __COLOR__;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1b1f2a);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.01, 200);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio || 1);
document.body.appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const sun = new THREE.DirectionalLight(0xffffff, 0.85);
sun.position.set(4, 6, 5);
scene.add(sun);
const fill = new THREE.DirectionalLight(0x88aaff, 0.3);
fill.position.set(-3, 1, -3);
scene.add(fill);

const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.Float32BufferAttribute(VERTS, 3));
geometry.setIndex(FACES);
geometry.computeVertexNormals();

// flat (faceted) shading — this is what makes the low-poly planes
// actually read as distinct facets, matching the reference sculpt style,
// instead of Three.js smoothing them into a fake-smooth blob.
// side: DoubleSide — this mesh is decimated from a hand-sculpted, edited
// reference (male_head.json), and single-sided rendering (the default)
// silently culls any triangle whose winding doesn't match its neighbors,
// which shows up as a solid-black hole punched through the face wherever
// that happens (reported by a user as "holes on the right side of the
// face"). Double-siding costs nothing visible on a closed, low-poly head
// and removes this whole class of bug regardless of any future edits to
// the underlying mesh data.
const material = new THREE.MeshStandardMaterial({ color: COLOR, flatShading: true, roughness: 0.85, side: THREE.DoubleSide });
const mesh = new THREE.Mesh(geometry, material);
scene.add(mesh);

const wire = new THREE.LineSegments(
  new THREE.WireframeGeometry(geometry),
  new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.12 })
);
scene.add(wire);

geometry.computeBoundingSphere();
const radius = geometry.boundingSphere ? geometry.boundingSphere.radius : 1;

camera.position.set(radius * 2.2, radius * 1.3, radius * 2.2);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.update();

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
</script>
</body>
</html>
"""


def build_mesh_viewer_html(vertices: list[tuple[float, float, float]],
                            faces: list[tuple[int, int, int]], color: str = "#E0AC85") -> str:
    """The mesh-tier counterpart to `build_viewer_html`: renders a real
    vertex/face polygon mesh (flat-shaded, so the low-poly facets stay
    visible) instead of instanced voxel cubes."""
    flat_verts = [coord for vertex in vertices for coord in vertex]
    flat_faces = [idx for face in faces for idx in face]
    html = _MESH_TEMPLATE.replace("__VERTS__", json.dumps(flat_verts))
    html = html.replace("__FACES__", json.dumps(flat_faces))
    html = html.replace("__COLOR__", json.dumps(color))
    html = html.replace("__COUNT__", str(len(faces)))
    return _inject_loader(html)
