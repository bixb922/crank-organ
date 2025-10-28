// Copyright (c) 2023-2025 Hermann von Borries
// MIT License
let clt0 = Date.now();
let clt00 = clt0;
function consoledebug( ...args  ){
	let clt1 = Date.now();
	args.unshift( clt1-clt0 );
	args.unshift((clt1-clt00)/1000);
	console.debug(args.join(" "));
	clt0 = clt1;
}
consoledebug("common.js start");
// also using console.error(), console.warn() and console.assert()

let MAX_DB = 0 ;
let MIN_DB = -20 ;

let MAX_CENTS = 50 ;

// >>>define colors in root class of css instead of here
// :root {
//   --primary-color: #007bff;
//   --font-size-base: 16px;
// }
light_gold = "#B29700";
american_gold = "#D4AF37";
sunray = "#E1C158";
asparagus = "#7DAA6A";
palm_leaf = "#619A46";
sap_green = "#438029";
gold = "#FAD723";
sandy = "#F4cF77";
oxford_blue = "#062646";
midnight_green = "#0C435E";
cream = "#FDFDD3";
gargoyle_gas = "#F7E13E";
fire_brick = "#B22222" ;

meter_green_color = "#95bb00" ; 
meter_red_color = "#C36922";
meter_gray = "#e8e8e8" ;
progress_color = "#3EA8A3" ; 



function is_no_number( n ){
	return n == null || typeof n === "undefined" || isNaN(n) ;
}

function format02i(n) {
	if (is_no_number(n) || n < 0 ) return "-";
	const num = Math.round(n);
	return (num < 10 ? "0" : "") + num;
}


function formatMilliMMSS(msec) {
	if(is_no_number(msec) || msec < 0) return "-";
	const totalSeconds = Math.round(msec / 1000);
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = format02i(totalSeconds % 60);
	return `${minutes}:${seconds}`;
}

function format_secHHMM( seconds ) {
	if(is_no_number(seconds) || seconds < 0){ return "-" };
	const totalMinutes = Math.round(seconds / 60) ;
	const hours = Math.floor(totalMinutes / 60);
	const minutes = format02i( totalMinutes % 60 ) ;
	return `${hours}:${minutes}`;
}


function getResourceFromURL(){
	let page_url = new URL(window.location.href) ;
	let path = page_url.pathname.split("/") ;
	if( path.length <= 2 ) {
		return "" ;
	}
	else {
		let r = path.slice(-1)[0]; // get last element as "resource"
        if( r.includes("html") + r.includes("json") != 0 ){
            r = "" ;   
        }
        return r;
	}
}
function getResourceNumberFromURL(){
    r = getResourceFromURL() ;
    if(r == ""){
        return "";
    }
    else {
        return parseInt(r) ;
    }
}

class BarGraph extends HTMLCanvasElement {
    constructor(){
        super();
        this.height = 16;
        this.backColor = meter_gray;
        this.barColor = progress_color ;
    }
    
    setParam( widthPercent=50, minvalue=0,  maxvalue=100 ){
        this.widthPercent = widthPercent;
        this.maxvalue = maxvalue;
        this.minvalue = minvalue;
        // Origin of BarGraph is always at left end of bar
    }
	draw(value) {
		const ctx = this.getContext("2d");
        this.width = Math.round(window.innerWidth*this.widthPercent/100);
		const cw = this.width;
		const ch = this.height;
		ctx.beginPath();
		ctx.clearRect(0, 0, cw, ch);

		// Erase rectangle (fill with gray)
		ctx.fillStyle = meter_gray;
		ctx.fillRect(0, 0, cw, ch);
		// Paint bar
		ctx.fillStyle = this.barColor;
		let c = Math.max(this.minvalue, Math.min(this.maxvalue, value));
        c = (c-this.minvalue)/(this.maxvalue-this.minvalue);
        ctx.fillRect(0, 0, c * cw, ch);
		ctx.stroke();
        
        //Draw border
		ctx.beginPath();
		ctx.strokeStyle = "black";
		ctx.lineWidth = 1;
		ctx.rect(0, 0, cw, ch);
		ctx.stroke();
	}
}
customElements.define("bar-graph", BarGraph, { extends: "canvas" });

class NeedleBar extends HTMLCanvasElement {
	constructor() {
		super();
        this.height = 18;
        this.barHeight = this.height - 3;
        
        this.barColor = meter_green_color;
        this.backColor = meter_gray;
        this.thresholdColor = meter_red_color ;
    }
    setParam(widthPercent=50, minvalue=0, maxvalue=100, threshold=0){
        this.widthPercent = widthPercent;
        this.threshold = threshold;
        this.minvalue = minvalue;
        this.maxvalue = maxvalue;
    }
    normalize( value ){
        // normalize to interval 0 to 1
        let v = Math.round((value-this.minvalue)/(this.maxvalue-this.minvalue)*this.width);
        return v;
    }
    draw( value ){
        const ctx = this.getContext("2d");
        this.width = Math.round(window.innerWidth*this.widthPercent/100);
        this.drawBackground( ctx );
        this.drawBar( ctx, value );
        this.drawThresholdInterval(ctx );
        this.drawBorder(ctx);
        this.drawNeedle(ctx, value  );
    }
    drawBackground(ctx){
		ctx.beginPath();
        ctx.fillStyle = this.backColor;
		ctx.lineWidth = 0;
		ctx.fillRect(0, 0, this.width, this.barHeight);
		ctx.stroke();
        
    }
    drawBar(ctx, value){
        const v = this.normalize( value );
        if( this.threshold && Math.abs(value) <= this.threshold ){
            return;
        }
        const center = this.normalize( 0 );
        ctx.beginPath();
        ctx.fillStyle = this.barColor;
        if( this.threshold ){
            ctx.fillStyle = this.thresholdColor;
        }
        ctx.lineWidth = 0;
        if( value >= 0){
            ctx.fillRect( center, 0,  v-center, this.barHeight);
        }
        else {
            ctx.fillRect( v, 0, center-v, this.barHeight);
        }
        ctx.stroke();
    }
    drawThresholdInterval(ctx){
        if( !this.threshold ){
            return;
        }
        const center = this.normalize( 0 );
        const t1 = this.normalize( this.threshold );
        const tw = (center-t1)*2;
        ctx.beginPath();
        ctx.fillStyle = this.barColor;
        ctx.lineWidth = 0;
        ctx.fillRect(t1, 0, tw  , this.barHeight);
        ctx.stroke();
    }
	drawNeedle(ctx,value) {
		if( value <= this.minvalue || value >= this.maxvalue ){
			return; // don't draw needle if out of range or at limit
		}
		const ch = this.height;
        let needlePos = this.normalize( value );
		// if value exceeds min/max, bar will cover canvas but
        // needle wil be in canvas, i.e. in the colored part.
		ctx.beginPath();
		ctx.lineWidth = 1;
		ctx.strokeStyle = "black";
		ctx.moveTo(needlePos - 2, ch - 5);
		ctx.lineTo(needlePos, ch * 0.15);
		ctx.lineTo(needlePos + 2, ch - 5);
		ctx.closePath();
		ctx.fillStyle = "black";
		ctx.fill();
		ctx.stroke();

		ctx.beginPath();
		ctx.lineWidth = 1;
		ctx.strokeStyle = "black";
		ctx.fillStyle = "white";
		ctx.arc(needlePos, ch - 4, 3, 0, 6.3);
		ctx.fill();
		ctx.stroke();
	}
    drawBorder(ctx){
		ctx.beginPath();
		ctx.strokeStyle = "black";
		ctx.lineWidth = 0.2;
		ctx.rect(0, 0, this.width, this.barHeight );
		ctx.stroke();
    }
}
customElements.define("needle-bar", NeedleBar, { extends: "canvas" });


