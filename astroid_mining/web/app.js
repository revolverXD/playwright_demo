// 3D view of the fleet, driven only by the public API: no data is baked in here.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const REFRESH_MS = 5000;
const SITE_RING = 48;
const RELAY_RING = 22;
// rad/s, deliberately slow: a belt orbit ~21 min, a relay orbit ~8 min, a robot lap of its asteroid ~52 s
const SPIN = { site: 0.005, relay: 0.013, robot: 0.12 };

const ROBOT_COLOR = {
  ACTIVE: '#46e08a', PAUSED: '#ffd166', RETURNING: '#6ec6ff', CHARGING: '#b28dff',
  IDLE: '#8d97a5', STOPPED: '#5f6a78', FAULT: '#ff5566', MAINTENANCE: '#ffb347', LOST_LINK: '#38506b',
};
const RELAY_COLOR = { OPERATIONAL: '#8fd8ff', STANDBY: '#4f6f96', OFFLINE: '#ff5566', DECOMMISSIONED: '#414b57' };
const LINK_COLOR = { ESTABLISHED: '#2ee6c0', PROVISIONING: '#ffd166', DEGRADED: '#ff5566', FAULT: '#ff5566', DISABLED: '#39434f' };
const ADJ_COLOR = { FULL: '#ffd166', '2_WAY': '#6ec6ff', INIT: '#6ec6ff', DOWN: '#ff5566' };
const LINK_OPACITY = { PRIMARY: 0.95, SECONDARY: 0.5, SURVEY: 0.3, COLD_STANDBY: 0.18 };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
const fmt = (n, digits = 1) => (n === null || n === undefined || Number.isNaN(n) ? '-' : Number(n).toFixed(digits));

