import {defineStore} from "pinia";
import {fetchGet} from "@/utilities/fetch.js";
import {v4} from "uuid";
import {GetLocale} from "@/utilities/locale.js";

export const DashboardConfigurationStore = defineStore('DashboardConfigurationStore', {
	state: () => ({
		EHGateway: Boolean(window.EH_GATEWAY),
		EHNode: sessionStorage.getItem('EHSelectedNode') || 'vpn2',
		Redirect: undefined,
		Configuration: undefined,
		Messages: [],
		Peers: {
			Selecting: false,
			RefreshInterval: undefined
		},
		CrossServerConfiguration:{
			Enable: false,
			ServerList: {}
		},
		SystemStatus: undefined,
		ActiveServerConfiguration: undefined,
		IsElectronApp: false,
		ShowNavBar: false,
		Locale: null,
		HelpAgent: {
			Enable: false
		}
	}),
	actions: {
		selectEHNode(value){
			if (!['vpn1', 'vpn2'].includes(value)) return;
			sessionStorage.setItem('EHSelectedNode', value);
			window.location.hash = '#/overview';
			window.location.reload();
		},
		initCrossServerConfiguration(){
			if (window.EH_GATEWAY) return;
			const currentConfiguration = localStorage.getItem('CrossServerConfiguration');
			if (localStorage.getItem("ActiveCrossServerConfiguration") !== null){
				this.ActiveServerConfiguration = localStorage.getItem("ActiveCrossServerConfiguration");
			}
			if (currentConfiguration === null){
				window.localStorage.setItem('CrossServerConfiguration', JSON.stringify(this.CrossServerConfiguration))
			}else{
				this.CrossServerConfiguration = JSON.parse(currentConfiguration)
			}
		},
		syncCrossServerConfiguration(){
			window.localStorage.setItem('CrossServerConfiguration', JSON.stringify(this.CrossServerConfiguration))
		},
		addCrossServerConfiguration(){
			this.CrossServerConfiguration.ServerList[v4().toString()] = {
                host: "",
                apiKey: "",
                active: false
            }
		},
		deleteCrossServerConfiguration(key){
			delete this.CrossServerConfiguration.ServerList[key];
		},
		getActiveCrossServer(){
			const key = localStorage.getItem('ActiveCrossServerConfiguration');
			if (key !== null){
				return this.CrossServerConfiguration.ServerList[key]
			}
			return undefined
		},
		async setActiveCrossServer(key){
			this.ActiveServerConfiguration = key;
			localStorage.setItem('ActiveCrossServerConfiguration', key)
			await fetchGet("/api/locale", {}, (res) => {
				this.Locale = res.data
			})
		},
		removeActiveCrossServer(){
			this.ActiveServerConfiguration = undefined;
			localStorage.removeItem('ActiveCrossServerConfiguration')
		},
		async getConfiguration(){
			await fetchGet("/api/getDashboardConfiguration", {}, (res) => {
				if (res.status) this.Configuration = res.data
			});
		},
		async signOut(){
			await fetchGet("/api/signout", {}, () => {
				this.removeActiveCrossServer();
				document.cookie = '';
				this.$router.go('/signin')
			});
		},
		newMessage(from, content, type){
			this.Messages.push({
				id: v4(),
				from: GetLocale(from),
				content: GetLocale(content),
				type: type,
				show: true
			})
		},
		applyLocale(key){
			if (this.Locale === null) 
				return key
			const reg = Object.keys(this.Locale)
			const match = reg.filter(x => {
				return key.match(new RegExp('^' + x + '$', 'g')) !== null
			})
			console.log(match)
			if (match.length === 0 || match.length > 1){
				return key
			}
			return this.Locale[match[0]]
		}
	},
	persist: {
		pick: [
			'HelpAgent.Enable'
		]
	}
});
