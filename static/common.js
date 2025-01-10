// Copyright (c) 2023 Hermann von Borries
// MIT License

let MAX_DB = -20 ;
let MIN_DB = -0 ;

let MAX_CENTS = 50 ;
let CENTS_LIMIT = 5 ;

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
meter_grey = "#e8e8e8" ;
progress_color = "#3EA8A3" ; 


// Many useful functions
function is_no_number( n ){
	// Is it enough to check isNaN()?
	return n == null || n == undefined || isNaN(n) ;
}

function format02i( n ) {
	if( is_no_number(n)){
		return "-"
	};
    // to be used in formatMilliMMSS and format_secHHMM
	let ss = "" + Math.round( n );
	if( ss.length == 1 ) {
			ss = "0" + ss ;
	} 
	return ss ;
}

function formatMilliMMSS( msec ){
	if( is_no_number(msec)){
		return "-"
	};
	let t = msec / 1_000 ;
	let ss = format02i( t%60 ) ;
	return "" + Math.floor(t/60) + ":" + ss ;
}

function format_secHHMM( sec ) {
	if( is_no_number(sec)){
		return "-"
	};
	let t = sec/60 ;
	let mm = format02i( t%60 );
	return "" + Math.floor(t/60) + ":" + mm ;
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
        return r*1 ;
    }
}



//>>> still used for velocity
function barGraph( container_name, value, color, scale_divisions, alignment, width_percent ) {
	// barGraph on container, must create canvas
	let canvas_name = container_name + "canvas" ;
	let canvas = document.getElementById(canvas_name) ;
	if( canvas === null ) {
		let cd = document.getElementById( container_name );
		let w = Math.round( window.innerWidth * width_percent/100 *0.98);
		let h = 15 ;
		let s = '<canvas id="' + canvas_name + '" width=' + w + ' height=' + h + '>' + 'canvas dentro de ' + container_name + '</canvas>' ;
		cd.innerHTML = s ;
		canvas = document.getElementById(canvas_name) ;
	}
	canvasBarGraph( canvas, value, color, scale_divisions, alignment ) ;
}


function canvasBarGraph(canvas, value, color, scale_divisions, 
	alignment ) {
	// low level bar graph, on canvas
	let ctx = canvas.getContext("2d") ;
	let cw = canvas.width ;
	let ch = canvas.height ;
	ctx.beginPath();
	ctx.lineWidth = 0;
	// Erase rectangle (fill with white)
	ctx.fillStyle = "#ffffff" ;
	ctx.fillRect(0,0,cw,ch) ;
	// Paint bar
	ctx.fillStyle = color ;
	let c = value ;
	if( c > 1 ){
		c = 1 ;
	}
	if( c < -1 ) {
		c = -1 ;
	}
	if( alignment === "left" ) {
		ctx.fillRect(0,0, c*cw, ch) ;
	}
	else {
		ctx.fillRect((1-c)*cw, 0, cw, ch) ;
	}

	ctx.strokeStyle = "#ffffff" ;
	ctx.lineWidth = 4 ;
	for( let i = 0 ; i < scale_divisions ; i++ ){
		w = cw*i/scale_divisions ;
		ctx.moveTo( w, ch ) ;
		ctx.lineTo( w, ch*0.75) ;
	}
	ctx.stroke() ;	

	ctx.beginPath() ;
	ctx.strokeStyle = color ;
	ctx.fillStyle = color ;
	ctx.lineWidth = 2 ;
	ctx.rect( 0, 0, cw, ch) ;
	ctx.stroke() ;	
}

