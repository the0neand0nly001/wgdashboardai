<script setup async>
import {RouterView, useRoute} from 'vue-router'
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {computed, watch} from "vue";
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

</script>

<template>
	<div class="h-100 bg-body" :data-bs-theme="store.Configuration?.Server.dashboard_theme">
		<div style="z-index: 9999; height: 5px" class="position-absolute loadingBar top-0 start-0"></div>
		<nav class="navbar bg-dark sticky-top" :class="{'eh-topbar': store.EHGateway}" data-bs-theme="dark" v-if="!route.meta.hideTopNav">
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