// Function to fetch a json from server.
// Retries communication until successful.
// fetch_json.isConnected() shows if the connection is active
async function fetch_json( url, post_data ){
    let t0 ;
    let t ;
    let response ;
    let json_result ;
	let post_arg = make_fetch_args( post_data ) ;
	// One connect yields 0.75 but one failure still does not lower connects_ok so drastically
	fetch_json.isConnected = ()=>{ 
		// should be 2-3 times commonGetProgress.setSleep()
		if( (Date.now() - fetch_json.last_ok) > 15_000 ){
			return false; // should be some activity at least...
		}
		/// or if there are on average a fraction of good fetch_jsons.
		return fetch_json.connects_ok > 0.7; }
	while( true ) {
		try {
            t0 = Date.now() ;  // Reports response time
			fetch_json.last_ok = t0;
            response = {};
			response = await fetch( url, post_arg ) ;
			console.assert( response, "fetch() returned empty response");
			break ;
		}
		catch( err ) {
			console.error("fetch json failed", err, "url=", url ) ;
            // In the header battery time, replace battery
            // icon and time remaining with "network connection broken"
            // symbol.
			// keep running average of connects, goes faster up than down
		    fetch_json.connects_ok = (3*fetch_json.connects_ok + 0)/4; 
			msg = tlt("no conectado") ;
			popupmsg = (msg + " " + err).replace("TypeError", "Network error" ) ;
			showPopup( "", popupmsg );
			await sleep_ms( 5_000 ) ;
		}
		// retry fetch forever until getting through to server
	}
	// keep running average of connects, goes faster up than down
    fetch_json.connects_ok = (fetch_json.connects_ok + 3)/4; 
	if( !response.ok ){
		// Response not ok will notify error to user and abort throwing an error
        let rstatus = response.status ;
		if( rstatus == 401 ){
			if( await new PasswordDialog().askAndVerify() ){
				// askAndVerify() only returns true with a correct password
				// false means: dialog cancelled, no password entered.
				return await fetch_json( url, post_data );
			}
			// Fall through and generate 401 message if cancel was pressed.
		}
        response_html = await response.text() ; 
        response_text = response_html.replace(/<[^>]*>/g, ' ');
        console.error("Error response", rstatus, "url", url, "response", response, "text", response_text ) ;
        alert( `Server error ${rstatus} ${response_text}` ) ;
        throw new Error(`Server sent error status {response.status}`);
		// Fetch calls and call function will abort unless
		// there is a try/catch block.
	}
	json_result = await response.json() ; 
   
    t = Date.now() - t0;
	console.info("fetch_json ", url, "response time", t, "msec");
	// If there is an alert, show to user and reraise exception
	if( json_result["alert"]) {
		let alert_message = json_result["alert"];
		// Translate but only on pages where tlt is defined by translations.js
		if( typeof tlt === 'function' ) {
			alert_message = tlt ( alert_message ) ;
		}
		alert( alert_message ) ;
	}
	if(json_result["error"]){
			throw new Error("Error signalled by server: " + json_result.alert + " url " + url ) ;
		// respond_error_alert() prevents calling code to continue
		// (except when enclosing fetch_json in try/catch)
	}
	return json_result;
	
}
fetch_json.connects_ok = 0;
fetch_json.last_ok = Date.now();

function make_fetch_args( data ){
	if( data == undefined ){
		return undefined ;
	}
	// make a post argument for fetch
	return {
		method: "POST", // *GET, POST, PUT, DELETE, etc.
		mode: "same-origin", // no-cors, *cors, same-origin
		cache: "no-cache", // *default, no-cache, reload, force-cache, only-if-cached
		credentials: "same-origin", // include, *same-origin, omit
		headers: {
		  "Content-Type": "application/json",
		},
		redirect: "error", // manual, *follow, error
		referrerPolicy: "no-referrer", // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
		body: JSON.stringify(data), // body data type must match "Content-Type" header
  };
}

async function sleep_ms( t ){
	await new Promise(r => setTimeout(r, t));
}

class GetProgress{
	// Usage: instantiated in common.js only once (like a singleton)
	// commonGetProgress.registerCallback() to register callback when progress has been updated
	// commonGetProgress.setReloadIfTunelibChanged(v) true=reload this page if tunelib has changed, false=don't.
	// commonGetProgress.fetchJson( "/drop_setlist", post_data ) to
	// call some fetch_json that returns a progress and filter it, will also do callbacks.
	// commonGetProgress.registerCache( ) to register a JsonCache for fill/drop functions
	constructor(){
		this.callbackList = [];
		this.cacheList = [];
		this.sleep_ms = 10_000;
		this.reloadIfTunelibChanged = false;
	}
	registerCallback( callback ){
		this.callbackList.push( callback );
	}
	registerCache( cache ){
		this.cacheList.push( cache );
	}
	async fillCaches(){
		for( let cache of this.cacheList ){
			await cache.get();
		}
	}
	dropCaches(){
		for( let cache of this.cacheList ){
			cache.drop();
		}
	}
	setReloadIfTunelibChanged( v ){
		this.reloadIfTunelibChanged = v;
	}
	setSleep( v ){
		// in milliseconds
		this.sleep_ms = v ;
	}
	getSleep(){
		return this.sleep_ms;
	}
	startBackground(){
		this.#backgroundProcess();
	}
	async getProgress( ){
		let progress = await this.fetchJson( "/get_progress" );
		console.debug("progress=", progress);
		return progress;
	}

	async fetchJson( url, post ){
		// do a fetch_json that returns a progress, and filter it
		// before returning.
		let progress = await fetch_json( url, post );
		if( !progress ){
			throw new Error("fetch_json progress is empty, ignored");
		}

		await this.#filterProgress( progress );
		this.#checkCaches(progress);
		return progress;
	}

	async #filterProgress( progress ){
		let tunelib = await tunelibCache.get();
		// setlist could have tunes not in tunelib, filter out to make life easier.
		progress["setlist"] = progress["setlist"].filter((ele)=>{ return ele in tunelib } );
		// it is free to pass along tunelib in progress[] object
		progress["tunelib"] = tunelib ;
		for( let callback of this.callbackList){
			callback(progress);
		}
	}

	async #backgroundProcess(){
		let progress;
		while( true ){
			// first update then wait (better response first time)
			try{
				progress = await this.getProgress();
				console.assert( progress, "progress is empty");
			}
			catch(e){
				console.error("GetProcess.#background process fetch failed", e);
			}
			await sleep_ms(this.sleep_ms);
		}
	}
	#checkCaches(progress){
		// Check if caches have to be dropped or page reloaded
		// to reload caches with fresh information.
		// this info is kept per page (not in tab storage)
		// to ensure pages are reloaded when they need it
		if( !this.stored_boot_session || !this.stored_tunelib_signature ){
			// First time only, if undefined, get current value, no other action required.
			this.stored_boot_session = progress.boot_session ;
			this.stored_tunelib_signature =  progress.tunelib_signature ;
			return ;
		}

		// Cache is refreshed on boot and when tunelib changes significantly.
		let tunelib_change = progress.tunelib_signature != this.stored_tunelib_signature ;
		let reboot = progress.boot_session != this.stored_boot_session;
		console.log("#checkCaches reboot=", reboot, "tunelib_change=", tunelib_change);
		if( tunelib_change || reboot ){
			// Force refresh of all the (registered) JsonCache objects
			// by calling their drop method
			this.dropCaches();
		}
		if( tunelib_change ){
			this.stored_tunelib_signature =  progress.tunelib_signature ;
		}
		if( reboot ){
			this.stored_boot_session = progress.boot_session ;
		}
		if( reboot || (tunelib_change && this.reloadIfTunelibChanged) ){
			// Reload page if reboot or tunelib changed EXCEPT
			// when the page asks not to do so (like tunelist.html)
			location.reload();
		}
	}

}
let commonGetProgress = new GetProgress();

