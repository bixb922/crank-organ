// Copyright (c) 2023-2025 Hermann von Borries
// MIT License

// Define columns of translationDict
// keys are language codes of browser
let languageDict = { "es": null, "en": 0, "de": 1 };

// Translation keys must be in lower case
let translationDict = {
"[melodías]": // index.html 
	["[tunes]", "[Melodien]"],
"[mseg]": // diag.html 
	["[msec]", "[msec]"],
"¿cuál es tu nombre?": // tunelist.html (mcserver)
    ["What is your name?", "Dein Name, bitte?"],
" a ": // note.html
	[" to ", " bis "],
"aceptar": // common.js
	["OK","Ok"],
"activa": // diag.html 
	["Active", "Active"],
"actuación": // tunelist.html 
	["Performance", "Setlist"],
"actualizando setlist": // tunelist.html 
	["updating setlist", "Setlist wird aktualisiert"],
"actualizar archivos":
    ["Update files", "Dateien aktualisieren"],
"afinación": // note.html notelist.html 
	["Tuning", "Frequenz"],
"afinación (cents)":
	["Tuning (cents)", "Frequenzabweichung (cents)"],
"afinador": // index.html 
	["Tuner", "Stimmgerät"],
"afinados": // notelist.html
	["in tune", "gestimmt"],
"afinar": // note.html 
	["Tune", "Stimmen"],
"afinar nota": // note.html 
	["Tune note", "Note stimmen"],
"afinar notas": // notelist.html 
	["Tuning", "Stimmen"],
"afinar a": // notelist.html
	["Tune to", "Stimmen auf"],
"afinar todos": // notelist.html 
	["Tune all", "Alle Noten stimmen"],
"agregar a setlist": // common.js
	["Append to setlist", "An Setliste anhängen"],
"ajuste velocidad:": // play.html 
	["Set playback speed:", "Rückgabegeschwindingkeit:"],
"alcanza para": // index.html 
	["Enough for", "Reicht für"],
"al día.": // tunelibedit.html 
	["Up to date.", "Aktualisiert."],
"alguien conectado": // diag.html 
	["Someone connected", "Jemand angeschlossen"],
"amplitud (db)": // note.html notelist.html 
	["Amplitude (dB)", "Amplitude (dB)"],
	"amplitud": // note.html notelist.html 
	["Amplitude", "Amplitude"],
"archivos midi": // diag.html 
	["MIDI files", "MIDI-dateien"],
"autoplay": // common.js
	["Autoplay", "Autoplay"],
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
"(borrado)": // history.html
	["(deleted)", "(gelöscht)"],
"🔍búsqueda": // tunelist.html 
	["🔍Search", "🔍Suche"],
"cambios almacenados, actualización pendiente": // common.html
	["Changes stored, update pending", "Änderungen zum Update gespeichert"],
"cambios a la espera que la música termine": // common.js
	["Changes waiting for tune to stop","Änderungen warten auf das Melodieende"],
"cambiar titulos de setlists...": // common.js
	["Change setlist titles...", "Setlist Titel ändern..."],
"cancelar": // common.js
	["Cancel", "Abbrechen"],
"cancelado": // play.js
	["cancelled", "abgebrochen"],
"calibrar indicación batería": // index.html 
	["Calibrate battery indicators", "Batterieanzeige eichen"],
"cargar setlist": // common.js
	["Load setlist", "Setlist laden"],
"cargar setlist actual desde:": // common.js
    ["Load current setlist from:", "Aktuelle Setlist von hier laden:"],
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
"configuración actuadores": // diag.html 
	["Actuator configuration", "Aktuatorkonfiguration"],
"configuración wifi": // diag.html 
	["WIFI configuration", "WIFI-Konfiguration"],
"contadores batería en cero": // index.html 
	["Battery counters set to zero", "Batteriezähler auf Null"],
"control tempo": // play.html 
	["Tempo control", "Temposteuerung"],
"da capo": // play.html
	["Da capo", "Da capo"],
"desafinados": // notelist.html
	["not in tune", "verstimmt"],
"descripción": // diag.html 
	["Description", "Beschreibung"],
"en espera": // play.html
	["waiting","wartet"],
"tocar música deshabilitado por afinador, pinout": // tunelist.html play.html 
	["Playback disabled by tuner or pinout test. Reboot to reset.", "Stimmgerät oder Pinout test aktiv, keine Musikwiedergabe. Reboot zum zurücksetzen."],
"desordenar setlist": // play.html 
	["Shuffle setlist", "Setlist mischen"],
"desordenar todos": // play.html 
	["Shuffle all tunes", "Alle Melodien mischen"],
"desordenar ⭐⭐⭐": // play.html
	["Shuffle ⭐⭐⭐", " ⭐⭐⭐ mischen"],
"duración": // play.html 
	["Duration", "Länge"],
"días": // history.html 
	["days,", "Tage,"],
"editar tunelib": // index.html 
	["Edit tunelib", "Tunelib bearbeiten"],
"errores)": // diag.html 
	["errors)", "Fehler)"],
"escala de prueba": // notelist.html 
	["Play scale", "Notenskala"],
"fecha": // tunelist.html history.html 
	["Date", "Datum"],
"fecha/hora": // diag.html 
	["Date/Time", "Datum/Zeit"],
"fecha/hora compilación": // diag.html 
	["Compilation date/time", "Kompilationsdatum"],
"flash libre": // diag.html 
	["Free flash", "Flash frei"],
"flash usada": // diag.html 
	["Used flash", "flash belegt"],
"formato de tabla para copiar": // tunelibedit.html
	["Table format for copy", "Tabellenformat zum kopieren"],
"frecuencia": // diag.html 
	["Frequency", "Frequenz"],
"frecuencia media": // diag.html
	["average frequency", "Durchschnittsfrequenz"],
"girando": // play.html 
	["Turning", "Dreht"],
"gráfico manivela": // diag.html
	["Crank RPS graph", "Drehgeschwindigkeitsdiagramm"],
"guardando setlist": // common.js
	["Saving setlist","Setlist wird gespeichert"],
"guardar": // tunelibedit.html, lyrics
	["Save", "Speichern"],
"guardar setlist": // common.js
	["Save setlist", "Setlist speichern"],
"guardar setlist actual en:": // common.js
	["Save current setlist here:", "Aktuelle Setlist hier speichern:"],
"género": // tunelist.html play.html 
	["Genre", "Genre"],
"hist": // tunelist.html 
	["Hist", "Wiedergaben"],
"historia": // index.html play.html history.html 
	["History", "Chronik"],
"historia truncada": // history.html
    ["History purged", "Chronik gekürzt"],
"hz": // notelist.html
	["Hz", "Hz"],	
"hz,": // notelist.html
	["Hz,", "Hz,"],
"imagen micropython": // diag.html 
	["MicroPython image", "MicroPython image"],
"índice": // index.html
	["Home page","Homepage"],
"info": // tunelist.html play.html 
	["Info", "Info"],
"ingrese": // common.js
	["Enter", "Hier eingeben:"],
"ingresa nivel carga actual de la batería, 100=lleno, 0=vacío (usado para estimar descarga), reset=borrar calibración": // index.html
	["Enter current charge level of battery, 100=full, 0=empty, reset=delete calibration data. This is used to show battery level", "Gib den aktuellen Stand der Batterie an, 100=voll, 0=leer, reset=Eichungsdatei löschen (diese Information dient zur Eichung des Ladezustands der Batterie)"],
"ip de clientes activos": // diag.html 
	["IP of active clients", "IP aktiver Kunden"],
"letra": // play.html 
	["Lyrics", "Liedtext"],
"lista de melodías": // tunelist.html 
	["Tune list", "Melodieliste"],
"los cambios se guardan automáticamente cada par de segundos.": // tunelibedit.html
	["Changes are automatically saved every few seconds.", "Änderungen werden alle paar Sekunden automatisch gespeichert."],
"manivela": // diag.html
	["Crank", "Kurbel"],
"manivela instalada": // diag.html
    ["Crank sensor active", "Kurbelsensor aktiv"],
"melodía": // history.html 
	["Tune", "Melodie"],
"melodía actual": // play.html 
	["Current tune", "Jetzige Melodie"],
"melodías tocadas": // index.html 
	["Tunes played", "Gespielte Melodien"],
"mm:ss": // diag.html meaning minutes:seconds
	["mm:ss", "mm:ss"],
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
	["not connected", "nicht angeschlossen"],
"no gira": // play.html 
	["Not turning", "Dreht nicht"],
"no hay melodía en curso": // play.html
	["No tune in progress", "Es läuft keine Melodie"],
"no probados": // notelist.html
	["untested", "nicht getestet"],
"nombre archivo": // tunelibedit.html
	["Filename", "Dateiname"],
"partida automática activada": // common.js
	["Autoplay enabled", "Automatisches abspielen aktiviert"],
"partir": // play.html 
	["Start", "Start"],
"password:": // common.js
	["Password:", "Passwort:"],
"pedido": // history.html 
	["Request", "Wunsch"],
"pedido por": // play.html
	["Requested by", "Gewünscht von"],
"poner contadores en cero": // index.html 
	["Set battery counters to zero", "Setze Batteriezähler auf Null"],
"programa y nota": // note.html notelist.html 
	["Program and note", "Programm und Note"],
"próximo": // play.html 
	["Next", "Nächster"],
"próxima nota": // note.html
    ["Next note", "Nächste Note"],
"prueba pins": // notelist.html
	["Test all pins", "Alle Pins testen"],
"puesto en cero": // index.html 
	["Set to zero", "Auf Null gesetzt"],
"puntaje": // common.js
	["Rating", "Bewertung"],
"ram libre": // diag.html 
	["Free RAM", "RAM frei"],
"ram usada": // diag.html 
	["Used RAM", "RAM belegt"],
"remanente": // index.html 
	["Remaining", "Verbleibend"],
"registros": // play.html 
	["Registers", "Register"],
"repetición": // note.html 
	["Repetition test", "Wiederholungstest"],
"repetición largo nota/silencio [msec]": // note.html
	["Repetition note length/silence [msec]", "Wiederholung Notenlänge/Pause [msec]"],
"rev/seg": // play.html 
	["rev/sec", "Umdrehungen/Sekunde"],
"se conecta a ssid": // diag.html 
	["Connects to SSID", "SSID"],
"setlist": // play.html 
	["Setlist", "Setlist"],
"setlist guardada": // common.js
    ["Setlist saved", "Setlist gespeichert"],
"si historia más antigua que": // history.html 
	["When older than", "Wenn älter als"],
"(sin título)": // common.js/SetlistMenu
	["(no title)", "(kein Titel)"],
"sistema": // index.html diag.html 
	["System", "System"],
"sonar nota": // note.html 
	["Note test", "Notentest"],
"stop":
	["Stop", "Halt"],
"tamaño": // common.js
	["Size", "Größe"],
"tempo sigue manivela": // play.html 
	["Tempo follows crank speed", "Drehgeschwindingkeit beeinflusst Tempo"],
"terminó": // play.html
	["ended", "geendet"],
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
"título": // tunelist.html play.html 
	["Title", "Titel"],
"ver log": // diag.html 
	["Show log", "Log anzeigen"],
"versión micropython": // diag.html 
	["MicroPython version", "MicroPython version"],
"zona horaria": // diag.html
	["Time zone", "Zeitzone"],
// Server translations
"bienvenido al organillo en internet": // server index.html
	["Welcome to the crank organ on the internet", "Willkommen zur Drehorgel im Internet"],
"aquí está la historia, en fotos, de la construcción del organillo": // server index.html	
	["Here is the construction log with photos", "Hier ist die Baugeschichte, mit Bildern"],
"aquí están todas las melodías que hoy tiene el organillo. puedes pedir que se toque una melodía pulsando el título de la canción.":
	["Here is the list of all tunes in the crank organ. You can tap a melody to request it to be played", "Hier ist die Melodieliste die in der Drehorgel gespeichert ist. Drück auf einen Titel damit die Melodie gespielt wird!"],
"cómo funciona": // server index.html
	["How does it work?", "Wie funktioniert es?"],
"aquí se explica cómo funcion el organillo":
	["Here is an explanation on how this crank-organ works", "Hier ist eine Beschreibung wie die Drehorgel funktioniert"],
"demostración del software":
	["Demo of the crank organ software","Drehorgelsoftware Demo"],
"el organillo en internet": // admin.html
	["The crank organ on internet", "Die Drehorgel im Internet"],
"espectadores":  // admin.html
	["Spectators","Zuhörer"], 
"esta es una demostración del software del organillo. así se ve la interfaz de usuario del microcontrolador dentro del organillo, con sus opciones de manejo de la música y configuración. vea detalles de esta solución de código libre":
    ["Here is a demo of the crank organ software. You can see all the options, navigate the pages and test how it works. You cannot alter the configuration. Link to the open source/free software ",
	"Hier ist eine Demo des Drehorgelsoftwares. Alle Webseiten des Softwares können angesehen werden und der Betrieb wird simuliert. Die Konfiguration kann allerdings nicht geändert werden. Link zum open source/freiem software "],
"aquí": 
	["here", "hier"],
"fecha expiración (local)":  // admin.html
	["Expiration date (local time)", "Verfallsdatum"],
"fecha software (local)": // admin.hml
	["Software update date","Softwareaktualisierung Datom "],
"fecha tunelib.json (local)":  // admin.html
	["tunelib.json date", "tunelib.json Datum"],
"fotos": // server index.html
	["Photos", "Fotos"],
"imprimir": // admin.html
	["Print","Ausdrucken"],
"logout": // admin.html
	["Logout", "Logout"],
"melodías": // server index.html
	["Tunes","Melodien"],
"nombre":  // admin.html
	["Name", "Namen"], // server index.html
"máximo tiempo para gc": // diag.html
	["Maximum gc time","Höchste gc Zeit"],
"melodía actual":  // server index.html
	["Current tune", "Gegenwärtige Melodie"],
"muestra la melodía que se esta tocando ahora ¡y tiene la letra para poder acompañar cantando!": // server index.html
	["Shows the melody now playing and the lyrics to sing along!", "Zeigt die Melodie an die gerade gespielt wird, mit Liedtext zum mitsingen!"],
"obtener link performance": // admin.html
	["Get performance link", "Link zur Vorführung erstellen"],
"pedidos": // admin.html
	["Requests","Wunsch"],
"remanente (hh:mm:ss)": // admin.html
	["Time remaining (hh:mm:ss)","Verbleibende Zeit (Stunden:Minuten:Sekunden)"],
"último refresco":  // admin.html
	["Last refresh","Letzte Aktualisierung"],
"vigente": // admin.html
	[ "Current", "Gültig" ],
}

let language = navigator.language.substring(0,2) ;
let languageIndex = languageDict[language] ;
console.info("language=", language, "languageIndex=", languageIndex);