function drawNeedle( ctx, needle_pos, cw, ch ){
	if( needle_pos < 2 ){
		needle_pos = 2 ;
	}
	if( needle_pos > cw-2 ) {
		needle_pos = cw-2 ;
	}
	ctx.beginPath();
	ctx.lineWidth = 1 ;
	ctx.lineStyle = "#FFFFFF" ;
	ctx.moveTo( needle_pos-1, ch-5 ) ;
	ctx.lineTo( needle_pos, ch*0.2 ) ;
	ctx.lineTo( needle_pos+1, ch-5 ) ;
	ctx.closePath() ;
	ctx.fillStyle = "#000000" ;
	ctx.fill() ;
	ctx.stroke();
	ctx.beginPath();
	ctx.lineWidth = 1 ;
	ctx.lineStyle = "#000000" ;
	ctx.fillStyle = "#FFFFFF"
	ctx.arc( needle_pos, ch-4, 3, 0, 6.3 ) ;
	ctx.fill();
	ctx.stroke();
}
function getCanvas( container_name, canvas_id, width_percent ){
	let canvas_name = container_name + canvas_id ;
	if( document.getElementById(canvas_name) === null ) {
		let cd = document.getElementById( container_name ) ;
		// compute width for graphics and text
		let w = window.innerWidth*width_percent/100*0.98 ;
		let h = 20 ;
		let s = `<canvas id="${canvas_name}"  width="${w}" height="${h}"></canvas>`;
		cd.innerHTML = s ;
	}
	
	return document.getElementById( canvas_name ) ;	
}
function centsBar( container_name, cents, width_percent ) {

	let canvas = getCanvas( container_name, "_centsBarCanvas", width_percent ) ;
	let ctx = canvas.getContext("2d") ;
	let cw = canvas.width ;
	
	let ch = canvas.height ;
	let limit_pos = cw*CENTS_LIMIT/MAX_CENTS/2;
	
	ctx.fillStyle = meter_grey ;
	ctx.beginPath();
	ctx.lineWidth = 0;
	// 0.8 to leave space for needle
	ctx.fillRect( 0,0, cw, ch*0.8 ) ;
	ctx.stroke();

	let needle_pos = cw/2 + cw*cents/MAX_CENTS/2 ;
    
	if( cents < -CENTS_LIMIT  ) {
		ctx.fillStyle = meter_red_color ;
		ctx.beginPath();
		ctx.lineWidth = 0;
		ctx.fillRect( needle_pos,0, cw/2-needle_pos, ch*0.8 ) ;
		ctx.stroke();
	}
	else if( cents > CENTS_LIMIT  ) {
		ctx.fillStyle = meter_red_color ;
		ctx.beginPath();
		ctx.lineWidth = 0;
		ctx.fillRect( cw/2,0, needle_pos-cw/2, ch*0.8 ) ;
		ctx.stroke();
	}
	
	ctx.beginPath() ;
	ctx.fillStyle = meter_green_color ;
	ctx.fillRect( cw/2-limit_pos, 0, limit_pos*2, ch*0.8 ) ;
	ctx.stroke() ;
	
	

	drawNeedle( ctx, needle_pos, cw, ch );
	
}

function dbBar( container_name, db, width_percent ) {
	let MINVALUE = MAX_DB ;
	let MAXVALUE = MIN_DB ;

	let canvas = getCanvas( container_name, "_dbBarCanvas", width_percent ) ;
	let ctx = canvas.getContext("2d") ;
	let cw = canvas.width ;
	let ch = canvas.height ;
	
	ctx.fillStyle = meter_grey ;
	ctx.beginPath();
	ctx.lineWidth = 0;
	// 0.8 to leave space for needle
	ctx.fillRect( 0,0, cw, ch*0.8 ) ;
	ctx.stroke();
	
	let pos = cw*( db-MINVALUE)/(MAXVALUE-MINVALUE) ;
	ctx.beginPath() ;
	ctx.fillStyle = meter_green_color ;
	init_pos = Math.max(pos, 3);
	ctx.fillRect( init_pos, 0, cw-init_pos-4, ch*0.8 ) ;
	ctx.stroke() ;
	
	drawNeedle( ctx, pos, cw, ch );
}

function progressBar( container_name, percent, width_percent ){
	let canvas = getCanvas( container_name, "_progressBarCanvas", width_percent ) ;

	let ctx = canvas.getContext("2d") ;
	let cw = canvas.width ;
	let ch = canvas.height ;
	

	ctx.beginPath();
	ctx.fillStyle = meter_grey ;
	ctx.fillRect( 0, 0, cw, ch );
	ctx.stroke() ;
	
	ctx.beginPath();
	ctx.fillStyle = progress_color ;
	pos = percent/100*cw ;
	ctx.fillRect( 0, 0, pos, ch );
	ctx.stroke() ;
}


function velocityBar( container_name, velocity, width_percent ) {
    needleBar( container_name, velocity, width_percent, 0, 100, "_velocityBarCanvas") ;
}

function rpsecBar( container_name, rpsec, width_percent ) {
    needleBar( container_name, velocity, width_percent, 0, 2, "_rpsecyBarCanvas") ; 
}

