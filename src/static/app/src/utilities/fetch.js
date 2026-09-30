import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import router from "@/router/router.js";
const getHeaders = () => {
	if (window.EH_GATEWAY) return {
		'Content-Type': 'application/json', 'X-EH-Request': '1',
		'X-EH-Node': sessionStorage.getItem('EHSelectedNode') || 'vpn2'
	};
	let headers = {
		"Content-Type": "application/json"
	}
	const store = DashboardConfigurationStore();
	const crossServer = store.getActiveCrossServer();
	if (crossServer){
		headers['wg-dashboard-apikey'] = crossServer.apiKey
        if (crossServer.headers){
            for (let header of Object.values(crossServer.headers)){
                if (header.key && header.value && !Object.keys(headers).includes(header.key)){
                    headers[header.key] = header.value
                }
            }
        }
	}


	return headers
}

export const getUrl = (url) => {
	if (window.EH_GATEWAY) return url;
	const store = DashboardConfigurationStore();
	const apiKey = store.getActiveCrossServer();
	if (apiKey){
		return `${apiKey.host}${url}`
	}
	if (import.meta.env.MODE === 'development') {
		return url;
	}
	// const appPrefix = window.APP_PREFIX || '';
	return `./.${url}`;
}

export const fetchGet = async (url, params=undefined, callback=undefined) => {
	if (window.EH_GATEWAY) {
		try {
			const response = await fetch(`${getUrl(url)}?${new URLSearchParams(params).toString()}`, {headers: getHeaders()});
			const value = await response.json();
			if (response.status === 401) router.push('/signin');
			return callback ? callback(value) : value;
		} catch {
			const value = {status:false, message:'Dashboard request failed. Check the private connection.'};
			return callback ? callback(value) : value;
		}
	}
	const urlSearchParams = new URLSearchParams(params);
	await fetch(`${getUrl(url)}?${urlSearchParams.toString()}`, {
		headers: getHeaders()
	})
		.then((x) => {
			const store = DashboardConfigurationStore();
			if (!x.ok){
				if (x.status !== 200){
					if (x.status === 401){
						store.newMessage("WGDashboard", "Sign in session ended, please sign in again", "warning")
					}
					throw new Error(x.statusText)
				}
			}else{
				return x.json()
			}
		})
		.then(x => callback ? callback(x) : undefined).catch(x => {
			console.log("Error:", x)
			router.push({path: '/signin'})
	})
}

export const fetchPost = async (url, body, callback) => {
	if (window.EH_GATEWAY) {
		try {
			const response = await fetch(getUrl(url), {headers:getHeaders(), method:'POST', body:JSON.stringify(body)});
			const value = await response.json();
			if (response.status === 401) router.push('/signin');
			return callback ? callback(value) : value;
		} catch {
			const value = {status:false, message:'Dashboard request failed. Check the private connection.'};
			return callback ? callback(value) : value;
		}
	}
	await fetch(`${getUrl(url)}`, {
		headers: getHeaders(),
		method: "POST",
		body: JSON.stringify(body)
	}).then((x) => {
		const store = DashboardConfigurationStore();
		if (!x.ok){
			if (x.status !== 200){
				if (x.status === 401){
					store.newMessage("WGDashboard", "Sign in session ended, please sign in again", "warning")
				}
				throw new Error(x.statusText)
			}
		}else{
			return x.json()
		}
	}).then(x => callback ? callback(x) : undefined).catch(x => {
		console.log("Error:", x)
		router.push({path: '/signin'})
	})
}
