<script setup>
import {ref, computed, onMounted, onUnmounted} from 'vue';
import {fetchGet} from '@/utilities/fetch.js';
import {DashboardConfigurationStore} from '@/stores/DashboardConfigurationStore.js';
const store = DashboardConfigurationStore();
const nodes = ref([]), error = ref(''), updated = ref(null);
const selected = computed(() => nodes.value.find(n => n.id === store.EHNode));
let timer, pending = false;
async function refresh() {
  if (pending || document.hidden) return;
  pending = true;
  try { await fetchGet('/api/eh/overview', {}, r => {
    if (r.status) { nodes.value = r.data; updated.value = new Date(); error.value = ''; }
    else error.value = r.message;
  }); } finally { pending = false; }
}
function bytes(n) {
  if (!Number.isFinite(n)) return '—';
  const units = ['B','KB','MB','GB','TB']; let i=0;
  while (n >= 1024 && i < 4) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
function curve(history, field) {
  if (!history?.length) return '';
  const top = Math.max(1, ...history.flatMap(s => [s.upload, s.download]));
  const first = history[0].time, span = Math.max(1, history.at(-1).time - first);
  return history.map(s => `${((s.time-first)/span*600).toFixed(1)},${(130-s[field]/top*120).toFixed(1)}`).join(' ');
}
function label(peer) {
  return localStorage.getItem(`EHLabel:${store.EHNode}:${peer.key}`) || peer.key.slice(0, 10);
}
function rename(peer) {
  const name = window.prompt('Device name (saved in this browser)', label(peer));
  if (name !== null) { localStorage.setItem(`EHLabel:${store.EHNode}:${peer.key}`, name.trim().slice(0, 80)); refresh(); }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 5000); });
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <section class="eh-overview mx-auto p-3 p-lg-4 text-body">
    <div class="d-flex align-items-center justify-content-between mb-4"><div><p class="text-info mb-1">PRIVATE NETWORK</p><h2 class="mb-1">Your VPN overview</h2><p class="text-secondary mb-0">Both servers at a glance. Controls follow the server selected above.</p></div><button class="btn btn-outline-secondary" @click="refresh">Refresh</button></div>
    <p v-if="error" class="alert alert-danger">{{ error }}</p>
    <div class="row g-3 mb-4">
      <div v-for="node in nodes" :key="node.id" class="col-md-6"><article class="node-card p-4 rounded-4 border" :class="{'border-info':node.id===store.EHNode}">
        <div class="d-flex justify-content-between"><h4>{{ node.name }}</h4><span :class="node.ok ? 'text-success':'text-warning'">{{ node.ok ? 'Online':'Unavailable' }}</span></div>
        <p class="text-secondary">{{ node.public_ip || 'Address unavailable' }} · {{ node.peers.filter(p=>p.active).length }} recently active / {{ node.peers.length }} devices</p>
        <div class="d-flex gap-4"><div><small class="text-secondary">UPLOAD</small><h5>{{ bytes(node.peers.reduce((n,p)=>n+p.upload_speed,0)) }}/s</h5></div><div><small class="text-secondary">DOWNLOAD</small><h5>{{ bytes(node.peers.reduce((n,p)=>n+p.download_speed,0)) }}/s</h5></div></div>
        <small v-if="node.load" class="text-secondary">Host load (1 / 5 / 15 min): {{ node.load.map(n=>n.toFixed(2)).join(' / ') }}</small>
        <p v-if="node.error" class="text-warning mt-2 mb-0">{{ node.error }}</p>
        <button v-if="node.id!==store.EHNode" class="btn btn-sm btn-outline-info mt-3" @click="store.selectEHNode(node.id)">Manage {{ node.name }}</button>
      </article></div>
    </div>
    <template v-if="selected">
      <div class="node-card border rounded-4 p-4 mb-4"><h5>{{ selected.name }} · traffic over the last 24 hours</h5><p class="text-secondary small">Upload <span class="text-info">●</span> · Download <span class="text-success">●</span> · Stored since this monitor starts</p>
        <svg v-if="selected.history?.length" viewBox="0 0 600 140" role="img" aria-label="Upload and download history" class="traffic-chart"><polyline :points="curve(selected.history,'upload')" fill="none" stroke="#38bdf8" stroke-width="2"/><polyline :points="curve(selected.history,'download')" fill="none" stroke="#34d399" stroke-width="2"/></svg>
        <div v-if="selected.history?.length" class="d-flex justify-content-between small text-secondary"><span>{{ new Date(selected.history[0].time*1000).toLocaleTimeString() }}</span><span>Scale: 0–{{ bytes(Math.max(...selected.history.flatMap(s=>[s.upload,s.download]))) }}/s</span><span>{{ new Date(selected.history.at(-1).time*1000).toLocaleTimeString() }}</span></div>
        <p v-else class="text-secondary">Traffic history will appear after the first samples.</p>
      </div>
      <div class="d-flex justify-content-between align-items-center mb-3"><h5>{{ selected.name }} · devices</h5><RouterLink to="/configurations" class="btn btn-sm btn-outline-info">Manage devices &amp; QR codes</RouterLink></div>
      <div class="table-responsive border rounded-4"><table class="table align-middle mb-0"><thead><tr><th>Device</th><th>Tunnel IP</th><th>Activity</th><th>Upload</th><th>Download</th><th>Tracked totals ↑ / ↓</th></tr></thead><tbody><tr v-for="peer in selected.peers" :key="peer.key"><td><button class="btn btn-link p-0 text-info" @click="rename(peer)">{{ label(peer) }}</button><div class="small text-secondary">{{ peer.endpoint }}</div></td><td>{{ peer.tunnel_ip }}</td><td><span :class="peer.active?'text-success':'text-secondary'">{{ peer.active?'Recent':'Inactive' }}</span><div class="small text-secondary">{{ peer.handshake ? new Date(peer.handshake*1000).toLocaleString() : 'No handshake' }}</div></td><td>{{ bytes(peer.upload_speed) }}/s</td><td>{{ bytes(peer.download_speed) }}/s</td><td>{{ bytes(peer.total_upload) }} / {{ bytes(peer.total_download) }}</td></tr><tr v-if="!selected.peers.length"><td colspan="6" class="text-secondary p-4">No devices available from this server.</td></tr></tbody></table></div>
    </template>
    <p class="small text-secondary mt-3">{{ updated ? `Updated ${updated.toLocaleTimeString()}` : 'Loading servers…' }} · Recent activity means a handshake within 3 minutes; it is not a guaranteed connection status.</p>
  </section>
</template>
<style scoped>
.eh-overview{max-width:1400px}.node-card{background:rgba(25,38,45,.75)}.traffic-chart{width:100%;height:180px}.table{--bs-table-bg:transparent}th{font-size:.8rem;color:#9ca3af}td{font-size:.9rem}
</style>