class PageHeader{
	// Must be called at from each page to pass page header title,
	// and up (back arrow on header) navigation rules.
	constructor( ){
		this.bannerEmpty = "";
		this.bannerWarn = "" ; 

		this.headerdiv = document.getElementById("headerdiv");
		if( !this.headerdiv ){
			this.headerdiv = document.createElement("span");
			// 26px is the height of the headerdiv class
			this.headerdiv.innerHTML = `
<div class="headerdiv" id="headerdiv" style="line-height:25px">
  <a id="uparrow" class="headerleft" style="color:white">&nbsp;&#11013;</a>
  &nbsp;&nbsp;&nbsp;
  <span id="headerTitle"></span>
  <span class="headerright">
	<span id="batterySymbol" style="background-color:white"></span>
	<span id="batteryTime"></span>  
		&nbsp;&nbsp;&nbsp;
	<span id="connectSymbol" style="background-color:white">&#x2006;&#x2001;&#x2006;</span>
	<span id="connectText">&#x205F;</span>
  </span>
</div>
<h2 id="banner" style="display:none"></h2>`;
			document.body.prepend(this.headerdiv);
			document.getElementById("uparrow").addEventListener( "click", ()=>{ this.#pageUp()});

			// launch getting document title (async) in parallel but don't wait here.
			this.#setDocumentTitle();
		}
	}

	async #setDocumentTitle(){
		let j = await configCache.get();
		document.title = j["description"];
	}

	// Called at the start of each page
	setTitle( headerTitle, pageupAction ){
		// pageupAction is one of:
		// 		a function that handles the page up (go back), used by file manager for folders
		// 		"back" meaning history.back() 
		// 		a page name like "index" or "tunelist" (no /static/, no .html)
		// 		null, meaning: this is the index page, no arrow.
		textById( "headerTitle", headerTitle );
		this.pageupAction = pageupAction;
		// Hide arrow for pages like the index page which has no action here.
		showHideElement( "uparrow", pageupAction );
		// Launch update header background tasks
		commonGetProgress.registerCallback( (progress)=>this.#updateBattery(progress) );
		commonGetProgress.registerCallback( (progress)=>this.#updateBanner(progress) );
		this.#updateConnectedProcess();
	}
	setBannerInfo( empty, bannerWarn ){
		// Allow pages to set their own banner text
		// and the prefix of warning messages. tunelibedit.html
		// has a bit different messages in the banner.
		this.bannerEmpty = empty; // queue empty
		this.bannerWarn = bannerWarn ; // Warning prefix, either "" or "!"
	}
	#pageUp(){
		if( typeof this.pageupAction == "function"){
			return this.pageupAction();
		}
		let from = document.referrer;
		if( from == undefined || from.includes(this.pageupAction) || this.pageupAction == "back" ){
			// to be faster: if the previous page is the "up" page, go back
			history.back();
		}
		else{
			// Came from another page (not the parent) navigate to this page
			window.location.href = "/static/" + this.pageupAction + ".html" ;
		}
	}
	async #updateConnectedProcess( ){
		// not depending on progress, asks fetch_json for status.

		while( true ){
			await sleep_ms( 5_000 );
			let isConnected = fetch_json.isConnected();
			if( isConnected ){
				// 🛜 Wifi  💚green heart. 💕two hearts 
				// see here for spaces https://jkorpela.fi/chars/spaces.html
				// \u2006 thin space. \u205f medium space
				textById("connectSymbol", "\u2006💚\u2006"); 
				textById("connectText", "\u205F"); 
			}
			else{
				// 💔 &#x1f494; broken heart + six per em space
				textById("connectSymbol", "\u2006💔\u2006"); 
				textById("connectText", tlt("no conectado")+"\u205F"); 
			}
			showHideElement( "batterySymbol", isConnected );
			showHideElement( "batteryTime", isConnected );
		}
	}
	
	#updateBattery(progress){
		let normal_background = sap_green ;
		// Check if calibration done. percent_remaining is a number
		// only if calibration done, as are "low" and "remaining_seconds"
		if( is_no_number(progress["bat_percent_remaining"])){
			// No calibration done, don't bother requesting
			// information about battery any more
			return ;
		}	
		let header_background = normal_background ;
		let batterySymbol = document.getElementById("batterySymbol");

		if( progress["bat_low"] ) {
			// Low battery emoji on white background
			batterySymbol.innerText = "🪫"; // low battery &#x1faab;
			header_background = meter_red_color ;
		}
		else {
			// Normal green battery emoji on white background
			batterySymbol.innerText = "🔋"; // full battery &#x1f50b;
			header_background = normal_background;
		}
		document.getElementById("headerdiv").style.backgroundColor = header_background;
	
		textById( "batteryTime",  
					"" + Math.round( progress["bat_percent_remaining"] ) 
					+ "% " 
					+ format_secHHMM( progress["bat_remaining_seconds"] ) ) ;
	}

	#updateBanner(progress){
		// Banner is always present, courtesy of this class.
		let banner_element = document.getElementById("banner");
		let banner = "";
		
		// Order is by priority of message.
	 	if( progress["sync_pending"]){
	 		if( progress["status"] == "playing" ){
	 			banner = this.bannerWarn + tlt( "Cambios a la espera que la música termine");
			}
			else{
				banner = this.bannerWarn + tlt("Cambios almacenados, actualización pendiente")
			}
		}
		else if( !progress["playback_enabled"]){
			banner = tlt("Tocar música deshabilitado por afinador, pinout");
		}
	    else if( progress["automatic_delay"] ){
	 		banner = tlt("Partida automática activada") + `, ${progress["automatic_delay"]} s` ;
	 	}

		if( banner == "" ){
			// page (such as tunelibedit.html) can set own text here
			banner = this.bannerEmpty;
		}
		banner_element.innerText = banner ;
		banner_element.style.display = banner ? "": "none" ;
	}
}

// Formatting of numbers with locale information
let locale ;
if( navigator.languages.length > 0 ) {
	locale = navigator.languages[0] ;
}
else {
	locale = "en-US" ;
}
let numberFormatter = Intl.NumberFormat(locale, useGrouping="auto") ;

function formatIfNumber( newText ) {
	let formatText = newText ;
	// Format if number. If not: leave unchanged.
	if( /^\-?[0-9]+\.?[0-9]*$/.test(formatText) )  {
		try{
			let n = parseInt( newText );
			if( 0 <= n && n <= 2100 ){
				// don't format years
				return newText;
			}
		}
		catch{
			// Ignore errors, go ahead ;
		}
	   formatText = " " + numberFormatter.format(+formatText) ;
	}
	return formatText ;
}

// Functions to change innerText and innerHTML of DOM element by id
function textById( id, newText ) {
	// Format if number or boolean
    let formattedNewText ;
	if( newText === true ){
		formattedNewText = "✔️" ;
	}
	else if( newText === false ){
		formattedNewText = "❌" ;
        }
	else if( newText == undefined || newText == null ){
		formattedNewText = "-" ;
	}
	else {
		formattedNewText = formatIfNumber( newText ) ;
	}
  	document.getElementById(id).innerText = formattedNewText ;
}

// DOM helper functions to show/hide, set text and html by id.
function showHideElement(id, value ){
	let d = document.getElementById( id );
	if( value == "" || value == null || 
		value == undefined  || value == false ){
		d.style.display = "none" ;
	}
	else {
		d.style.display = "" ;
	}
}

function htmlById( id, htmlText ) {
	let element = document.getElementById(id);
	if( htmlText == "" && element.innerHTML == "" ){
		// a bit of optimization for large lists like
		// tunelist or history page. Saves a bit of energy
		return;
	}
	element.innerHTML = htmlText ;
}

function htmlByIdIgnoreErrors( id, htmlText ){
    try {
        htmlById( id, htmlText ) ;
    }
    catch( error ) {
        // do nothing   
        ;
    }
}

function setAllTextById( json_result ) {
    // Set DOM elements by ID with matching key in json_result.
	for( const [key, value] of Object.entries(json_result)) {
		textById( key, value );
	}
}

// Tunelib.json columns, function to verify if correct.
TLCOL_ID = 0 ;
TLCOL_TITLE = 1 ;
TLCOL_GENRE = 2 ;
TLCOL_AUTHOR = 3 ;
TLCOL_YEAR = 4 ;
TLCOL_TIME = 5 ;
TLCOL_FILENAME = 6 ;
TLCOL_AUTOPLAY = 7 ;
TLCOL_INFO = 8 ;
TLCOL_DATEADDED = 9 ;
TLCOL_RATING = 10 ;
TLCOL_SIZE = 11 ;
TLCOL_HISTORY = 12 ;
TLCOL_LYRICS = 13 ; // lyrics present
TLCOL_COLUMNS = 14 ;


