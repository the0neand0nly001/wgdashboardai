import './css/dashboard.css'
import 'bootstrap/dist/css/bootstrap.css'
import 'bootstrap/dist/js/bootstrap.js'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'animate.css/animate.css'
import '@vuepic/vue-datepicker/dist/main.css'
import './css/eh.css'
import endlessIcon from './assets/eh/endless-icon.png'
import {createApp, markRaw} from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/router.js'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

const app = createApp(App)
if (window.EH_GATEWAY) {
  document.body.classList.add('eh-mode');
  document.title = 'Endless VPN';
  document.querySelector('link[rel="icon"]')?.setAttribute('href', endlessIcon);
}

app.use(router)
const pinia = createPinia();
pinia.use(piniaPluginPersistedstate)
pinia.use(({ store }) => {
	store.$router = markRaw(router)
})


app.use(pinia)
app.mount('#app')