const token = { value: null, user: null, role: null, expiresAt: null };

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'content-type': 'application/json', ...(token.value ? { authorization: 'Bearer ' + token.value } : {}), ...options.headers },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({})))?.detail;
    const error = new Error(detail || `${response.status} ${path}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

// ---------- three.js scaffolding ----------
const host = $('scene');
let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
} catch (e) {
  $('err').textContent = 'this browser has no WebGL: ' + e.message;
}

const scene = new THREE.Scene();
scene.background = new THREE.Color('#05070c');
const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 6000);
camera.position.set(0, 52, 104);

let controls = null;
if (renderer) {
  renderer.setPixelRatio(Math.devicePixelRatio || 1);
  host.appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 12;
  controls.maxDistance = 400;
  scene.add(new THREE.AmbientLight(0x8899bb, 0.9));
  const sun = new THREE.DirectionalLight(0xfff2d0, 1.5);
  sun.position.set(60, 40, 20);
  scene.add(sun);
  scene.add(stars());
  for (const [ring, color] of [[SITE_RING, '#1b2a3d'], [RELAY_RING, '#3a2f18']]) {
    const guide = new THREE.Mesh(new THREE.TorusGeometry(ring, 0.06, 6, 160), new THREE.MeshBasicMaterial({ color }));
    guide.rotation.x = Math.PI / 2;
    scene.add(guide);
  }
}

function stars() {
  const count = 1200;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const r = 900 + Math.random() * 900;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions.set([r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)], i * 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  return new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0x6f86a8, size: 1.6, sizeAttenuation: false }));
}

// ---------- the fleet layer, rebuilt on every poll ----------
const fleet = new THREE.Group();
scene.add(fleet);
let sites = [];
let relays = [];
let robots = [];
let edges = [];
let pickable = [];

function disposeFleet() {
  fleet.traverse((object) => {
    object.geometry?.dispose?.();
    object.material?.dispose?.();
  });
  fleet.clear();
  sites = []; relays = []; robots = []; edges = []; pickable = [];
}

function addMesh(geometry, color, info, extra = {}) {
  const material = new THREE.MeshLambertMaterial({ color, emissive: extra.emissive || 0x000000, flatShading: !!extra.flat });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.info = info;
  fleet.add(mesh);
  pickable.push(mesh);
  return mesh;
}

function addEdge(a, b, color, opacity, info) {
  const geometry = new THREE.BufferGeometry().setFromPoints([a, b]);
  const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
  line.userData.info = info;
  fleet.add(line);
  pickable.push(line);
  edges.push({ line, a, b });
  return line;
}

async function snapshot() {
  const [summary, clock, siteList, relayList, netList] = await Promise.all([
    api('/api/v1/fleet/summary'),
    api('/api/v1/clock'),
    api('/api/v1/sites'),
    api('/api/v1/satellites'),
    api('/api/v1/relay-nets'),
  ]);
  const bases = {};
  for (const site of siteList.sites) {
    bases[site.id] = (await api(`/api/v1/sites/${site.id}`)).baseStation;
  }
  return { summary, clock, sites: siteList.sites, relays: relayList.satellites, nets: netList.relayNets, bases };
}

function roleOf(nets, relayId) {
  for (const net of nets) {
    if (net.ds?.satelliteId === relayId) { return { role: 'DS', net }; }
    if (net.bds?.satelliteId === relayId) { return { role: 'BDS', net }; }
  }
  return { role: null, net: null };
}

function build(data) {
  disposeFleet();
  const sorted = (list) => [...list].sort((a, b) => String(a.id).localeCompare(String(b.id)));

  const angleOf = (index, total) => (index / Math.max(1, total)) * Math.PI * 2;

  for (const [index, site] of sorted(data.sites).entries()) {
    const base = data.bases[site.id] || {};
    const production = base.summary?.productionRateTph ?? site.summary?.productionRateTph ?? 0;
    const radius = 2.4 + Math.min(6, production / 6);
    const healthy = site.status === 'OPERATIONAL' ? Math.max(0, Math.min(1, site.healthScore ?? 0)) : 0;
    const color = site.status === 'OPERATIONAL' ? `hsl(${healthy * 128} 65% ${34 + healthy * 18}%)` : '#39424e';
    const angle = angleOf(index, data.sites.length);
    const node = addMesh(
      new THREE.IcosahedronGeometry(radius, 1),
      color,
      `<b>${esc(site.name)}</b> ${esc(site.designation)}<br>${esc(site.status)} · health ${fmt((site.healthScore ?? 0) * 100, 0)}%<br>` +
      `host body ${esc(site.hostBody)}<br>producing ${fmt(production)} t/h · ore ${fmt(site.summary?.rawOreStockTons, 0)} t · refined ${fmt(site.summary?.refinedStockTons, 0)} t<br>` +
      `base station ${esc(base.model || '-')}`,
      { flat: true },
    );
    sites.push({ node, id: site.id, radius, base: angle, speed: SPIN.site, y: Math.sin(index * 2.1) * 5 });
  }

  for (const [index, relay] of sorted(data.relays).entries()) {
    const election = roleOf(data.nets, relay.id);
    const peer = data.nets.flatMap((net) => net.adjacencies).find((row) => row.satelliteId === relay.id);
    const node = addMesh(
      new THREE.OctahedronGeometry(1.8),
      RELAY_COLOR[relay.status] || '#8899aa',
      `<b>${esc(relay.name)}</b> ${esc(relay.operator || '')}<br>${esc(relay.status)} · health ${fmt((relay.healthScore ?? 0) * 100, 0)}%<br>` +
      `serving ${relay.connectedSites} site(s)<br>role on ${esc(election.net?.name || 'no net')}: ${esc(election.role || 'DROther')}` +
      (peer ? `<br>adjacency ${esc(peer.state)} · hold timer ${fmt(peer.holdTimeS)}s` : ''),
    );
    const angle = angleOf(index, data.relays.length);
    relays.push({ node, id: relay.id, name: relay.name, base: angle, speed: SPIN.relay });
    if (election.role === 'DS' || election.role === 'BDS') {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(3.1, 0.13, 8, 60),
        new THREE.MeshBasicMaterial({ color: election.role === 'DS' ? '#ffd166' : '#cfd8e3' }),
      );
      ring.rotation.x = Math.PI / 2;
      node.add(ring);
    }
  }

  const siteNode = new Map(sites.map((s) => [s.id, s]));
  const relayNode = new Map(relays.map((r) => [r.id, r]));
  const at = (entry) => entry.node.position;

  for (const site of data.sites) {
    const from = siteNode.get(site.id);
    if (!from) { continue; }
    for (const link of data.bases[site.id]?.satelliteLinks?.links || []) {
      const to = relayNode.get(link.satelliteId);
      if (!to) { continue; }
      const color = link.status === 'ESTABLISHED' ? LINK_COLOR.ESTABLISHED : (LINK_COLOR[link.status] || '#39434f');
      addEdge(
        at(from),
        at(to),
        color,
        LINK_OPACITY[link.role] ?? 0.35,
        `${esc(link.role)} uplink ${esc(site.name)} → ${esc(to.name)}<br>${esc(link.status)} · band ${esc(link.band)} · ${fmt(link.sharePct, 0)}% · missed ${link.missedReports ?? 0}`,
      );
    }
    for (const [robotIndex, robot] of (data.bases[site.id]?.fleet?.roster || []).entries()) {
      const body = addMesh(
        new THREE.BoxGeometry(0.8, 0.8, 0.8),
        ROBOT_COLOR[robot.state] || '#8d97a5',
        `<b>${esc(robot.designation)}</b> ${esc(robot.class)}<br>state ${esc(robot.state)} · status ${esc(robot.status)}<br>` +
        `battery ${fmt(robot.batteryPct, 0)}% · health ${fmt(robot.healthPct, 0)}%`,
      );
      robots.push({
        node: body, parent: from, base: robotIndex * 1.9, speed: SPIN.robot + robotIndex * 0.02,
        radius: from.radius + 2.2 + (robotIndex % 3) * 0.9,
      });
    }
  }

  for (const net of data.nets) {
    const live = net.adjacencies.map((peer) => [peer, relayNode.get(peer.satelliteId)]).filter(([, node]) => node);
    for (let i = 0; i < live.length; i += 1) {
      for (let j = i + 1; j < live.length; j += 1) {
        const [pa, na] = live[i];
        const [pb, nb] = live[j];
        const down = pa.state !== 'FULL' || pb.state !== 'FULL';
        addEdge(
          at(na),
          at(nb),
          down ? ADJ_COLOR.DOWN : ADJ_COLOR[pa.state] || ADJ_COLOR.FULL,
          down ? 0.22 : 0.7,
          `adjacency on ${esc(net.name)} (${esc(net.band)}, hello ${net.helloIntervalS}s / dead ${net.deadIntervalS}s)<br>` +
          `${esc(pa.name)} ${esc(pa.state)} · ${esc(pb.name)} ${esc(pb.state)}`,
        );
      }
    }
  }

  renderHud(data);
  window.__viz.ready = true;
}

function renderHud(data) {
  const summary = data.summary;
  const states = Object.entries(summary.byState || {});
  const nets = data.nets
    .map((net) => {
      const rows = net.adjacencies
        .map((peer) => `<tr><td>${esc(peer.name)}</td><td>${esc(peer.role || '-')}</td><td class="${peer.state === 'FULL' ? '' : 'bad'}">${esc(peer.state)}</td><td class="n">${fmt(peer.holdTimeS)}</td></tr>`)
        .join('');
      return `<h2>${esc(net.name)} · ${esc(net.band)}</h2>
        <p>DS ${esc(net.ds?.name || 'none')} · BDS ${esc(net.bds?.name || 'none')} · hello ${net.helloIntervalS}s / dead ${net.deadIntervalS}s</p>
        <table><tr><th>peer</th><th>role</th><th>adj</th><th class="n">hold s</th></tr>${rows}</table>`;
    })
    .join('');
  const legend = [
    ...states.map(([state, count]) => [`<span class="k" style="background:${ROBOT_COLOR[state] || '#888'}"></span>${esc(state)} ${count}`]),
    [`<span class="k" style="background:${LINK_COLOR.ESTABLISHED}"></span>uplink established`,
     `<span class="k" style="background:${LINK_COLOR.DEGRADED}"></span>degraded`,
     `<span class="k" style="background:${ADJ_COLOR.FULL}"></span>FULL adjacency`,
     `<span class="k" style="background:${ADJ_COLOR.DOWN}"></span>adjacency DOWN`],
  ].flat().join('<br>');
  const expiresIn = token.expiresAt ? Math.max(0, (new Date(token.expiresAt) - Date.now()) / 1000) : 0;
  $('hud').innerHTML = `
    <h2>fleet</h2>
    <table>
      <tr><td>relays</td><td class="n">${summary.satellites}</td><td>links up</td><td class="n">${summary.establishedLinks}</td></tr>
      <tr><td>sites</td><td class="n">${data.sites.length}</td><td>robots</td><td class="n">${summary.totalRobots}</td></tr>
      <tr><td>anomalies</td><td class="n ${summary.openAnomalies ? 'bad' : 'good'}">${summary.openAnomalies}</td><td>avg health</td><td class="n">${fmt(summary.averageHealthPct, 0)}%</td></tr>
    </table>
    ${nets}
    <h2>legend</h2><p>${legend}</p>`;
  $('who').innerHTML = `signed in as <b>${esc(token.user)}</b> (${esc(token.role)})<br>` +
    `server clock ${esc(data.clock.now)} · up ${fmt(data.clock.uptimeS, 0)}s · token ${fmt(expiresIn / 60, 0)} min left<br>` +
    `polled ${new Date().toLocaleTimeString()}`;
}

// ---------- motion ----------
// Position is a pure function of elapsed time, not of accumulated frames: that way a rebuild on poll
// puts every body exactly where it would have been anyway, and nothing snaps back to its start angle.
const EPOCH = performance.now();
function frame(now) {
  const t = (now - EPOCH) / 1000;
  for (const site of sites) {
    const angle = site.base + site.speed * t;
    site.node.position.set(Math.cos(angle) * SITE_RING, site.y, Math.sin(angle) * SITE_RING);
    site.node.rotation.y = t * 0.05;
  }
  for (const relay of relays) {
    const angle = relay.base + relay.speed * t;
    relay.node.position.set(Math.cos(angle) * RELAY_RING, Math.sin(angle * 2) * 2.5, Math.sin(angle) * RELAY_RING);
    relay.node.rotation.y = -t * 0.25;
  }
  for (const robot of robots) {
    const angle = robot.base + robot.speed * t;
    const centre = robot.parent.node.position;
    robot.node.position.set(
      centre.x + Math.cos(angle) * robot.radius,
      centre.y + Math.sin(angle * 1.7) * 1.2,
      centre.z + Math.sin(angle) * robot.radius,
    );
  }
  for (const edge of edges) {
    const [a, b] = [edge.a, edge.b];
    edge.line.geometry.attributes.position.setXYZ(0, a.x, a.y, a.z).setXYZ(1, b.x, b.y, b.z);
    edge.line.geometry.attributes.position.needsUpdate = true;
  }
  controls?.update();
  renderer?.render(scene, camera);
  requestAnimationFrame(frame);
}

function resize() {
  if (!renderer) { return; }
  const w = window.innerWidth;
  const h = window.innerHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();
requestAnimationFrame(frame);

// ---------- hover readout ----------
const pointer = new THREE.Vector2(-10, -10);
const raycaster = new THREE.Raycaster();
raycaster.params.Line.threshold = 1.2;  // so uplinks and adjacencies are hoverable too
window.addEventListener('pointermove', (event) => {
  pointer.set((event.clientX / window.innerWidth) * 2 - 1, -(event.clientY / window.innerHeight) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(pickable, false)[0];
  const tip = $('tip');
  if (!hit) { tip.style.display = 'none'; return; }
  tip.innerHTML = hit.object.userData.info;
  tip.style.display = hit.object.userData.info ? 'block' : 'none';
  tip.style.left = `${event.clientX + 14}px`;
  tip.style.top = `${event.clientY + 14}px`;
});

// ---------- sign in, then poll ----------
let timer = null;
async function poll() {
  try {
    build(await snapshot());
  } catch (error) {
    if (error.status === 401) { signOut('token expired or rejected: ' + error.message); return; }
    $('err').textContent = 'poll failed: ' + error.message;
  }
}

function signOut(message) {
  token.value = null;
  clearInterval(timer);
  timer = null;
  disposeFleet();
  $('hud').innerHTML = '';
  $('who').textContent = '';
  $('login').style.display = '';
  $('err').textContent = message || '';
}

async function signIn() {
  $('err').textContent = '';
  try {
    const session = await api('/api/v1/auth/login', {
      method: 'POST',
      body: { username: $('user').value, password: $('pass').value },
    });
    token.value = session.token;
    token.user = session.username;
    token.role = session.role;
    token.expiresAt = session.expiresAt;
    $('login').style.display = 'none';
    await poll();
    timer = setInterval(poll, REFRESH_MS);
  } catch (error) {
    $('err').textContent = error.message;
  }
}

$('go').addEventListener('click', signIn);
$('pass').addEventListener('keydown', (event) => { if (event.key === 'Enter') { signIn(); } });
window.__viz = {
  ready: false,
  counts: () => ({ sites: sites.length, relays: relays.length, robots: robots.length, edges: edges.length }),
  pose: () => sites.map((s) => [s.node.position.x, s.node.position.z]),  // for checking the motion is continuous
};