function needleBar( container_name, velocity, width_percent, minvalue, maxvalue, canvas_suffix) {

	let canvas = getCanvas( container_name, canvas_suffix, width_percent ) ;
	let ctx = canvas.getContext("2d") ;
	let cw = canvas.width ;
	let ch = canvas.height ;
	ctx.beginPath() ;
	ctx.fillStyle = "#ffffff";
	ctx.fillRect( 0, 0, cw, ch );
	ctx.stroke() ;
	
	ctx.beginPath() ;
	ctx.fillStyle = meter_grey ;
	ctx.beginPath();
	ctx.lineWidth = 0;
	// 0.8 to leave space for needle
	ctx.fillRect( 0,0, cw, ch*0.8 ) ;
	ctx.stroke();
	
	ctx.beginPath();
	ctx.lineWidth = 1 ;
	ctx.moveTo( cw/2, 0 ) ;
	ctx.lineTo( cw/2, ch*0.8 )
	ctx.stroke() ;
	
	let needle_pos = cw*(velocity-minvalue)/(maxvalue-minvalue);
	ctx.beginPath() ;
	ctx.fillStyle = meter_green_color ;
	ctx.fillRect( cw/2, 0, needle_pos-cw/2, ch*0.8 ) ;
	ctx.stroke() ;
	
	
	drawNeedle( ctx, needle_pos, cw, ch );
	
}

// Function to fetch a json from server.
// Retries communication until successful.
async function fetch_json( url, post_data ){
    let t0 ;
    let t ;
    let response ;
    let json_result ;
	let post_arg = make_fetch_args( post_data ) ;
	while( true ) {
		try {
            t0 = Date.now() ;  // Reports response time
            response = {};
			response = await fetch( url, post_arg ) ;
			break ;
		}
		catch( err ) {
			console.log("fetch json failed", err, "url=", url ) ;
            // In the header battery time, replace battery
            // icon and time remaining with "network connection broken"
            // symbol.
			msg = "not connected" ;
            htmlByIdIgnoreErrors( "header_time",
                                 msg + " &#x1f494;") ;
			popupmsg = (msg + " " + err).replace("TypeError", "Network error" ) ;
			showPopup( "", popupmsg );
			await sleep_ms( 5_000 ) ;
		}
		// retry fetch forever until getting through to server
	}
	if( !response.ok ){
		// Response not ok will notify error to user and abort throwing an error
        let rstatus = response.status ;
		if( rstatus == 401 ){
			let button = await askForPassword() ;
			// Now we have to retry...!!!
			if( button == "ok" ){
				return await fetch_json( url, post_data );
			}
			// Fall through and generate 401 message if cancel was pressed.
		}
        response_html = await response.text() ; 
        response_text = response_html.replace(/<[^>]*>/g, ' ');
        console.log("Error response", rstatus, "url", url, "response", response, "text", response_text ) ;
        alert( `Server error ${rstatus} ${response_text}` ) ;
        throw new Error(`Server sent error status {response.status}`);
		// Fetch calls and call function will abort unless
		// there is a try/catch block.
	}
	json_result = await response.json() ; 
   
    t = Date.now() - t0;
	console.log("fetch_json ", url, "response time", t, "msec");
    
	// If there is an alert, show to user and reraise exception
	if( json_result["alert"]) {
		alert( json_result["alert"] ) ;
	}
	if(json_result["error"]){
			throw new Error("Error signalled by server: " + json_result.alert + " url " + url ) ;
		// respond_error_alert() prevents calling code to continue
		// (except when enclosing fetch_json in try/catch)
	}
	return json_result;
	
}

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