function map_tlcol_names( header_map ){
	// initializing here because:
	// 1. tlt is not defined before
	// 2. check_translations.py knows about tlt
	if( typeof map_tlcol_names.tlcol_names == "undefined" ){
		map_tlcol_names.tlcol_names = [
			"", tlt("Título"), tlt("Género"), tlt("Autor"), tlt("Año"), tlt("Duración"),
			tlt("Nombre archivo"), tlt("Autoplay"), tlt("Info"), tlt("Fecha"),
			tlt("Puntaje"), tlt("Tamaño"), tlt("Hist"), tlt("Letra")
		] ;
	}
	if( typeof header_map.map == "function"){
		return header_map.map((ele) =>  map_tlcol_names.tlcol_names[ele]);
	}
	else{
		return map_tlcol_names.tlcol_names[header_map];
	}
}
async function showPopup(id_where, show_text) {
	// show a popup message for some seconds, then hide automatically
    if( show_text === null ){
        return ;
    }
	let popup = document.getElementById("popup") ;
	if( !popup ){
		// <span id="popup" class="popuptext"></span>
		popup = document.createElement("span");
		popup.id = "popup";
		popup.classList.add("popuptext");
		document.body.appendChild( popup );
	}
	popup.innerText = show_text;
	let saveWidth = popup.style.width ;
	let saveHeight = popup.style.height; 
	popup.style.height = "70px" ;
	popup.style.width = "200px" ;
    let boundingRect ;
	if( id_where.length > 0 ){
		docElement = document.getElementById(id_where) ;
		boundingRect = docElement.getBoundingClientRect() ;
		popup.style.left = (boundingRect.left + (boundingRect.width*1.3+50)) + "px";
		popup.style.top = (boundingRect.top + window.pageYOffset) + "px";
	}
	else {
		popup.style.left = "200px";
		popup.style.left = (window.pageXOffset + window.screen.width/5);
		popup.style.top = (window.pageYOffset + window.screen.height/3) + "px";
	}

	popup.style.visibility = "visible" ;
	await sleep_ms(3_000);
	popup.style.visibility = "hidden" ;
	popup.style.width = saveWidth ;
	popup.style.height = saveHeight ;
}


function escapeHtml(text) {
    let el = document.createElement("div");
  	el.innerText = text;
  	return el.innerHTML
}

