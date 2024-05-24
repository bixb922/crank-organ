// Define columns of translationDict
let languageDict = { "es": null, "en": 0, "de": 1 };

let translationDict = {
"[melodías]": // index.html 
	["[tunes]", "[Melodien]"],
"[mseg]": // diag.html 
	["[msec]", "[msec]"],
"¿cuál es tu nombre?": // tunelist.html
    ["What is your name?", "Dein Name bitte?"],
" a ": // note.html
	[" to ", " bis "],
"activa": // diag.html 
	["Active", "Active"],
"actuación": // tunelist.html 
	["Performance", "Setlist"],
"actualizando setlist": // tunelist.html 
	["updating setlist", "Setlist wird aktualisiert"],
"afinación": // note.html notelist.html 
	["Tuning", "Frequenz"],
"afinador": // index.html 
	["Tuner", "Stimmgerät"],
"afinar": // note.html 
	["Tune", "Stimmen"],
"afinar todos": // notelist.html 
	["Tune all", "Alle Noten stimmen"],
"ajuste velocidad:": // play.html 
	["Set playback speed:", "Rückgabegeschwindingkeit:"],
"al comienzo": // play.html 
	["To beginning", "Zum Anfang"],
"alcanza para": // index.html 
	["Enough for", "Reicht für"],
"alguien conectado": // diag.html 
	["Someone connected", "Jemand angeschlossen"],
"amplitud": // note.html notelist.html 
	["Amplitude", "Amplitude"],
"archivos midi": // diag.html 
	["MIDI files", "MIDI-dateien"],
"autor": // tunelist.html play.html 
	["Author", "Author"],
"avance %": // history.html 
	["% completed", "% abgespielt"],
"año": // tunelist.html play.html 
	["Year", "Jahr"],
"batería": // index.html 
	["Battery", "Batterie"],
"borrar": // history.html 
	["delete", "Löschen"],
"borrar afinación": // notelist.html 
	["Clear stored tuning", "Gespeicherte Frequenzen löschen"],
"borrar setlist": // play.html 
	["Clear setlist", "Setlist löschen"],
"🔍búsqueda": // tunelist.html 
	["🔍Search", "🔍Suche"],
"calibrar indicación batería": // index.html 
	["Calibrate battery indicators", "Batterieanzeige eichen"],
"cargar setlist": // play.html 
	["Load setlist", "Setlist laden"],
"carpeta música": // diag.html 
	["Music folder", "MIDI ordner"],
"como wifi access point": // diag.html 
	["As WiFi access point", "Als WiFi access point"],
"como wifi station": // diag.html 
	["As WiFi station", "Als WIFI-Station"],
"conectado a un ssid": // diag.html 
	["Connected to a SSID", "An SSID angeschlossen"],
"config. general": // index.html 
	["General configuration", "Allgemeine Konfiguration"],
"configuración pins/midi": // index.html 
	["Pin and MIDI configuration", "Pin und MIDI Konfiguration"],
"configuración solenoides": // diag.html 
	["Solenoid configuration", "Solenoidkonfiguration"],
"configuración wifi": // diag.html 
	["WIFI configuration", "WIFI-Konfiguration"],
"contadores batería en cero": // index.html 
	["Battery counters set to zero", "Batteriezähler auf Null"],
"control tempo": // play.html 
	["Tempo control", "Temposteuerung"],
"descripción": // diag.html 
	["Description", "Beschreibung"],
"deshabilitado por afinador, pinout": // tunelist.html play.html 
	["Disabled by tuner, pinout test", "Stimmgerät oder Pinout test aktiv, keine Musikwiedergabe"],
"desordenar setlist": // play.html 
	["Shuffle setlist", "Setlist mischen"],
"desordenar todos": // play.html 
	["Shuffle all tunes", "Alle Melodien mischen"],
"diagnóstico": // index.html diag.html 
	["System information", "Systeminformation"],
"drehorgel": // index.html 
	["Crank organ", "Drehorgel"],
"duración": // play.html 
	["Duration", "Länge"],
"días,": // history.html 
	["days,", "Tage,"],
"editar tunelib": // index.html 
	["Edit tunelib", "Tunelib bearbeiten"],
"errores)": // diag.html 
	["errors)", "Fehler)"],
"escala de prueba": // notelist.html 
	["Play scale", "Notenskala"],
"esperando": // common.js 
	["waiting", "erwartet Start"],
"fecha": // tunelist.html history.html 
	["Date", "Datum"],
"fecha/hora": // diag.html 
	["Date/Time", "Datum/Zeit"],
"fecha/hora compilación": // diag.html 
	["Compilation date/time", "Kompilationsdatum"],
"fin": // common.js 
	["end", "Ende"],
"flash libre": // diag.html 
	["Free flash", "Flash frei"],
"flash usada": // diag.html 
	["Used flash", "flash belegt"],
"girando": // play.html 
	["Turning", "Dreht"],
"guardado": // play.html 
	["Saved", "Gespeichert"],
"guardar setlist": // play.html 
	["Save setlist", "Setlist speichern"],
"género": // tunelist.html play.html 
	["Genre", "Genre"],
"hist": // tunelist.html 
	["Hist", "Wiedergaben"],
"historia": // index.html play.html history.html 
	["History", "Verlauf"],
"imagen micropython": // diag.html 
	["MicroPython image", "MicroPython image"],
"info": // tunelist.html play.html 
	["Info", "Info"],
"información actualizada": // history.html 
	["Information updated", "Information aktualisiert"],
"ingresa nivel carga actual de la batería, 100=lleno, 0=vacío (usado para estimar descarga), reset=borrar calibración": // index.html 
	["Enter current charge level of battery, 100=full, 0=empty, reset=delete calibation data. This is used to show battery level", "Gib den aktuellen Stand der Batterie an, 100=voll, 0=leer, reset=Eichungsdatei löschen (diese Information dient zur Eichung des Ladezustands der Batterie)"],
"ingrese comentario o puntaje *, ***,*** para: ": // history.html 
	["Enter comment or rating *, **, *** for: ", "Schreib Kommentar oder Bewertung *, **, *** zu: "],
"ip de clientes activos (60 segundos)": // diag.html 
	["IP of clients active in last 60 sec", "IP aktiver Kunden (60 Sek)"],
"letra": // play.html 
	["Lyrics", "Liedtext"],
"lista de melodías": // tunelist.html 
	["Tune list", "Melodieliste"],
"melodía": // history.html 
	["Tune", "Melodie"],
"melodía actual": // play.html 
	["Current tune", "Jetzige Melodie"],
"melodías tocadas": // index.html 
	["Tunes played", "Gespielte Melodien"],
"minutos": // diag.html 
	["minutes", "Minuten"],
"mostrar letra": // play.html 
	["Show lyrics", "Liedtext anzeigen"],
"mostrar setlist": // play.html 
	["Show setlist", "Setlist anzeigen"],
"nivel de batería registrado": // index.html 
	["Battery level registered", "Registiert!"],
"nivel debe estar entre 0 y 100": // index.html 
	["Level must be between 0 and 100", "Level muss zwischen 0 und 100 liegen"],
"nivel debe ser numérico": // index.html 
	["Level must be numeric", "Level muss eine Zahl sein"],
"no conectado": // common.js 
	["Not connected", "nicht angeschlossen"],
"no gira": // play.html 
	["Not turning", "Dreht nicht"],
"no guardado, error": // play.html 
	["Not saved, error", "Nicht gespeichert, Fehler aufgetreten"],
"no hay información de avance disponible": // tunelist.html play.html 
	["No progress information available", "Information über Fortschritt nicht verfügbar"],
"no hay melodía en curso": // play.html
	["No tune in progress", "Es läuft keine Melodie"],
"organillo": // index.html 
	["Crank organ", "Drehorgel"],
"partir": // play.html 
	["Start", "Start"],
"partió ftp.": // index.html 
	["FTP started", "FTP gestarted"],
"partió ftp. reiniciar microcontrolador para detener. conectarse con filezilla o windows explorer": // index.html 
	["FTP started. Reboot to stop. Connect with FileZilla or Windows Explorer", "FTP gestarted. Zum stoppen, Microcontroller aus- und wieder einschalten. Mit FileZilla o Windows Explorer anschlieẞen."],
"pedido": // history.html 
	["Request", "Wunsch"],
"pedido por": // play.html
	["Requested by", "Gewünscht von"],
"poner contadores en cero": // index.html 
	["Set battery counters to zero", "Setze Batteriezähler auf Null"],
"programa-nota": // note.html notelist.html 
	["Program-note", "Programm-Note"],
"próximo": // play.html 
	["Next", "Nächster"],
"pts": // tunelist.html 
	["Rating", "Bewertung"],
"puesto en cero": // index.html 
	["Set to zero", "Auf Null gesetzt"],
"puntos": // play.html 
	["Rating", "Bewertung"],
"ram libre": // diag.html 
	["Free RAM", "RAM frei"],
"ram usada": // diag.html 
	["Used RAM", "RAM belegt"],
"repetición": // note.html 
	["Repetition test", "Wiederholungstest"],
"rev/seg": // play.html 
	["rev/sec", "Umdrehungen/Sekunde"],
"se conecta a ssid": // diag.html 
	["Connects to SSID", "SSID"],
"setlist": // play.html 
	["Setlist", "Setlist"],
"si historia más antigua que": // history.html 
	["When older than", "Wenn älter als"],
"sonar nota": // note.html 
	["Note test", "Notentest"],
"status_text = cancelado": // common.js 
	["status_text = cancelled", "status_text = gestrichen"],
"tdremanente/td": // index.html 
	["tdRemaining/td", "tdVerbleibend/td"],
"tempo sigue manivela": // play.html 
	["Tempo follows crank speed", "Drehgeschwindingkeit beeinflusst Tempo"],
"tiempo desde reboot": // diag.html 
	["Time since reboot", "Zeit seit reboot"],
"tiempo operación": // index.html 
	["Time powered on", "Zeit operativ"],
"tiempo para gc": // diag.html 
	["gc time", "gc Zeit"],
"tiempo remanente": // index.html 
	["Remaining time", "Verbleibende Zeit"],
"tiempo solenoides energizados": // index.html 
	["Time solenoids energized", "Zeit Ventile an"],
"tiempo tocando": // index.html 
	["Time playing", "Zeit Musikwiedergabe"],
"truncada": // history.html 
	["purged", "gelöscht"],
"título": // tunelist.html play.html 
	["Title", "Titel"],
"ver log": // diag.html 
	["Show log", "Log anzeigen"],
"versión micropython": // diag.html 
	["MicroPython version", "MicroPython version"],

// Server translations
"bienvenido al organillo en internet":
	["Welcome to the crank organ on the internet", "Willkommen zur Drehorgel im Internet"],
"fotos":
    ["Fotos", "Bilder"],
"aquí está la historia, en fotos, de la construcción del organillo":	
	["Here is the construction log with photos", "Hier ist die Baugeschichte, mit Bildern"],
"cómo funciona":
	["How does it work?", "Wie funktioniert es?"],
"aquí se explica cómo funcion el organillo":
	["Here is an explanation on how this crank-organ works", "Hier ist eine Beschreibung wie die Drehorgel funktioniert"],
"melodías":
	["Tunes","Melodien"],
"aquí están todas las melodías que hoy tiene el organillo. puedes pedir que se toque una melodía pulsando el título de la canción.":
	["Here is the list of all tunes in the crank organ. You can tap a melody to request it to be played", "Hier ist die Melodieliste die in der Drehorgel gespeichert ist. Drück auf einen Titel damit die Melodie gespielt wird!"],
"melodía actual":
	["Current tune", "Gegenwärtige Melodie"],
"muestra la melodía que se esta tocando ahora ¡y tiene la letra para poder acompañar cantando!":
	["Shows the melody now playing and the lyrics to sing along!", "Zeigt die Melodie an die gerade gespielt wird, mit Liedtext zum mitsingen!"],

}

