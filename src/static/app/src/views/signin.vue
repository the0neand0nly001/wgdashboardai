<script>
import {fetchGet, fetchPost} from "../utilities/fetch.js";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import Message from "@/components/messageCentreComponent/message.vue";
import RemoteServerList from "@/components/signInComponents/RemoteServerList.vue";
import {GetLocale} from "@/utilities/locale.js";
import LocaleText from "@/components/text/localeText.vue";
import SignInInput from "@/components/signIn/signInInput.vue";
import SignInTOTP from "@/components/signIn/signInTOTP.vue";
import endlessIcon from '@/assets/eh/endless-icon.png';

export default {
	name: "signin",
	components: {SignInTOTP, SignInInput, LocaleText, RemoteServerList, Message},
	async setup(){
		const store = DashboardConfigurationStore()
		let theme = "dark"
		let totpEnabled = false;
		let version = undefined;
		if (!store.IsElectronApp){
			await Promise.all([
				fetchGet("/api/getDashboardTheme", {}, (res) => {
					theme = res.data
				}),
				fetchGet("/api/isTotpEnabled", {}, (res) => {
					totpEnabled = res.data
				}),
				fetchGet("/api/getDashboardVersion", {}, (res) => {
					version = res.data
				})
			]);
		}
		store.removeActiveCrossServer();
		return {store, theme, totpEnabled, version, endlessIcon}
	},
	data(){
		return {
			data: {
				username: "",
				password: "",
				totp: "",
			},
			loginError: false,
			loginErrorMessage: "",
			loading: false
		}
	},
	computed: {
		getMessages(){
			return this.store.Messages.filter(x => x.show)
		},
		applyLocale(key){
			return GetLocale(key)
		},
		formValid(){
			return this.data.username && this.data.password && ((this.totpEnabled && this.data.totp) || !this.totpEnabled)
		}
	},
	methods: {
		GetLocale,
		async auth(){
			if (this.formValid){
				this.loading = true
				await fetchPost("/api/authenticate", this.data, (response) => {
					if (response.status){
						this.loginError = false;
						this.$refs["signInBtn"].classList.add("signedIn")
						if (response.message){
							this.$router.push('/welcome')
						}else{
							if (this.store.Redirect !== undefined){
								this.$router.push(this.store.Redirect)
							}else{
								this.$router.push('/')
							}
						}
					}else{
						this.loginError = true;
						this.loginErrorMessage = response.message || 'Sign in failed';
						this.store.newMessage("Server", response.message, "danger")
						document.querySelectorAll("input[required]").forEach(x => {
							x.classList.remove("is-valid")
							x.classList.add("is-invalid")
						});
						this.loading = false
					}

				})
			}else{
				document.querySelectorAll("input[required]").forEach(x => {
					if (x.value.length === 0){
						x.classList.remove("is-valid")
						x.classList.add("is-invalid")
					}else{
						x.classList.remove("is-invalid")
						x.classList.add("is-valid")
					}
				});
			}
		}
	}
}
</script>