function removeSpecialHtmlChars( text ){
    return text.replace(/[&<>"']/g, "");
}

class JsonCache{
	constructor(url, postOnly=false ){
		this.url = url;
		this.postOnly = postOnly;
		this.reentry = 0;
		this.theData = null;
		// It's better to drop on reboot, to ensure configuration
		// changes take effect here after reboot
		commonGetProgress.registerCache( this );
	}
	async get(post){
		if( this.theData != null ){
			return this.theData;
		}
		if( !post && this.postOnly ){
			return ;
		}
		// avoid reentering the critical section, if not,
		// the same element may be asked for twice, slowing down
		// the system.
		this.reentry += 1;
		while( this.reentry > 1 ){
			await sleep_ms(50);
		}
		let data = null;
		try{
			// sessionStorage is a good place: valid for multiple pages on the same tab.
			// User can clear sessionStorage by changing tab (unlike localStorage) in case of problems.
			// Cache API does not work since we use http and not https.
			data = sessionStorage.getItem( this.url );
			if( !data || typeof data != "string" || (data.substring(0,1) != "{" && data.substring(0,1) != "["))	{
				data = JSON.stringify( await fetch_json( this.url, post ));
				sessionStorage.setItem( this.url,  data )  ;
			}
		}
		catch(e){
			console.error("JsonCache get failed", e);
			this.reentry -= 1;
			throw e ;
		}
		this.reentry -= 1;
		// JSON.parse takes about 1msec for 100kb tunelib with 600 tunes.
		this.theData = JSON.parse( data ) ;
		return this.theData;
	}
	drop(){
		console.log("cache drop", this.url );
		sessionStorage.removeItem( this.url  );
		this.theData = null;
	}

}
let tunelibCache = new JsonCache("/data/tunelib.json");
let lyricsCache = new JsonCache("/data/lyrics.json");
async function lyricsCacheTuneid( tuneid ){
	// If no lyrics available, return empty string
	return ((await lyricsCache.get())[tuneid]) || "";
}
let configCache = new JsonCache("/data/config.json");
async function isMultipleSetlistsEnabled(){
	let config = await configCache.get();
	return config["multiple_setlists"];
}


function formatRating( tune ){
	return tune[TLCOL_RATING].replace(/\*/g, "⭐"); //&#x2B50;
}

// Function for mcserver
function isUsedFromDemo(){
	return (""+window.location.href).includes("/demo/");
}
function isUsedFromIOT(){
	return (""+window.location.href).includes("/iot/");
}
function isUsedFromServer(){
	// True if this page resides on the drehorgel.pythonanywhere.com server
	// as IOT crank organ component (via mcserver)
	return isUsedFromDemo() || isUsedFromIOT();
}


let programNameList = [
    "any",
    "Acoustic Grand Piano",
    "Bright Acoustic Piano",
    "Electric Grand Piano",
    "Honky-tonk Piano",
    "Electric Piano 1",
    "Electric Piano 2",
    "Harpsichord",
    "Clavi",
    "Celesta",
    "Glockenspiel",
    "Music Box",
    "Vibraphone",
    "Marimba",
    "Xylophone",
    "Tubular Bells",
    "Dulcimer",
    "Drawbar Organ",
    "Percussive Organ",
    "Rock Organ",
    "Church Organ",
    "Reed Organ",
    "Accordion",
    "Harmonica",
    "Tango Accordion",
    "Acoustic Guitar (nylon)",
    "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)",
    "Electric Guitar (clean)",
    "Electric Guitar (muted)",
    "Overdriven Guitar",
    "Distortion Guitar",
    "Guitar Harmonics",
    "Acoustic ",
    "Electric  (finger)",
    "Electric  (pick)",
    "Fretless ",
    "Slap  1",
    "Slap  2",
    "Synth  1",
    "Synth  2",
    "Violin",
    "Viola",
    "Cello",
    "Contra",
    "Tremolo Strings",
    "Pizzicato Strings",
    "Orchestral Harp",
    "Timpani",
    "String Ensemble 1",
    "String Ensemble 2",
    "Synth Strings 1",
    "Synth Strings 2",
    "Choir Aahs",
    "Voice Oohs",
    "Synth Voice",
    "Orchestra Hit",
    "Trumpet",
    "Trombone",
    "Tuba",
    "Muted Trumpet",
    "French Horn",
    "Brass Section",
    "Synth Brass 1",
    "Synth Brass 2",
    "Soprano Sax",
    "Alto Sax",
    "Tenor Sax",
    "Baritone Sax",
    "Oboe",
    "English Horn",
    "oon",
    "Clarinet",
    "Piccolo",
    "Flute",
    "Recorder",
    "Pan Flute",
    "Blown bottle",
    "Shakuhachi",
    "Whistle",
    "Ocarina",
    "Lead 1 (square",
    "Lead 2 (sawtooth)",
    "Lead 3 (calliope)",
    "Lead 4 (chiff)",
    "Lead 5 (charang)",
    "Lead 6 (voice)",
    "Lead 7 (fifths)",
    "Lead 8 ( + lead)",
    "Pad 1 (new age)",
    "Pad 2 (warm)",
    "Pad 3 (polysynth)",
    "Pad 4 (choir)",
    "Pad 5 (bowed)",
    "Pad 6 (metallic)",
    "Pad 7 (halo)",
    "Pad 8 (sweep)",
    "FX 1 (rain)",
    "FX 2 (soundtrack)",
    "FX 3 (crystal=",
    "FX 4 (atmosphere)",
    "FX 5 (brightness)",
    "FX 6 (goblins)",
    "FX 7 (echoes)",
    "FX 8 (sci-fi)",
    "Sitar",
    "Banjo",
    "Shamisen",
    "Koto",
    "Kalimba",
    "Bag pipe",
    "Fiddle",
    "Shanai",
    "Tinkle Bell",
    "Agogô",
    "Steel Drums",
    "Woodblock",
    "Taiko Drum",
    "Melodic Tom",
    "Synth Drum",
    "Reverse Cymbal",
    "Guitar Fret Noise",
    "Breath Noise",
    "Seashore",
    "Bird Tweet",
    "Telephone Ring",
    "Helicopter",
    "Applause",
    "Gunshot",
    "drum"]
// Translate MIDI program number to program name
function program_name( program_number ){
		if( program_number == "" ){
			return programNameList[0];
		}
		try{
			return programNameList[ parseInt( program_number )];
		}
		catch{
			return "???";
		}
		
}

function noteName( midi ){
    let note_list = [ "C", "C#/Db", "D", "D#/Eb", "E", "F", "F#/Gb", "G", "G#/Ab", "A", "A#/Bb", "B" ];
    let nn =  note_list[ midi%12 ] + Math.floor( (midi/12) - 1 );
    return nn;
}

function insertRow( body, data ){
	let row = body.insertRow(-1);
	for( v of data ){
		if( v == undefined || v == null ){
			v = "";
		}
		row.insertCell(-1).innerText = "" + v ;
	}
	return row;
}


// Encodes a Unicode filename so that it can be
// added to the url
function encodePath( path ){
	let p = path.normalize("NFKC");
    // https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURIComponent
    return (
    encodeURIComponent(p)
      // The following creates the sequences %27 %28 %29 %2A (Note that
      // the valid encoding of "*" is %2A, which necessitates calling
      // toUpperCase() to properly encode). Although RFC3986 reserves "!",
      // RFC5987 does not, so we do not need to escape it.
      .replace(
        /['()*]/g,
        (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
      )
      // The following are not required for percent-encoding per RFC5987,
      // so we can allow for a little better readability over the wire: |`^
      .replace(/%(7C|60|5E)/g, (str, hex) =>
        String.fromCharCode(parseInt(hex, 16)),
      )
  );
}

class PasswordDialog{
	static initialize(){
		let modalDialog = document.getElementById( "modalPasswordDialog" );
		if( modalDialog == undefined ){
			modalDialog = document.createElement("div");
			modalDialog.id = "modalPasswordDialog";
			modalDialog.classList.add("modal");
			modalDialog.innerHTML = `
			<div class="modal-content">
			<span id="passwordX" class="close"">&times;</span>
			<br>
			<span id="enter_password"></span>
			<br>
			<input id="passwordInput" type="password" size="20"/>
			<br>
			<button id="passwordOkButton"></button>
			<button id="passwordCancelButton"></button>
			</div>
			`;
			document.body.appendChild( modalDialog );
			document.getElementById("enter_password").innerText = tlt("Password:") ;
			document.getElementById("passwordOkButton").innerText = tlt("Aceptar");
			document.getElementById("passwordCancelButton").innerText = tlt("Cancelar") ;
			
			let ok = document.getElementById( "passwordOkButton")
			ok.addEventListener( "click", ()=>this.#clickOk() );
			let cancel = document.getElementById( "passwordCancelButton")
			cancel.addEventListener( "click", ()=>this.#clickCancel() );
			let x = document.getElementById( "passwordX")
			x.addEventListener( "click", ()=>this.#clickCancel() );
			this.modalDialog = modalDialog;
			this.passwordInput = document.getElementById( "passwordInput");
			this.waitingForPassword = "";
		}
	}

	static #clickCancel(){
		this.passwordInput.value = "";
		this.waitingForPassword = "cancel";
	}

	static async #clickOk(){
		let hp = this.#hashPassword( this.passwordInput.value );
		try{
			await fetch_json( "/verify_password", { "password": hp } );
			// Password valid, close dialog
			// Error 401 should  disappear next fetch_json
			this.waitingForPassword = "ok";
			this.passwordInput.value = "";

		}
		catch{
		}
		this.passwordInput.value = "";
		// Continue waiting until cancel or password entered		
	}
	static #hashPassword( password ){
    	const data = getCookie( "session") + "_" + password ;
    	return  buf2hex( sha256( new TextEncoder().encode( data ) ) );
	}

	constructor(){
		PasswordDialog.initialize();
	}

	async askAndVerify(){
		PasswordDialog.passwordInput.value = "";
		PasswordDialog.waitingForPassword = "";
		PasswordDialog.modalDialog.style.display = "block";
		while( PasswordDialog.waitingForPassword == ""){
			await sleep_ms(1000);
		}
		PasswordDialog.modalDialog.style.display = "none";
		return PasswordDialog.waitingForPassword == "ok";	
	}
	
}

// Share current time zone information with server
async function setTimezone(){
	let offsetMinutes = new Date().getTimezoneOffset();
	let timeInfo = new Date().toLocaleString([], {timeZoneName:"short"}).split(" ");
	let shortName = timeInfo[timeInfo.length-1];
	let longName = Intl.DateTimeFormat().resolvedOptions().timeZone; 
	// Allow only posts with this cache, this prevents race condition with index.html's cach refill
	if( !setTimezone.cache ){
		setTimezone.cache = new JsonCache("/set_time_zone", postOnly=true ) ;
	}
	// fetch_json will be done only once 
	await setTimezone.cache.get({"offset": offsetMinutes*60, 
			  "shortName":shortName,
			  "longName": longName,
			  // current time in Unix epoch seconds
			  "timestamp": Math.round( Date.now()/1000 )
			 });
	// if get() should be called without a post (GetProgress.fillCaches)
	// the postOnly ensures it is not sent.
}
// Calling this in background does not interfere with page load
// Since the call is cached, this means effectively one call per boot session
setTimezone();


// https://github.com/6502/sha256
//
// Copyright 2022 Andrea Griffini
// MIT License
// sha256(data) returns the digest
// sha256() returns an object you can call .add(data) zero or more time and .digest() at the end
// digest is a 32-byte Uint8Array
// Input should be either a string (that will be encoded as UTF-8) or an array-like object with values 0..255.
function sha256(data) {
    let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a,
        h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19,
        tsz = 0, bp = 0;
    const k = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
               0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
               0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
               0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
               0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
               0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
               0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
               0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2],
          rrot = (x, n) => (x >>> n) | (x << (32-n)),
          w = new Uint32Array(64),
          buf = new Uint8Array(64),
          process = () => {
              for (let j=0,r=0; j<16; j++,r+=4) {
                  w[j] = (buf[r]<<24) | (buf[r+1]<<16) | (buf[r+2]<<8) | buf[r+3];
              }
              for (let j=16; j<64; j++) {
                  let s0 = rrot(w[j-15], 7) ^ rrot(w[j-15], 18) ^ (w[j-15] >>> 3);
                  let s1 = rrot(w[j-2], 17) ^ rrot(w[j-2], 19) ^ (w[j-2] >>> 10);
                  w[j] = (w[j-16] + s0 + w[j-7] + s1) | 0;
              }
              let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
              for (let j=0; j<64; j++) {
                  let S1 = rrot(e, 6) ^ rrot(e, 11) ^ rrot(e, 25),
                      ch = (e & f) ^ ((~e) & g),
                      t1 = (h + S1 + ch + k[j] + w[j]) | 0,
                      S0 = rrot(a, 2) ^ rrot(a, 13) ^ rrot(a, 22),
                      maj = (a & b) ^ (a & c) ^ (b & c),
                      t2 = (S0 + maj) | 0;
                  h = g; g = f; f = e; e = (d + t1)|0; d = c; c = b; b = a; a = (t1 + t2)|0;
              }
              h0 = (h0 + a)|0; h1 = (h1 + b)|0; h2 = (h2 + c)|0; h3 = (h3 + d)|0;
              h4 = (h4 + e)|0; h5 = (h5 + f)|0; h6 = (h6 + g)|0; h7 = (h7 + h)|0;
              bp = 0;
          },
          add = data => {
              if (typeof data === "string") {
                  data = typeof TextEncoder === "undefined" ? Buffer.from(data) : (new TextEncoder).encode(data);
              }
              for (let i=0; i<data.length; i++) {
                  buf[bp++] = data[i];
                  if (bp === 64) process();
              }
              tsz += data.length;
          },
          digest = () => {
              buf[bp++] = 0x80; if (bp == 64) process();
              if (bp + 8 > 64) {
                  while (bp < 64) buf[bp++] = 0x00;
                  process();
              }
              while (bp < 58) buf[bp++] = 0x00;
              // Max number of bytes is 35,184,372,088,831
              let L = tsz * 8;
              buf[bp++] = (L / 1099511627776.) & 255;
              buf[bp++] = (L / 4294967296.) & 255;
              buf[bp++] = L >>> 24;
              buf[bp++] = (L >>> 16) & 255;
              buf[bp++] = (L >>> 8) & 255;
              buf[bp++] = L & 255;
              process();
              let reply = new Uint8Array(32);
              reply[ 0] = h0 >>> 24; reply[ 1] = (h0 >>> 16) & 255; reply[ 2] = (h0 >>> 8) & 255; reply[ 3] = h0 & 255;
              reply[ 4] = h1 >>> 24; reply[ 5] = (h1 >>> 16) & 255; reply[ 6] = (h1 >>> 8) & 255; reply[ 7] = h1 & 255;
              reply[ 8] = h2 >>> 24; reply[ 9] = (h2 >>> 16) & 255; reply[10] = (h2 >>> 8) & 255; reply[11] = h2 & 255;
              reply[12] = h3 >>> 24; reply[13] = (h3 >>> 16) & 255; reply[14] = (h3 >>> 8) & 255; reply[15] = h3 & 255;
              reply[16] = h4 >>> 24; reply[17] = (h4 >>> 16) & 255; reply[18] = (h4 >>> 8) & 255; reply[19] = h4 & 255;
              reply[20] = h5 >>> 24; reply[21] = (h5 >>> 16) & 255; reply[22] = (h5 >>> 8) & 255; reply[23] = h5 & 255;
              reply[24] = h6 >>> 24; reply[25] = (h6 >>> 16) & 255; reply[26] = (h6 >>> 8) & 255; reply[27] = h6 & 255;
              reply[28] = h7 >>> 24; reply[29] = (h7 >>> 16) & 255; reply[30] = (h7 >>> 8) & 255; reply[31] = h7 & 255;
              reply.hex = () => {
                  let res = "";
                  reply.forEach(x => res += ("0" + x.toString(16)).slice(-2));
                  return res;
              };
              return reply;
          };
    if (data === undefined) return {add, digest};
    add(data);
    return digest();
}

function buf2hex(buffer) { // buffer is an ArrayBuffer
    // https://stackoverflow.com/questions/40031688/how-can-i-convert-an-arraybuffer-to-a-hexadecimal-string-hex
    return [...new Uint8Array(buffer)]
      .map(x => x.toString(16).padStart(2, '0'))
      .join('');
}

function getCookie(cname) {
  const name = cname + "=";
  const decodedCookie = decodeURIComponent(document.cookie);
  const ca = decodedCookie.split(';');
  for(let i = 0; i <ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) == ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) == 0) {
      return c.substring(name.length, c.length);
    }
  }
  alert("No session cookie avaiable, cannot process password" );
  throw new Error( "No session cookie available" );
}
function hashWithSeed( s ){
    const data = getCookie( "session") + "_" + s ;
    return hexdigest = buf2hex( sha256( new TextEncoder().encode( data ) ) );
}