let language = navigator.language.substring(0,2) ;
let languageIndex = languageDict[language] ;
console.log("language=", language, "languageIndex=", languageIndex);

// verify all keys in lowercase, correct that if not
function verifyTranslationDict(){
	for( k in translationDict ){
		if( k != k.toLowerCase() ){
			console.log("Warning: translationDict key not in lower case", k );
			translationDict[k.toLowerCase()] = translationDict[k] ;
		}
	}
}
verifyTranslationDict() ;

// Translate a string with current languge
function tlt( s ){
	if( languageIndex == null || languageIndex == undefined){
		return s;
	}
	let tlist = translationDict[s.toLowerCase()];
	if( tlist == undefined ){
		return s ;
	}
    return tlist[languageIndex];
}


function translate_html(){
	// Translates bottom level html DOM elements
	// Must be run by page to be translated when DOM
	// elements are loaded.
	let all = document.getElementsByTagName("*");
	for (let i=0, max=all.length; i < max; i++) {
		let d = all[i] ;
		let localName = d.localName ;
		if( ["html", "meta", "body", "script", "head", "table", "tbody", "thead", "tr"].includes(localName)){
			continue ;
		}
		let innerHTML = d.innerHTML ;
		if( innerHTML == undefined ||  innerHTML.includes("<")){
			continue ;
		}
        let text = d.innerText ;
		d.innerText = tlt(text) ;
	}
}



