<script setup async>
import {RouterView, useRoute} from 'vue-router'
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {computed, watch, onMounted, onUnmounted, nextTick} from "vue";
import endlessIcon from '@/assets/eh/endless-icon.png';
const store = DashboardConfigurationStore();
import "@/utilities/wireguard.js"
import {fetchGet} from "@/utilities/fetch.js";
store.initCrossServerConfiguration();
if (window.IS_WGDASHBOARD_DESKTOP){
	store.IsElectronApp = true;
	store.CrossServerConfiguration.Enable = true;
	if (store.ActiveServerConfiguration){
		fetchGet("/api/locale", {}, (res) => {
			store.Locale = res.data
		})
	}
}else{
	fetchGet("/api/locale", {}, (res) => {
		store.Locale = res.data
	})
}
watch(store.CrossServerConfiguration, () => {
	store.syncCrossServerConfiguration()
}, {
	deep: true
});
const route = useRoute()
watch(() => route.path, () => { if (store.EHGateway) store.ShowNavBar = false; });
async function toggleTools(){
  store.ShowNavBar = !store.ShowNavBar;
  if (store.ShowNavBar) { await nextTick(); document.querySelector('.eh-nav a')?.focus(); }
}
function closeTools(event){
  if (!store.EHGateway) return;
  if (event.key === 'Escape' && store.ShowNavBar) {
    store.ShowNavBar = false;
    document.querySelector('.eh-tools-toggle')?.focus();
  }
  if (event.key === 'Tab' && store.ShowNavBar) {
    const controls = [document.querySelector('.eh-tools-toggle'), ...document.querySelectorAll('.eh-nav a[href], .eh-nav button')].filter(e => e && !e.disabled && e.getClientRects().length);
    const index = controls.indexOf(document.activeElement);
    if (event.shiftKey && index <= 0) { event.preventDefault(); controls.at(-1)?.focus(); }
    else if (!event.shiftKey && (index < 0 || index === controls.length - 1)) { event.preventDefault(); controls[0]?.focus(); }
  }
}
onMounted(() => window.addEventListener('keydown', closeTools));
onUnmounted(() => window.removeEventListener('keydown', closeTools));

</script>

<template>
	<div class="h-100 bg-body" :class="{'eh-app':store.EHGateway}" :data-bs-theme="store.EHGateway ? 'dark' : store.Configuration?.Server.dashboard_theme">
		<a v-if="store.EHGateway" href="#eh-content" class="eh-skip">Skip to content</a>
		<header v-if="store.EHGateway && !route.meta.hideTopNav" class="eh-header">
			<div class="eh-header-inner">
				<RouterLink to="/overview" class="eh-brand" aria-label="Endless VPN home"><img :src="endlessIcon" alt="" width="52" height="52"><span>ENDLESS<span class="eh-brand-sub">VPN CONTROL</span></span></RouterLink>
				<nav class="eh-primary-nav" aria-label="Main navigation"><RouterLink to="/overview">Overview</RouterLink><RouterLink to="/configurations" :class="{'router-link-active':route.path.startsWith('/configuration/')}">Devices</RouterLink><RouterLink to="/forwarding">Public ports</RouterLink></nav>
				<label class="eh-server-picker"><span>Managing</span><select aria-label="Choose VPN server" :value="store.EHNode" @change="store.selectEHNode($event.target.value)"><option value="vpn1">Oracle VPN1</option><option value="vpn2">Oracle VPN2</option></select></label>
				<button class="eh-tools-toggle" aria-label="Advanced tools" aria-controls="sidebarMenu" :aria-expanded="store.ShowNavBar" @click="toggleTools"><span aria-hidden="true">{{ store.ShowNavBar ? '×' : '☰' }}</span><span>Tools</span></button>
			</div>
		</header>
		<div v-if="store.EHGateway && store.ShowNavBar" class="eh-menu-dismiss" @click="store.ShowNavBar=false" aria-hidden="true"></div>
		<div style="z-index: 9999; height: 5px" class="position-absolute loadingBar top-0 start-0"></div>
		<nav class="navbar bg-dark sticky-top" data-bs-theme="dark" v-if="!store.EHGateway && !route.meta.hideTopNav">
			<div class="container-fluid d-flex text-body align-items-center">
				<RouterLink to="/" class="navbar-brand mb-0 h1">
					<span v-if="store.EHGateway">Endless Horizons <small class="text-secondary">VPN</small></span>
					<img v-else src="/img/Logo-2-Rounded-512x512.png" alt="WGDashboard Logo" style="width: 32px">
				</RouterLink>
				<select v-if="store.EHGateway" class="form-select w-auto ms-auto me-3" aria-label="Choose VPN server"
				        :value="store.EHNode" @change="store.selectEHNode($event.target.value)">
					<option value="vpn1">Oracle VPN1</option><option value="vpn2">Oracle VPN2</option>
				</select>
				<a role="button" class="navbarBtn text-body"
				   tabindex="0" aria-label="Open navigation" :aria-expanded="store.ShowNavBar" @keydown.enter="store.ShowNavBar = !store.ShowNavBar"
				   @click="store.ShowNavBar = !store.ShowNavBar"
				   style="line-height: 0; font-size: 2rem">
					<Transition name="fade2" mode="out-in">
						<i class="bi bi-list" v-if="!store.ShowNavBar"></i>
						<i class="bi bi-x-lg" v-else></i>
					</Transition>
				</a>
			</div>
		</nav>
		<Suspense>
			<RouterView v-slot="{ Component }">
				<Transition name="app" mode="out-in" type="transition" appear>
					<Component :is="Component"></Component>
				</Transition>
			</RouterView>
		</Suspense>
	</div>
</template>

<style scoped>
.navbar.eh-topbar { display: flex !important; min-height: 64px; }
.eh-topbar .navbar-brand { font-size: 1rem; }
.app-enter-active,
.app-leave-active {
	transition: all 0.7s cubic-bezier(0.82, 0.58, 0.17, 1);
}
.app-enter-from,
.app-leave-to{
	opacity: 0;
	transform: scale(1.05);
	filter: blur(8px);
}
@media screen and (min-width: 768px) {
	.navbar{
		display: none;
	}
}
</style>