// Refresh battery info in header
// fetch_json also updates header_time element when
// connection to server fails.
async function updateHeader() {
	let d = document.getElementById( "header_time" ) ;
	if( d === null ) {
		// A page might have no battery time element in the header
		return ;
	}
    // Get the normal background color of the header div
    let elements = document.getElementsByClassName("headerdiv");
    let normal_background = elements[0].style.backgroundColor ;
    // Wait a bit for other requests, than show battery
    // info on a freshly loaded page.
	await sleep_ms( 1_000 );
	while( true ) {
		let battery = await fetch_json( "/battery" ) ;
		let batteryText = "" ;
		// Check if calibration done. percent_remaining is a number
		// only if calibration done, as are "low" and "remaining_seconds"
		if( is_no_number(battery["percent_remaining"])){
			// No calibration done, don't bother requesting
			// information about battery any more
			htmlById( "header_time", "" ) ;
			return ;
		}
		let header_time = document.getElementById( "header_time" );
		let ht_symbol = document.getElementById ( "ht_symbol" );
		if( !ht_symbol ){
			let ht_symbol = document.createElement( "span" );
			ht_symbol.id = "ht_symbol";
			ht_symbol.style.backgroundColor = "white";
			header_time.appendChild( ht_symbol );
			let ht_text =  document.createElement( "ht_text" );
			ht_text.id = "ht_text";
			header_time.appendChild( ht_text );
		}
		ht_symbol = document.getElementById ( "ht_symbol" );
		let ht_text = document.getElementById( "ht_text" );

		if( battery["low"] ) {
			// Low battery emoji on white background
			ht_symbol.innerHTML = "&#x1faab;"; 
			// Change background color if low
			header_background = meter_red_color ;
		}
		else {
			// Normal green battery emoji on white background
			ht_symbol.innerHTML = "&#x1f50b;"
			header_background = normal_background;
		}
		elements = document.getElementsByClassName("headerdiv");
		for (let i = 0; i < elements.length; i++) {
			// Should be only one headerdiv, but this covers all
			elements[i].style.backgroundColor = header_background;
		} 
		ht_text.innerHTML = "&nbsp;" + Math.round( battery["percent_remaining"] ) 
					+ "%&nbsp;" 
					+ format_secHHMM( battery["remaining_seconds"] ) ;

        // Battery info gets updated once a minute.
        // Refresh display about twice a minute, that's more than enough 
        // since battery info changes slowly.
		await sleep_ms( 24_000 ) ;
	}
}
// Run battery info update in it's own async task
updateHeader() ; 