async function queueTune( tuneid, slot ) {
    let spectator_name = "" ;
    if( isUsedFromIOT()  ){
        let resp = await fetch_json( "/get_spectator_name" ) ;
        spectator_name = resp["spectator_name"] ;
        while( spectator_name == "" ){
            spectator_name = window.prompt(tlt("¿Cuál es tu nombre?")).trim().replace(/<\/?[^>]+(>|$)/g, "");
        }
    }
	// make a text to show in showPopup below
	let slot_text = "";
	if( slot ){
		slot_text = slot;
	}
	showPopup( "", tlt("Actualizando setlist")+ " " + slot_text);
    postdata = { 
        "spectator_name": spectator_name, 
        "tuneid": tuneid, 
        "slot": slot } ;
	// queue tune and update page with result
	await commonGetProgress.fetchJson( "/queue_tune", postdata ) ;
}


// The title of a tune
class TuneTitle extends HTMLSpanElement{
	static lastProgress;
	static updateProgress( progress ){
		// Called by commonGetProgress.#backgroundProcess() for periodic update
		// Called by commonGetProcess.get() on the pages to force update immediately
		// Called by visibilityChange() below to update when scrolling uncovers tune titles.
		if(!progress){
			return ; // can happen if lastProgress has not been initialized yet
		}
		// Store progress to update titles while scrolling
		TuneTitle.lastProgress = progress;
		// Update only visible TuneTitle elements of this page
		for( let element of document.getElementsByClassName("tune-title-visible")){
			element.updateProgress( progress );
		}

	}
	static async backgroundUpdateProgress( progress ){
		// Wait a bit before updating to diminish forced reflow violations
		// i.e. accumulate some changes before updating progress.
		await sleep_ms(50);
		TuneTitle.updateProgress( progress );
	}
	static visibilityChanges( entries ){
		// Page has scrolled, update TitleTunes that entered/exited viewport.
		for( let entry of entries ){
			// Add/remove class according to visibility in viewport
			if( entry.isIntersecting ){
				entry.target.classList.add("tune-title-visible");
			}
			else{
				entry.target.classList.remove("tune-title-visible");
			}
		}
		
		// Could update only elements changed to visible, but this is fast enough.
		// since there are normally no more than 10 or 30 tune titles visible depending on zoom level.
		TuneTitle.backgroundUpdateProgress( TuneTitle.lastProgress );
	}
	// Set up callback when TuneTitle enters and when it exits the viewport.
	static observer = new IntersectionObserver( TuneTitle.visibilityChanges );