<template>
	<div v-if="store.EHGateway" class="eh-signin">
		<section class="eh-signin-identity"><img :src="endlessIcon" alt="Endless VPN icon" width="95" height="95"><p class="eh-kicker">ENDLESS HORIZONS / NETWORK</p><h1>Endless VPN</h1><p>Manage your devices, monitor traffic and share services across your two VPN servers.</p><div class="eh-signin-servers"><div>Oracle VPN1<span>WireGuard</span></div><div>Oracle VPN2<span>WireGuard · dashboard host</span></div></div></section>
		<section class="eh-signin-form" aria-labelledby="sign-in-title"><h2 id="sign-in-title">Admin sign in</h2><p class="eh-intro">One account for both servers.</p><form @submit.prevent="auth"><label class="eh-form-label" for="eh-username">Username<input id="eh-username" v-model="data.username" class="eh-input" name="username" autocomplete="username" required :disabled="loading"></label><label class="eh-form-label" for="eh-password">Password<input id="eh-password" v-model="data.password" class="eh-input" name="password" type="password" autocomplete="current-password" required :disabled="loading"></label><p v-if="loginError" class="eh-alert" role="alert">{{ loginErrorMessage }}</p><button class="eh-action" ref="signInBtn" :disabled="loading || !formValid">{{ loading?'Signing in…':'Sign in →' }}</button><p class="eh-footnote">Dashboard access requires a connection to either VPN.</p></form></section>
		<footer class="eh-signin-footer"><span>Endless Horizons · private network</span><span>Powered by <a href="https://github.com/WGDashboard/WGDashboard" target="_blank" rel="noopener">WGDashboard</a> {{ version }}</span></footer>
	</div>
	<div v-else class="container-fluid login-container-fluid d-flex main flex-column py-4 text-body h-100"
	     style="overflow-y: scroll"
	     :data-bs-theme="this.theme">
		<div class="login-box m-auto" >
			<div class="m-auto signInContainer" style="width: 700px;">
				<h4 class="mb-0 text-body">
					<LocaleText t="Welcome to"></LocaleText>
				</h4>
				<span class="dashboardLogo display-3">
					<strong>{{ store.EHGateway ? 'Endless Horizons VPN' : 'WGDashboard' }}</strong>
				</span>
				<form @submit="(e) => {e.preventDefault(); this.auth();}"
				      class="mt-3"
				      v-if="!this.store.CrossServerConfiguration.Enable">
					<div class="form-floating mb-2">
						<input type="text"
						       required
						       :disabled="loading"
						       v-model="this.data.username"
						       name="username"
						       autocomplete="username"
						       autofocus
						       class="form-control rounded-3" id="username" placeholder="Username">
						<label for="floatingInput" class="d-flex">
							<i class="bi bi-person-circle me-2"></i>
							<LocaleText t="Username"></LocaleText>
						</label>
					</div>
					<div class="form-floating mb-2">
						<input type="password"
						       required
						       :disabled="loading"
						       autocomplete="current-password"
						       v-model="this.data.password"
						       class="form-control rounded-3" id="password" placeholder="Password">
						<label for="floatingInput" class="d-flex">
							<i class="bi bi-key-fill me-2"></i>
							<LocaleText t="Password"></LocaleText>
						</label>
					</div>
					<div class="form-floating mb-2" v-if="this.totpEnabled">
						<input type="text"
						       id="totp"
						       required
						       :disabled="loading"
						       placeholder="totp"
						       v-model="this.data.totp"
						       class="form-control rounded-3"
						       maxlength="6"
						       inputmode="numeric"
						       autocomplete="one-time-code">
						<label for="floatingInput" class="d-flex">
							<i class="bi bi-lock-fill me-2"></i>
							<LocaleText t="OTP from your authenticator"></LocaleText>
						</label>
					</div>
					<button class="btn btn-lg btn-dark ms-auto mt-5 w-100 d-flex btn-brand signInBtn rounded-3"
					        :disabled="this.loading || !this.formValid"
					        ref="signInBtn">
							<span v-if="!this.loading" class="d-flex w-100">
								<LocaleText t="Sign In"></LocaleText>
								<i class="ms-auto bi bi-chevron-right"></i>
							</span>
							<span v-else class="d-flex w-100 align-items-center">
								<LocaleText t="Signing In..."></LocaleText>
								<span class="spinner-border ms-auto spinner-border-sm" role="status"></span>
							</span>
					</button>
				</form>
				<RemoteServerList v-else></RemoteServerList>

				<div class="d-flex mt-3" v-if="!this.store.IsElectronApp && !store.EHGateway">
					<div class="form-check form-switch ms-auto">
						<input
							v-model="this.store.CrossServerConfiguration.Enable"
							:disabled="loading"
							class="form-check-input"
							type="checkbox"
							role="switch"
							id="flexSwitchCheckChecked">
						<label class="form-check-label" for="flexSwitchCheckChecked">
							<LocaleText t="Access Remote Server"></LocaleText>
						</label>
					</div>
				</div>
			</div>
		</div>
		<div class="d-flex container-fluid align-items-center my-1 w-100">
			<small class="text-muted">
				WGDashboard <strong>{{ this.version }}</strong> | Made with ❤️ by
				<a href="https://github.com/WGDashboard"
				   class="text-decoration-none text-body"
				   target="_blank"><strong>WGDashboard</strong></a>
			</small>
			<a v-if="!store.EHGateway" href="./client" target="_blank"
			   class="text-decoration-none ms-auto text-body"
			   style="white-space: nowrap">
				<small><i class="bi bi-box-arrow-up-right me-1"></i>
					<LocaleText t="Client App" /></small>
			</a>
		</div>
		<div class="messageCentre text-body position-absolute d-flex">
			<TransitionGroup name="message" tag="div"
			                 class="position-relative flex-sm-grow-0 flex-grow-1 d-flex align-items-end ms-sm-auto flex-column gap-2">
				<Message v-for="m in getMessages.slice().reverse()"
				         :message="m" :key="m.id"></Message>
			</TransitionGroup>
		</div>
	</div>
</template>

<style scoped>
@media screen and (max-width: 768px) {
	.login-box{
		width: 100% !important;
	}

	.login-box div{
		width: auto !important;
	}
}


</style>