function make_status_text( progress_status, percentage ) {
	// Transform player status to language
    let status_text ;
	if (progress_status === "ended") {
		status_text = "ended" ;
	}
	else if(progress_status === "playing" ) {
		status_text = "" + Math.round(percentage) + "%" ;
	}
	else if(progress_status === "cancelled" ) {
		status_text = "cancelled" ;
	}
    else if( progress_status == "waiting"){
        status_text = "\u231B waiting" ;
    }
	else {
		status_text = progress_status ;
	}
	return status_text ;
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
	document.getElementById(id).innerHTML = htmlText ;
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
TLCOL_RFU = 13 ;
TLCOL_COLUMNS = 14 ;


async function showPopup(id_where, show_text) {
    if( show_text === null ){
        return ;
    }
	// needs <span id="popup" class="popuptext"></span>
	// in some place of the <body>
	let popup = document.getElementById("popup") ;
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


function currentPage(){
    let path = window.location.pathname;
    return path.split("/").pop();
}

// Cache a json file 
async function cache_json( path ) {
	let data = sessionStorage.getItem( path );
	if( data == null || data == undefined || data == "undefined"){
        console.log("getting json from net for cache:", path ) ;
		let json_for_cache = await fetch_json( path );
        sessionStorage.setItem( path, JSON.stringify( json_for_cache ) ) ;
		return json_for_cache ;
	}
	return JSON.parse( data ) ;
}

// Drop cached json, next time cache_json() is called
// data will be retrieved again from server
function drop_cache( path ){
	sessionStorage.removeItem( path );
}

// Get tunelib.json and cache in tab storage for fast access
// drop_tunelib() is called when the tunelib is changed
// by the user.
async function get_tunelib() {
	return await cache_json( "/data/tunelib.json" ) ;
}

// Drop tunelib, next time get_tunelib() is called
// data will be retrieved again from server
function drop_tunelib(){
	drop_cache( "/data/tunelib.json" ) ;
}

async function get_lyrics( tuneid ){
	data = await cache_json( "/data/lyrics.json" ) ;
	lyrics = data[tuneid] ;
	if( lyrics == undefined || lyrics == null ){
		return "";
	}
	return lyrics ;
}
function drop_lyrics() {
	drop_cache( "/data/lyrics.json" );
}

function pageUp(pagename){
    from = document.referrer;
    if( from == undefined || from.includes(pagename) || pagename == undefined ){
        // to be faster: if the previous page is the "up" page, go back
        // This could lead to another page of the same name in history
        // Tough luck.
        history.back();
    }
    else{
		let p = pagename ;
		if( !p.endsWith(".html") ){
			p = p + ".html";
		}
		if( p.indexOf("static") == -1 ){
			p = "/static/" + p ;
		}
        // Came from other page, navigate to this page
        window.location.href = p ;
    }
}


function get_rating( tune ){
	return tune[TLCOL_RATING].replace(/\*/g, "⭐"); //&#x2B50;
}

function isUsedFromServer(){
	// True if this page resides on the drehorgel.pythonanywhere.com server
	// as IOT crank organ component (via mcserver)
	let url = ""+window.location.href;
	return url.indexOf("/iot/") != -1;
}

async function setPageTitle(){
	// Set page title
	let pt = document.getElementById( "pagetitle" );
	if( pt == undefined || pt.innerText != "" ){
		return ;
	}
	// cache description in tab storage for efficiency
	let j = await cache_json("/get_description");
	pt.innerText = j.description ;
}
setPageTitle() ;


async function commonGetProgress() {
	let stored_boot_session = sessionStorage.getItem( "boot_session" );
	let progress = await fetch_json( "/get_progress/" + stored_boot_session  );
	console.log("get progress", progress );
	// This is a good place to check, progress is used
	// with tunelib and lyrics...
	if( progress.boot_session != stored_boot_session ){
		// Force refresh of tunelib and lyrics on reboot.
		drop_tunelib();
		drop_lyrics();
		sessionStorage.setItem(  "boot_session", progress.boot_session) ;
	}
	return progress ;
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

async function makeTuneTitle( tune ){
	let mic = "" ;
	let lyrics = await get_lyrics(tune[TLCOL_ID]);
	if( lyrics.length > 0 ){
		mic = "🎤";
	}
	return tune[TLCOL_TITLE] + mic ;
}

// Encodes a Unicode filename so that it can be
// added to the url, like in: /delete_file/%2Fmy%20file.txt
function encodePath( path ){
	let p = path.normalize("NFC");
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

// Having two browsers asking for login concurrently might not work...
let waitingForPassword = "" ;

function cancelPasswordDialog(){
	let modalPasswordDialog = document.getElementById( "modalPasswordDialog" );
	modalPasswordDialog.style.display = "none";
	waitingForPassword = "cancel";
}

async function okPasswordDialog(){
	let hp = hashWithSeed( document.getElementById( "passwordInput" ).value );
	while( true ){
		try{
			await fetch_json( "/verify_password", { "password": hp} );
			// Password valid, close dialog
			// Error 401 should  disappear next fetch_json
			break;
		}
		catch{
			// Wait until cancel or password entered
			return ;
		}
	}
	waitingForPassword = "ok";
}

async function askForPassword(){
	waitingForPassword = "" ;

    let modalPasswordDialog = document.getElementById( "modalPasswordDialog" );
    if( modalPasswordDialog == undefined ){
        modalPasswordDialog = document.createElement("div");
        modalPasswordDialog.id = "modalPasswordDialog";
		modalPasswordDialog.classList.add("modal");
        modalPasswordDialog.innerHTML = `
        <div class="modal-content">
          <span class="close" onclick="cancelPasswordDialog()">&times;</span>
          <br>
		  Enter password:
		  <br>
          <input id="passwordInput" type="password" size="20"/>
          <br>
          <button onclick="okPasswordDialog()">OK</button>
          <button onclick="cancelPasswordDialog()">Cancel</button>
        </div>
        `;
		document.body.appendChild( modalPasswordDialog );
    }

    modalPasswordDialog.style.display = "block";
	document.getElementById("passwordInput").value = "";
	while( waitingForPassword == ""){
		await sleep_ms(100);
	}
	modalPasswordDialog.style.display = "none";
	return waitingForPassword;
}

// Share current time zone information with server
async function setTimezone(){
	let offsetMinutes = new Date().getTimezoneOffset();
	let timeInfo = new Date().toLocaleString([], {timeZoneName:"short"}).split(" ");
	let shortName = timeInfo[timeInfo.length-1];
	let longName = Intl.DateTimeFormat().resolvedOptions().timeZone; 
	await fetch_json( "/set_time_zone", 
		post={"offset": offsetMinutes*60, 
			  "shortName":shortName,
			  "longName": longName,
			  // current time in Unix epoch seconds
			  "timestamp": Math.round( Date.now()/1000)
			 });	
}
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