	constructor(){
		super();
		this.options ={ beforeFormat:"", afterFormat:"", shortClick:false, menu:false }

		this.setlistMenu = document.createElement( "button", {is:"setlist-menu"})
		this.before = document.createElement( "span" );
		this.titleLink = document.createElement("a");
		this.titleLink.style.cursor = "pointer";
		this.after = document.createElement( "span" );

		this.appendChild( this.setlistMenu );
		this.appendChild( this.before );
		this.appendChild( this.titleLink );
		this.appendChild( this.after );
		// don't add listener twice, not even by error.
		this.listenerAdded = false;

		// Add to list of elements updated by the IntersectionObserver
		TuneTitle.observer.observe(this);
	}
	connectedCallback(){
		if( this.listenerAdded ){
			// Allow to add this element twice to a document, needed for sort
			return; 
		}
		this.listenerAdded = true ;
		// If short click is disabled, that is handled in #shortClick()
		// this makes assigning the event easier.
		this.titleLink.addEventListener("click", ()=>{this.#shortClick()} );
	}

	// Set tune is designed to be called once for a tune-title
	// and then updateProgress() is called to update the title
	// with the current progress.
	setTune( tune, options ){
		this.options = options ;
		// format characters
		//		h =  shows hourglass symbol/musical symbol
		//		p = setlist position
		//		m = microphone for lyrics
		//		t = title in bold while playing
		//		% = percentage and bar graph
		//		s = spectator
		//		d = duration
		// { beforeFormat:"hptm%sd", afterFormat:"hptm%sd", shortClick:true, menu:true }
		// shortClick
		//		true: allow short click
		//		false: short click does nothing, not formatted as link
		// menu:
		//		true: show multiple setlist menu
		//		false: don't show multiple setlist menu
		// Caller must check isMultipleSetlistsEnabled().
		// This is not done here, no opportunity for an async function.... :-(
		this.tune = tune ;
		this.tuneid = tune[TLCOL_ID];
		// if there is menu leave a space &nbsp; \u00a0 before the title
		this.titleLink.innerText =  this.options.menu ? "\u00a0"+tune[TLCOL_TITLE]:tune[TLCOL_TITLE];

		if( this.options.shortClick ){
			this.titleLink.classList.add( "anohref" ); 
			// If setTune() needs to be called again
			// to update the title, then remove the classes
			//this.titleLink.classList.remove("a");
			//this.titleLink.classList.remove("anoshortclick");
		}
		else{
			this.titleLink.classList.add("anoshortclick");
			//this.titleLink.classList.remove( "anohref" ); 
		}
		this.setlistMenu.setOperation( "queueTune", tune, this.options.menu );

		this.setlistMenu.style.display = this.options.menu  ? "":"none";
	}

	updateProgress( progress ){
		function format( self, c ){
			let result = "";
			if( c == "h"){
				if( is_playing  ) {
					result = "🎵"; // musical note &#127925;
				}
				else if( in_setlist ){
					result =  "⏳"; // Hourglass &#x23F3;
				}
			}
			else if( c == "t"){
				if( is_playing ){
					self.titleLink.style.fontWeight = "bold";
				}
				else if(self.titleLink.style.fontWeight != "normal"){
						self.titleLink.style.fontWeight = "normal";
				}
			}
			else if( c == "p"){
				if( position>=0 ){
					result = `(${position+1}) `;
				}
			}
			else if( c == "%"){
				if( is_playing ){
					let percent = progress["playtime"]/self.tune[TLCOL_TIME]*100 ;
					if( isNaN(percent)){
						percent = 0 ;
					}
					// 0-10: 1 block advance, 90-99: minus 1 block
					result =  "\u00A0" + Math.round(percent) + "%\u00A0";
					let blocks = Math.floor(percent/10);
					// darkBlock = "￭"    &#xffed; halfwidth Black Square
		            // lightBlock = "･"   &#xff65; halfwidth katakana Middle Dot
					result += "￭".repeat(blocks) + "･".repeat(10-blocks) + "\u00A0";
				}
			}
			else if( c == "m"){
				if( self.tune[TLCOL_LYRICS]){
					result = "🎤\u00A0"; // microphone + non blank space
				}
			}
			else if( c == "s"){
				let spectator_name = tune_requests[ self.tuneid ];
				if( spectator_name ){
					result = "\u00A0-\u00A0" + escapeHtml(spectator_name) + "\u00A0";
				}
			}
			else if( c == "d"){
				result = "\u00A0" + formatMilliMMSS( self.tune[TLCOL_TIME] ) + "\u00A0";
			}
			return result;
		}
		const setlist = progress["setlist"]
		const is_playing = (this.tuneid == progress["tune"] && progress["status"] == "playing");
		let position = setlist.indexOf( this.tuneid );
		const in_setlist = (position >= 0);
		// Update only tunes in setlist
		let tune_requests = progress["tune_requests"] ;
		if( tune_requests == undefined ){
			tune_requests = {} ;
		}
		let before = "";
		let after = "";
		for( let c of this.options.beforeFormat ){
			before += format( this, c );
		}
		for( let c of this.options.afterFormat ){
			after += format( this, c );
		}
		// this optimization would not work if before/after had spaces
		// If there is a change, one TuneTitle.updateProgress takes 7msec per tune on PC
		// If there is no change, one TuneTitle.updateProgress takes 0.02 msec per tune
		if( this.before.innerText != before ){
			this.before.innerText = before;
		}
		if( this.after.innerText != after ){
			this.after.innerText = after ;
		}

	}
	#shortClick(){
		if( this.options.shortClick  ){
			// queueTune is async, might also be await queueTune()
			queueTune( this.tuneid, 0 );
		}
	}
}
customElements.define("tune-title", TuneTitle, { extends: "span" });

class SetlistMenu extends HTMLButtonElement{
	// implements the popup menu with all setlists.
	// Used in the following contexts:
	// * on a title (play.html, tunelist.html, history.html)
	// * for the load setlist and save setlist buttons on play.html
	static dialog = null;
	static assignMenuHandlers = true;

	// used to pass information to static handlers
	// while menu is open (can be open only once, because
	// it is blocking)
	static tuneid = "";
	static tune = [];
	static operation = "";

