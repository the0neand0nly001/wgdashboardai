<script setup>
import {ref, onMounted, onUnmounted} from 'vue';
import {fetchGet, fetchPost} from '@/utilities/fetch.js';
import {DashboardConfigurationStore} from '@/stores/DashboardConfigurationStore.js';
const store = DashboardConfigurationStore();
const peers = ref([]), leases = ref([]), address = ref(''), error = ref(''), busy = ref(false);
const form = ref({peer:'', local_port:25565, protocol:'tcp', minutes:60, label:''});
let timer;
async function refresh(){
  await fetchGet('/api/eh/overview', {}, r => {
    const node=r.data?.find(n=>n.id===store.EHNode);
    peers.value=node?.peers || []; address.value=node?.public_ip || '';
  });
  await fetchGet('/api/eh/leases', {}, r=>{if(r.status) leases.value=r.data; else error.value=r.message});
}
async function submit(path, body){
  if(busy.value) return;
  busy.value=true; error.value='';
  try{await fetchPost(path,body,r=>{if(!r.status) error.value=r.message}); await refresh();}
  finally{busy.value=false;}
}
async function copy(lease){
  const value=`${address.value}:${lease.public_port}`;
  try { await navigator.clipboard.writeText(value); }
  catch { window.prompt('Copy this address',value); }
}
onMounted(()=>{refresh();timer=setInterval(()=>{if(!document.hidden&&!busy.value)refresh()},10000)});
onUnmounted(()=>clearInterval(timer));
</script>
<template>
<section class="mx-auto p-3 p-lg-4 text-body" style="max-width:1100px">
  <p class="text-info mb-1">{{ store.EHNode==='vpn1'?'ORACLE VPN1':'ORACLE VPN2' }}</p><h2>Temporary port forwarding</h2>
  <p class="text-secondary">Share a service on a VPN device through this server’s public address. An available port from 45100–45120 is allocated for each lease.</p>
  <div v-if="error" class="alert alert-danger">{{ error }}</div>
  <form class="border rounded-4 p-4 mb-4" @submit.prevent="submit('/api/eh/leases',form)">
    <div class="row g-3"><label class="col-md-6">VPN device<select v-model="form.peer" class="form-select mt-1" required><option disabled value="">Choose a device</option><option v-for="p in peers" :key="p.key" :value="p.key">{{ p.tunnel_ip }} · {{ p.key.slice(0,10) }}</option></select></label>
    <label class="col-md-3">Local port<input v-model.number="form.local_port" class="form-control mt-1" type="number" min="1" max="65535" required></label>
    <label class="col-md-3">Protocol<select v-model="form.protocol" class="form-select mt-1"><option value="tcp">TCP</option><option value="udp">UDP</option><option value="both">TCP + UDP</option></select></label>
    <label class="col-md-6">Label<input v-model="form.label" class="form-control mt-1" maxlength="100" placeholder="Minecraft, game server…"></label>
    <label class="col-md-6">Duration in minutes<input v-model.number="form.minutes" class="form-control mt-1" type="number" min="1" max="10080" required><div class="d-flex gap-2 mt-2"><button v-for="m in [15,60,240,1440]" :key="m" type="button" class="btn btn-sm btn-outline-secondary" @click="form.minutes=m">{{ m<60?`${m} min`:`${m/60} hr` }}</button></div></label></div>
    <p class="small text-secondary mt-3">The device must be connected to this VPN and its service/firewall must accept the local port. The forwarded service is reachable from the public internet.</p>
    <button class="btn btn-info" :disabled="busy">{{ busy?'Working…':'Allocate public port' }}</button>
  </form>
  <h5>Active leases</h5><p class="text-secondary small">Renew uses the duration selected above. Close removes the forwarding rules and existing tracked connections.</p>
  <article v-for="lease in leases" :key="lease.id" class="border rounded-4 p-3 mb-3">
    <div class="d-flex flex-wrap gap-3 align-items-center"><div class="flex-grow-1"><h5 class="text-info mb-1">{{ address }}:{{ lease.public_port }}</h5><div>{{ lease.label || 'Forwarded service' }} · {{ lease.protocol.toUpperCase() }} → {{ lease.ip }}:{{ lease.local_port }}</div><small class="text-secondary">Expires {{ new Date(lease.expires*1000).toLocaleString() }}</small></div>
    <button class="btn btn-outline-secondary" @click="copy(lease)">Copy address</button><button class="btn btn-outline-info" :disabled="busy" @click="submit(`/api/eh/leases/${lease.id}/renew`,{minutes:form.minutes})">Renew</button><button class="btn btn-outline-danger" :disabled="busy" @click="submit(`/api/eh/leases/${lease.id}/close`,{})">Close</button></div>
  </article><p v-if="!leases.length" class="text-secondary">No active forwarded ports on this server.</p>
</section>
</template>
