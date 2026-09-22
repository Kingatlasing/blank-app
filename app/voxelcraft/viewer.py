"""Builds the self-contained Three.js HTML page used to preview a model."""

from __future__ import annotations

import json

Voxel = tuple[int, int, int, str]

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
<script type="importmap">
{ "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
} }
</script>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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
const material = new THREE.MeshLambertMaterial({ vertexColors: true, color: 0xffffff });
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
    return html


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
<script type="importmap">
{ "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
} }
</script>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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
// instead of Three.js smoothing them into a fake-smooth blob
const material = new THREE.MeshStandardMaterial({ color: COLOR, flatShading: true, roughness: 0.85 });
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
    return html