	static async #slotClick( slot ){
		if( SetlistMenu.operation == "queueTune" ){
			await queueTune( SetlistMenu.tuneid, slot );
		}
		else if( SetlistMenu.operation == "loadSetlist" ){
			await fetch_json( "/load_setlist", {"slot": slot} );
		}
		else if( SetlistMenu.operation == "saveSetlist"){
			await fetch_json( "/save_setlist", {"slot": slot} );
			showPopup( "", tlt("Setlist guardada") + " " + slot);

		}
		SetlistMenu.#close();
	}
	static async #openTunelibChangeDialog( tlcol ){
		let textMap = new Map();
		// >>> redesign if all columns are prompted
		textMap.set( TLCOL_RATING, tlt("Ingrese") + " " + map_tlcol_names(TLCOL_RATING));
		textMap.set( TLCOL_INFO, tlt("Ingrese") + " " + map_tlcol_names(TLCOL_INFO));
		// TLCOL_RATING, TLCOL_INFO, 
		// TLCOL_TITLE, TLCOL_AUTHOR, TLCOL_GENRE, TLCOL_YEAR, TLCOL_AUTOPLAY
		let text = textMap.get(tlcol);
		let info = prompt( text + " " + SetlistMenu.tune[TLCOL_TITLE], SetlistMenu.tune[tlcol] );
		if( info != null ){
			const TLOP_REPLACE_FIELD = 3; // see tunemanager.py

			// send a list of tuples just as /save_tunelib likes it
			// just with one change, but its a list of lists...
		// >>> should rating be limited to * ** and ***?
			await fetch_json( "/save_tunelib", [[TLOP_REPLACE_FIELD, SetlistMenu.tuneid, tlcol, info]] );
			showPopup("", tlt("Cambios almacenados, actualización pendiente")); 
			await sleep_ms(1000);
		}
	}

	static async #openSetlistDialog(){
		await SetlistTitleDialog.open();
		SetlistMenu.#close();
	}

	static #close(){
		SetlistMenu.dialog.style.display = "none";
	}

	constructor( ){
		
		super();
		this.style.cursor = "pointer";

		// Share a single modal div for the pop up menu
		SetlistMenu.dialog = document.getElementById("setlistMenu");
		if( SetlistMenu.dialog == undefined ){
			SetlistMenu.dialog = document.createElement("div");
			SetlistMenu.dialog.id = "setlistMenu";
			SetlistMenu.dialog.classList.add("modal");
			SetlistMenu.dialog.innerHTML = `
 <div class="modal-content">  
	<h3><span id="menuTitle" class="tune-only"></span></h3>
	<ul style="list-style-type:none;">
	<li><span id="menuCaption"></span></li>
	<li><a id="menuSlot1" class="anohref"></a></li>
	<li><a id="menuSlot2" class="anohref"></a></li>
	<li><a id="menuSlot3" class="anohref"></a></li>
	<li><a id="menuSlot4" class="anohref"></a></li>
	<li><a id="menuSlot5" class="anohref"></a></li>
	<li><a id="menuSlot6" class="anohref"></a></li>
	<li><a id="menuSlot7" class="anohref"></a></li>
	<li><a id="menuSlot8" class="anohref"></a></li>
	<li><a id="menuSlot9" class="anohref"></a></li>
	<li>─────────</li>
	<li><a id="menuInfo"  class="tune-only anohref"></a></li>
	<li><a id="menuRating"  class="tune-only anohref"></a></li>
	<li><a id="menuSetlistTitles" class="anohref"></a></li>
	</ul>
</div>`;
			document.body.append( SetlistMenu.dialog );
		}
	}

	
	connectedCallback(){
		// call #open() when the menu button is clicked.
		this.addEventListener( "click", ()=>{this.#open()});

		function assignMenuCallback( id, callback ){
			document.getElementById(id).addEventListener( "click", callback );
		}
		if( SetlistMenu.assignMenuHandlers ){
			// do this once only for the only only dialog shared by all instances
			SetlistMenu.assignMenuHandlers = false;
			for( let slot=1; slot<=9; slot++ ){
				assignMenuCallback( "menuSlot"+slot, ()=>SetlistMenu.#slotClick(slot) );
			}
			assignMenuCallback( "menuInfo", ()=>SetlistMenu.#openTunelibChangeDialog(TLCOL_INFO)) ;
			assignMenuCallback( "menuRating", ()=>SetlistMenu.#openTunelibChangeDialog(TLCOL_RATING) );			

			assignMenuCallback( "menuSetlistTitles", ()=>SetlistMenu.#openSetlistDialog() );
			// click on something that is not a menu option
			// will close the popup
			document.addEventListener( "click", ()=>SetlistMenu.#close() );
		
			// translate text only once
			let tlcol_names = map_tlcol_names([TLCOL_INFO, TLCOL_RATING]);
			htmlById( "menuInfo", "ℹ️ " + tlcol_names[0] + "...<br>");
			htmlById( "menuRating", "⭐ " + tlcol_names[1] + "...<br>");
			htmlById( "menuSetlistTitles", "🎩" + tlt("Cambiar titulos de setlists...") + "<br>");
		}
	}
	setOperation( op, tune, menu ){
		// op is one of these:
		//		"saveSetlist"
		//		"loadSetlist"
		//		"queueTune"
		// tune is a tune object for "queueTune" i.e. tune[] TLCOL indexable array
		// menu: true if multiple setlist enabled, false if only one setlist
		this.operation = op ;
		this.tune = null;
		this.tuneid = null;
		this.menu = menu;
		if( op == "queueTune" ){
			this.tune = tune;
			this.tuneid = tune[TLCOL_ID];
			// here is the menu character
			this.innerText = "⋮ " ; // (U+2630☰) (U+2261≡) (U+22EE⋮)
			// Make character a bit bigger
			this.classList.add("title-menu-button");
			// this.style.fontSize = "110%";
			// this.style.fontWeight = "bold";
			// this.style.padding = "0px 0px 0px 0px";
			// this.style.height = "100%";
			// this.style.lineHeight = "100%"; // line height set equal to font size
			// this.style.borderRadius = "2px";
			// this.style.marginBottom = "2px";
			// this.style.marginTop = "0px";
			// this.style.marginRight = "0px";
			// this.style.marginLeft = "0px";
		}
		else if( op == "loadSetlist" ){
			// this is the button text
			this.innerText = tlt("Cargar setlist");
		}
		else if( op == "saveSetlist"){
			// thisis the button text
			this.innerText = tlt("Guardar setlist");
		}
	}

	async #open( ){
		// pass the current state to the event listeners
		// of the popup menu in here. Since only one modal dialog
		// of this class can be active at a given time, there is no clash.
		SetlistMenu.operation = this.operation;
		SetlistMenu.tuneid = this.tuneid;
		SetlistMenu.tune = this.tune;

		if( !this.menu ){
			// No menu, only one setlist, call the action right away and that's it.
			await SetlistMenu.#slotClick(1);
			return;
		}
		const keycaps = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"];
		let titles =  await fetch_json( "/get_setlist_titles" );
		for( let [slot,title,tunes] of titles ){
			// info: [slot_number 1-9, title, number of tunes in setlist]
			// If no title use caption (no title)
			textById("menuSlot"+slot,
			`${keycaps[slot]} ${title||tlt("(sin título)")} (${tunes})`);
		}
		let caption = "???";
		let showTuneOnly = false ;
		if( this.operation == "queueTune" ){
			htmlById( "menuTitle",  this.tune[TLCOL_TITLE]);
			caption = tlt("Agregar a setlist");
			showTuneOnly = true;
		}
		else if( this.operation  == "loadSetlist"){
			// this is the popup menu caption
			caption = tlt("Cargar setlist actual desde:");
		}
		else if( this.operation  == "saveSetlist"){
			// this is the popup menu caption
			caption = tlt("Guardar setlist actual en:");
		}
		// apply caption, show tune-only elements
		for( let element of document.getElementsByClassName("tune-only")){
			showHideElement( element.id, showTuneOnly );
		}
		textById( "menuCaption", caption );

		SetlistMenu.dialog.style.display = "block";
	}

}
customElements.define( "setlist-menu", SetlistMenu, { extends: "button"});

class SetlistTitleDialog extends HTMLDivElement{
	// This is the only entry point:
	// await SetlistTitleDialog.open()
	static async open(){
		// Create one and only one custom DOM object with
		// the setlist dialog and then open the dialog.
		let sld = document.getElementById("setlistDialog")
		if( sld == undefined ){
			sld = document.createElement("div", {is:"setlist-title-dialog"});
			sld.id = "setlistDialog";
			document.body.appendChild( sld );
		}
		await sld.open();
	}

	constructor(){
		super();
		this.classList.add("modal");
		this.innerHTML =  `
    <div class="modal-content">   
		<span id="setlistCloseX" class="close">&times;</span>
	  	1️⃣ <input id="setlistTitle1" type="text" size="20"><br>
		2️⃣ <input id="setlistTitle2" type="text" size="20"><br>
		3️⃣ <input id="setlistTitle3" type="text" size="20"><br>
		4️⃣ <input id="setlistTitle4" type="text" size="20"><br>
		5️⃣ <input id="setlistTitle5" type="text" size="20"><br>
		6️⃣ <input id="setlistTitle6" type="text" size="20"><br>
		7️⃣ <input id="setlistTitle7" type="text" size="20"><br>
		8️⃣ <input id="setlistTitle8" type="text" size="20"><br>
		9️⃣ <input id="setlistTitle9" type="text" size="20"><br>
		<button id="setlistSave"></button>
		<button id="setlistCloseButton"></button>
    </div>`;

	}
	connectedCallback(){
		function assignDialogCallback( id, callback){
			document.getElementById(id).addEventListener( "click", callback );
		}
		assignDialogCallback( "setlistCloseButton", ()=>this.#close() );
		assignDialogCallback( "setlistCloseX", ()=>this.#close() );
		assignDialogCallback( "setlistSave", ()=>this.#save() );
		
		textById( "setlistSave", tlt("Guardar"));
		textById( "setlistCloseButton", tlt("Cancelar"));

	}
	async open(){
		let titles = await fetch_json( "/get_setlist_titles" );
		for( let info of titles ){
			let slot = info[0];
			// Slot is 1-9
			document.getElementById( "setlistTitle"+slot ).value = info[1] ;
		}
		this.style.display = "block";
	}
	async #save(){
		// titles must have 10 elements, element 0 is current setlist but
		// never shown anywhere
		let titles = ["current"];
		for( let slot = 1; slot <= 9; slot++  ){
			titles.push( document.getElementById(`setlistTitle${slot}`).value );
		}
		await fetch_json( "/save_setlist_titles", titles );
		this.#close();
		showPopup( "", tlt("Guardando setlist"));
	}
	#close(){
		this.style.display = "none";
	}
}
customElements.define( "setlist-title-dialog", SetlistTitleDialog, { extends: "div"});

// Translation functions. Data is in translations.js
// Translation functions tlt and translate_html are in common.js
// Translate a string with current languge
function tlt( s ){
	if( typeof languageIndex === "undefined"){
		// no translations.js present, don't translate
		return s;
	}
	let tlist = translationDict[s.toLowerCase()];
	if( tlist == undefined || tlist[languageIndex] == undefined){
		return s ;
	}
    return tlist[languageIndex];
}


function translate_html(){
	// Translates bottom level html DOM elements
	// Must be run by page to be translated once the DOM
	// elements are loaded.
	// Dynamic DOM elements have to be translated by tlt function
	if( typeof languageIndex === "undefined" ){
		// no translations.js present
		return;
	}
	let all = document.getElementsByTagName("*");
	for (let i=0, max=all.length; i < max; i++) {
		let d = all[i] ;
		let localName = d.localName ;
		if( ["html", "meta", "body", "script", "head", "table", "tbody", "thead", "tr"].includes(localName)){
			continue ;
		}
		let innerHTML = d.innerHTML ;
		if( innerHTML == undefined ||  innerHTML.includes("<") ){
			// Don't try tro translate if no text or if there is a tag
			continue ;
		}
		d.innerText = tlt(d.innerText) ;
	}
}


