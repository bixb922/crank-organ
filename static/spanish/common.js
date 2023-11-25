scale_divisions_db = 4 ;
max_db = -20 ;
min_db = -0 ;

scale_divisions_cents = 10 ;
max_cents = 50 ;


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


function list_average( list ){
    let total = 0 ;
    let elements = 0 ;
    for( let i in list ){
        let e = list[i] ;
        // Discard null, 
        if( !isNaN(e) && e != 1 && e != -9999 & e != -99 ){
            total += list[i] ;
            elements += 1 ;
        }
    }
    if( elements == 0 ) {
        return null ;
    }
    return total / elements ;
}

function get_max_amplitude( notelist ){
    let max_amplitude = 0 ;
    for( let m in notelist ){
        let note = notelist[m] ;
        amplist = note["amplist"] ;
        for( let i in amplist ){
            let amp = amplist[i] ;
            // discard null, -99, -9999, negative, cero, 1
            if( !isNaN(amp) && amp > 1 ){
                if( amp > max_amplitude ){
                    max_amplitude = amp ;
                }
            }
        }
    }
    return max_amplitude ;
}

function amplitude_to_db( amp, max_amplitude ) {
	// amp goes from 0 to a maximum of 32767
    let dbval = "-" ;
	if( amp > 0 && amp != null  && max_amplitude > 0 ) {
		dbval = 20 * Math.log10( amp/max_amplitude ) ;
		dbval = Math.round( dbval ) ;
	}
	else {
		dbval = "-" ;
	}
	return dbval;
}
	
function scale_db( db ) {
	let scaled = (db - min_db)/(max_db - min_db) ;
	return scaled ;
}

function scale_cents( cents ) {
	return cents/max_cents ;
}

function format02i( n ) {
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

function getResourceNumberFromURL(){
	let page_url = new URL(window.location.href) ;
	let path = page_url.pathname.split("/") ;
	if( path.length <= 2 ) {
		return "" ;
	}
	else {
		return path[2]*1 ; // convert to number
	}
}




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

function lrBarGraph( container_name, value, color, scale_divisions, width_percent ) {
	// lrBarGraph on container, must create 2 canvasses
	let canvas_name = container_name + "LRcanvas" ;
	if( document.getElementById(canvas_name) === null ) {
		let cd = document.getElementById( container_name )
		let w = Math.round( window.innerWidth*width_percent/100*0.98 ) ;
		let h = 15 ;
		let s = 
		'<canvas id="' + canvas_name + '" width=' + w + ' height=' + h + '>' + 'canvas dentro de ' + container_name +'</canvas>';
		cd.innerHTML = s ;
	}
	
	let canvas = document.getElementById( canvas_name ) ;
	let c = value;
	let ctx = canvas.getContext("2d") ;
	let cw = canvas.width ;
	let ch = canvas.height ;
	ctx.beginPath();
	ctx.lineWidth = 0;
	// Erase rectangle (fill with white)
	ctx.fillStyle = "#ffffff" ;
	ctx.fillRect(0,0,cw,ch) ;
	// Paint bar graph
	ctx.fillStyle = color ;
	c = value ;
	if( c > 1 ){
		c = 1 ;
	}
	if( c < -1 ) {
		c = -1 ;
	}
    let desde ;
    let hasta ;
	if( c < 0 ) {
        desde = cw/2 + c*cw/2;
		hasta = cw/2 - desde ;
		ctx.fillRect( desde, 0, hasta, ch ) ;
	}
	else {
		desde = cw/2 - 1 ;
		hasta = cw/2 + c*cw/2 - desde ;
		ctx.fillRect( desde, 0, hasta, ch ) ;
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
        console.log("Respuesta via red no ok" + response.status, "url", url, "check mode") ;

        if( response.status == 500 ) {
            // Show alert (not popup)
			alert("Server error 500 url " + url  ) ;
		}
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
		formattedNewText = "sí" ;
	}
	else if( newText === false ){
		formattedNewText = "no" ;
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
async function get_tunelib() {
	let data = sessionStorage.getItem( "tunelib" );
	if( data == null ){
		let tunelib = await fetch_json( "/data/tunelib.json" );
        sessionStorage.setItem( "tunelib", JSON.stringify( tunelib ) ) ;
		return tunelib ;
	}
    console.log("get_tunelib data", data.substr(0,30), "...");
	return JSON.parse( data ) ;
}
function drop_tunelib(){
	// call from tunelibedit
	sessionStorage.removeItem( "tunelib" );
}
