
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


function format02i( n ) {
    // to be used in formatMilliMMSS and format_secHHMM
	let ss = "" + Math.round( n );
	if( ss.length == 1 ) {
			ss = "0" + ss ;
	} 
	return ss ;
}
	
function formatMilliMMSS( msec ){
	let t = msec / 1_000 ;
	let ss = format02i( t%60 ) ;
	return "" + Math.floor(t/60) + ":" + ss ;
}

function format_secHHMM( sec ) {
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
        console.log("getResourceFromUrl", r, r.includes("html"), r.includes("json") ) ;
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
		let cd = document.getElementById( container_name )
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
	if( needle_pos < 2 ) {
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
	
	needle_pos = cw*(velocity-minvalue)/(maxvalue-minvalue);
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
            console.log("fetch json try", url, "post=", post_arg ) ;
            t0 = Date.now() ;  // Reports response time
            response = {} ;
			response = await fetch( url, post_arg ) ;
			break ;
		}
		catch( err ) {
			console.log("fetch json failed", err, url, "ok", response.ok, "status", response.status ) ;
            // In the header battery time, replace battery
            // icon and time remaining with message
            // symbols.
			msg = "no conectado" ;
            htmlByIdIgnoreErrors( "header_time",
                                 msg + " &#x1f494;") ;
			popupmsg = (msg + " " + err).replace("TypeError", "Network error" ) ;
			showPopup( "", popupmsg );
			await sleep_ms( 5_000 ) ;
		}
	}

	if( !response.ok ){
		// Response not ok will abort and notify error to user.
        status = response.status ;
        response_html = await response.text() ; 
        response_text = response_html.replace(/<[^>]*>/g, ' ');
        console.log("Error response", status, "url", url, "response", response, "text", response_text ) ;
        alert( `Server error ${status} ${response_text}` ) ;
        return ;
	}

    json_result = await response.json() ;    
    t = Date.now() - t0;
	console.log("fetch_json ok response time " + url + " " + t + " msec");
    
	// Return result if json does not say "alert"
	if( json_result["alert"] === undefined ) {
		return json_result;
	}
	alert( json_result["alert"] ) ;
	throw new Error("Alert " + json_result["alert"] + " url " + url ) ;
	
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
    // Wait a bit for other requests, than show battery
    // info on a freshly loaded page.
	await sleep_ms( 1_000 );
	while( true ) {
		let battery = await fetch_json( "/battery" ) ;
        let batteryText = "" ;
		if( battery["low"] ) {
			// Low battery emoji on BlanchedAlmond background
			batteryText = "<span style='background-color:#FFEBCD'>&#x1faab;</span>" ;
		}
		else {
			// Normal green battery emoji on white background
			batteryText = "<span style='background-color:white'>&#x1f50b;</span>" ;
		}
        batteryText += "&nbsp;" + Math.round( 100-battery["percent_used"] ) + "%&nbsp;";
		batteryText += format_secHHMM( battery["time_remaining"] ) ;

        if( battery["capacity"] != "no_battery" ){
            htmlById( "header_time", batteryText ) ;
        }
        else {
            htmlById( "header_time", "" );
        }
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
		status_text = "fin" ;
	}
	else if(progress_status === "playing" ) {
		status_text = "" + Math.round(percentage) + "%" ;
	}
	else if(progress_status === "cancelled" ) {
		status_text = "cancelado" ;
	}
    else if( progress_status == "waiting"){
        status_text = "\u231B esperando" ;
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
	else {
		formattedNewText = formatIfNumber( newText ) ;
	}
    // console.log("text by id",id, formattedNewText ) ;
	document.getElementById(id).innerText = formattedNewText ;
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
        console.log("setAlLText", key );
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
TLCOL_COLUMNS = 13 ;


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



async function revoke_credentials(){
    try {
        await fetch( "/revoke_credentials" );
        // Expected: must return 401 not authorized
    }   
    catch(e) {
        console.log("Credentials revoked: ", e ) ;
    }
}

function escapeHtml(text) {
  var map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  
  return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function removeSpecialHtml( text ){
    return text.replace(/[&<>"']/g, "");
}
function currentPage(){
    let path = window.location.pathname;
    return path.split("/").pop();
}

// Cached tunelib >>> add expiration date?
//>>>> replace with standard cache?????
async function get_tunelib() {
	let data = sessionStorage.getItem( "tunelib" );
	if( data == null || data == undefined || data == "undefined"){
        console.log("getting data from net") ;
		let tunelib = await fetch_json( "/data/tunelib.json" );
        let history = await fetch_json( "/data/history.json" )
        for(i in history){
            histitem = history[i];
            tuneid = histitem[0];
            tune = tunelib[tuneid];
            if( tune == undefined || tune == null ){
                continue ;
            }
            if( histitem[2] > 90){
                tune[TLCOL_HISTORY] += 1 ;
            }   
        }
        sessionStorage.setItem( "tunelib", JSON.stringify( tunelib ) ) ;
		return tunelib ;
	}
	return JSON.parse( data ) ;
}
function drop_tunelib(){
	// call from tunelibedit
	sessionStorage.removeItem( "tunelib" );
}
function pageUp(pagename){
    from = document.referrer;
    if( from == undefined || from.includes("/static/"+pagename+".html") || pagename == undefined ){
        // to be faster: if the previous page is the "up" page, go back
        // This could lead to another page of the same name in history
        // Tough luck.
        history.back();
    }
    else{
        // Came from other page, navigate to this page
        window.location.href = "/static/" + pagename + ".html" ;
    }
}
