import asyncio
import os
import json
import threading
import requests
import edge_tts
import speech_recognition as sr
import io
import wave
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
GEHEUGEN_PAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_langetermijngeheugen.json")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "https://ollama.com/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b-cloud")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")

def haal_alle_herinneringen_op(gegevens):
    """Lees herinneringen op en voorkom dubbele vermeldingen."""
    alle_herinneringen = []
    geziene_sleutels = set()
    for categorie in ("feiten", "voorkeuren", "doelen", "projecten", "herinneringen"):
        items = gegevens.get(categorie, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    sleutel = " ".join(item.casefold().strip().rstrip(".!?").split())
                    if sleutel and sleutel not in geziene_sleutels:
                        geziene_sleutels.add(sleutel)
                        alle_herinneringen.append(item)
    return alle_herinneringen


def sla_herinnering_op(herinnering):
    """Bewaar een herinnering in een passende categorie."""
    pad = GEHEUGEN_PAD
    try:
        with open(pad, "r", encoding="utf-8") as bestand:
            gegevens = json.load(bestand)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        gegevens = {}

    if not isinstance(gegevens, dict):
        gegevens = {}

    for categorie in ("feiten", "voorkeuren", "doelen", "projecten", "herinneringen"):
        if not isinstance(gegevens.get(categorie), list):
            gegevens[categorie] = []

    tekst = herinnering.lower()
    if any(woord in tekst for woord in ("favoriete", "favoriet", "houd van", "liever", "voorkeur")):
        categorie = "voorkeuren"
    elif any(woord in tekst for woord in ("mijn doel", "ik wil", "ik hoop", "ik wil bereiken")):
        categorie = "doelen"
    elif any(woord in tekst for woord in ("project", "ik werk aan", "ik bouw aan")):
        categorie = "projecten"
    else:
        categorie = "feiten"

    sleutel = " ".join(herinnering.casefold().strip().rstrip(".!?").split())

    def bestaat_al(lijst):
        return any(isinstance(item, str) and " ".join(item.casefold().strip().rstrip(".!?").split()) == sleutel for item in lijst)

    alle_categorieen = ("feiten", "voorkeuren", "doelen", "projecten", "herinneringen")
    al_opgeslagen = any(
        bestaat_al(gegevens[naam])
        for naam in alle_categorieen
    )

    if sleutel and not al_opgeslagen:
        gegevens[categorie].append(herinnering)


    with open(pad, "w", encoding="utf-8") as bestand:
        json.dump(gegevens, bestand, ensure_ascii=False, indent=2)
        bestand.write("\n")

GEHEUGEN_BESTAND = "jarvis_geheugen.json"
try:
    with open(GEHEUGEN_BESTAND, "r", encoding="utf-8") as bestand:
        gespreksgeheugen = json.load(bestand)
    if not isinstance(gespreksgeheugen, list):
        gespreksgeheugen = []
    else:
        gespreksgeheugen = [
            bericht for bericht in gespreksgeheugen
            if isinstance(bericht, dict)
            and bericht.get("role") in ("user", "assistant")
            and isinstance(bericht.get("content"), str)
        ][-20:]
except (FileNotFoundError, json.JSONDecodeError, OSError):
    gespreksgeheugen = []
os.makedirs("static", exist_ok=True)

HTML = """
<!doctype html>
<html lang="nl">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS</title>
<style>
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  max-width: 650px;
  margin: 0 auto;
  min-height: 100vh;
  padding: 28px 20px 40px;
  color: #d9f5ff;
  background: radial-gradient(ellipse at 50% 20%, #102d49 0%, #06111f 48%, #02060d 100%);
}
h1 {
  text-align: center;
  color: #72e4ff;
  letter-spacing: 8px;
  font-size: clamp(25px, 7vw, 38px);
  text-shadow: 0 0 18px #168dff;
  margin: 8px 0;
}
p { text-align: center; color: #739dbb; letter-spacing: 2px; font-size: 12px; text-transform: uppercase; }
body::before {
  content: "SYSTEM ONLINE  •  PERSONAL AI";
  display: block;
  text-align: center;
  color: #47cfff;
  font-size: 10px;
  letter-spacing: 3px;
  margin: 8px 0 22px;
}
textarea {
  width: 100%;
  height: 100px;
  font-size: 17px;
  padding: 15px;
  border: 1px solid #17618a;
  border-radius: 12px;
  background: rgba(3, 15, 29, .92);
  color: #e7faff;
  outline: none;
  box-shadow: 0 0 18px #0066aa22, inset 0 0 15px #0066aa18;
}
textarea:focus { border-color: #55dfff; box-shadow: 0 0 18px #00aaff44; }
button {
  width: 100%;
  padding: 14px;
  margin-top: 12px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
  color: #bff5ff;
  cursor: pointer;
  border: 1px solid #1689bd;
  border-radius: 10px;
  background: linear-gradient(135deg, #0b2a43, #071523);
  box-shadow: 0 0 14px #008cff20;
}
button {
  transition: background 180ms ease, border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}
button:hover {
  border-color: #62e5ff;
  background: linear-gradient(135deg, #10466a, #0a2035);
  box-shadow: 0 0 20px #00aeff44, inset 0 0 10px #00aeff12;
}
button:active {
  background: #10466a;
  transform: scale(0.985);
  box-shadow: 0 0 24px #00aeff55;
}
#micstatus {
  text-align: center;
  color: #63d9ff;
  margin-top: 12px;
  font-size: 13px;
}
#antwoord {
  white-space: pre-wrap;
  margin-top: 20px;
  padding: 16px;
  min-height: 55px;
  border: 1px solid #164c6d;
  border-radius: 12px;
  background: rgba(3, 14, 27, .8);
  line-height: 1.6;
  box-shadow: inset 0 0 20px #0077aa12;
}
audio { filter: hue-rotate(155deg); }

#reactor {
  position: relative; width: 230px; height: 230px;
  margin: 24px auto 40px; display: flex;
  align-items: center; justify-content: center;
}
.ring {
  position: absolute; border-radius: 50%;
  border: 1px solid #36caff; pointer-events: none;
}
.ring-buiten {
  inset: 5px; border-style: dashed; opacity: .65;
  animation: reactor-draai 18s linear infinite;
}
.ring-midden {
  inset: 22px; border-width: 2px;
  border-color: #168bff #57eaff #168bff #57eaff;
  box-shadow: 0 0 18px #009dff55;
  animation: reactor-draai 8s linear infinite;
}
.ring-binnen {
  inset: 42px; border-color: #65eaff88;
  box-shadow: inset 0 0 22px #008cff22;
  animation: reactor-pulse 2.4s ease-in-out infinite;
}
.reactor-kern {
  width: 94px; height: 94px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #d8fbff; font-size: 43px; font-weight: 300;
  border: 2px solid #65eaff;
  background: radial-gradient(circle, #176d9a, #07182c 72%);
  box-shadow: 0 0 24px #00aeff88, inset 0 0 20px #00aeff55;
  animation: reactor-pulse 2.4s ease-in-out infinite;
}
.reactor-label {
  position: absolute; bottom: -13px; font-size: 10px;
  letter-spacing: 4px; color: #7fdfff;
}
#reactorstatus {
  position: absolute; bottom: -32px; font-size: 9px;
  letter-spacing: 2px; color: #4db9e8;
}
@keyframes reactor-draai { to { transform: rotate(360deg); } }

#reactor.luistert .reactor-kern {
  border-color: #65ffcf;
  box-shadow: 0 0 35px #00ffc888, inset 0 0 24px #00ffc855;
}
#reactor.luistert .ring {
  border-color: #65ffcf;
}
#reactor.denkt .reactor-kern {
  border-color: #ffcc66;
  box-shadow: 0 0 35px #ffae0088, inset 0 0 24px #ffae0055;
}
#reactor.denkt .ring {
  border-color: #ffcc66;
}
#reactor.spreekt .reactor-kern {
  border-color: #b88aff;
  box-shadow: 0 0 35px #9b5cffaa, inset 0 0 24px #9b5cff66;
}
#reactor.spreekt .ring {
  border-color: #b88aff;
}

@keyframes reactor-pulse {
  0%, 100% { transform: scale(1); opacity: .82; }
  50% { transform: scale(1.045); opacity: 1; }
}


/* JARVIS COCKPIT UPGRADE */
body {
  max-width: 920px;
  padding: clamp(18px, 4vw, 42px);
  background: radial-gradient(ellipse at 50% 25%, #103653 0%, transparent 48%), linear-gradient(rgba(30, 130, 180, .035) 1px, transparent 1px), linear-gradient(90deg, rgba(30, 130, 180, .035) 1px, transparent 1px), linear-gradient(145deg, #061626, #020711 75%);
  background-size: auto, 32px 32px, 32px 32px, auto;
}
h1 { letter-spacing: clamp(5px, 1.4vw, 10px); text-shadow: 0 0 10px #55dfff, 0 0 30px #168dff88; }
p { letter-spacing: 3px; }
#reactor { width: clamp(230px, 42vw, 300px); height: clamp(230px, 42vw, 300px); margin: 30px auto 48px; filter: drop-shadow(0 0 22px #008cff20); }
.ring-buiten { border-color: #80eaff; box-shadow: 0 0 12px #36caff22; }
.ring-midden { box-shadow: 0 0 24px #009dff66, inset 0 0 18px #009dff22; }
.ring-binnen { box-shadow: inset 0 0 28px #008cff35, 0 0 15px #65eaff22; }
.reactor-kern { box-shadow: 0 0 32px #00aeff99, inset 0 0 24px #00aeff66; }
textarea { min-height: 110px; border-radius: 15px; border-color: #287ba5; box-shadow: 0 0 24px #0066aa22, inset 0 0 20px #0066aa20; }
textarea:focus { border-color: #8af0ff; box-shadow: 0 0 24px #00bfff55, inset 0 0 16px #0066aa22; }
button { min-height: 49px; border-color: #278db9; border-radius: 13px; background: linear-gradient(135deg, #103955, #071523 75%); box-shadow: 0 0 18px #008cff22, inset 0 1px #8beaff12; }
#micstatus { padding: 4px 8px; }
#antwoord { border-color: #26708f; border-radius: 15px; background: linear-gradient(145deg, #081b2cdd, #030b15f2); box-shadow: inset 0 0 24px #0077aa18, 0 0 16px #0066aa12; }
audio { border-radius: 12px; max-width: 100%; }
@media (max-width: 480px) { body { padding: 20px 15px 32px; } #reactor { margin-top: 24px; margin-bottom: 44px; } h1 { font-size: 27px; } }

</style>
</head>
<body>
<h1>J.A.R.V.I.S.</h1>
<p>Je persoonlijke assistent</p>
<div id="reactor" class="reactor-gereed">
  <div class="ring ring-buiten"></div>
  <div class="ring ring-midden"></div>
  <div class="ring ring-binnen"></div>
  <div class="reactor-kern"><span>J</span></div>
  <div class="reactor-label">J.A.R.V.I.S.</div>
  <div id="reactorstatus">SYSTEM GEREED</div>
</div>
<div style="display:none;">
<button type="button" onclick="jarvisStatus('luistert','TEST: GROEN')">Test groen</button>
<button type="button" onclick="jarvisStatus('denkt','TEST: ORANJE')">Test oranje</button>
<button type="button" onclick="jarvisStatus('spreekt','TEST: PAARS')">Test paars</button>
<button type="button" onclick="jarvisStatus('gereed','SYSTEM GEREED')">Terug naar blauw</button>
</div>
<textarea id="vraag" placeholder="Typ je vraag aan Jarvis..."></textarea><br>
<button id="handsfreeknop" type="button" onclick="wisselHandsfree()">🎙️ Praat tegen Jarvis</button>
<div id="micstatus"></div>
<button onclick="stuur()">Stuur naar Jarvis</button>
<div id="antwoord"></div>
<button type="button" onclick="speelJarvisAf()">🔊 Speel Jarvis af</button>
<audio id="spraak" controls style="display:block;width:100%;margin-top:20px"></audio>
<script>
let jarvisAudioContext = null;
let handsfreeActief = false;

function wisselHandsfree() {
  handsfreeActief = !handsfreeActief;
  const knop = document.getElementById("handsfreeknop");
  const status = document.getElementById("micstatus");
  if (handsfreeActief) {
    knop.textContent = "⏹️ Stop handsfree";
    luister();
  } else {
    knop.textContent = "🎙️ Praat tegen Jarvis";
    status.textContent = "Handsfree uit.";
  }
}

function luisterOpnieuw() {
  if (handsfreeActief) {
    setTimeout(() => {
      if (handsfreeActief) luister();
    }, 700);
  }
}

function jarvisStatus(status, label) {
  const reactor = document.getElementById('reactor');
  const tekst = document.getElementById('reactorstatus');
  if (!reactor || !tekst) return;
  reactor.classList.remove('luistert', 'denkt', 'spreekt');
  if (status !== 'gereed') reactor.classList.add(status);
  tekst.textContent = label;
}

function speelJarvisAf() {
  const audio = document.getElementById("spraak");
  if (!audio.src) {
    document.getElementById("antwoord").textContent = "Stel eerst een vraag aan Jarvis.";
    return;
  }
  audio.play().catch(() => {
    document.getElementById("antwoord").textContent += " Tik op de afspeelknop van de audiospeler.";
  });
}

async function luister() {
  const status = document.getElementById('micstatus');
  const invoer = document.getElementById('vraag');

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    status.textContent = 'Microfoontoegang vereist een beveiligde HTTPS-verbinding.';
    return;
  }

  let stream;
  let context;
  let processor;
  let bron;
  let stil;

  try {
    status.textContent = 'Vraag om microfoontoegang en spreek daarna duidelijk.';
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!jarvisAudioContext || jarvisAudioContext.state === 'closed') {
      jarvisAudioContext = new AudioCtx();
    }
    context = jarvisAudioContext;
    await context.resume();

    bron = context.createMediaStreamSource(stream);
    processor = context.createScriptProcessor(4096, 1, 1);
    stil = context.createGain();
    stil.gain.value = 0;

    const stukken = [];
    let aantal = 0;
    const maxSamples = Math.floor(context.sampleRate * 5);

    processor.onaudioprocess = function(event) {
      if (aantal >= maxSamples) return;
      const input = event.inputBuffer.getChannelData(0);
      const lengte = Math.min(input.length, maxSamples - aantal);
      stukken.push(new Float32Array(input.slice(0, lengte)));
      aantal += lengte;

      if (aantal >= maxSamples) {
        processor.onaudioprocess = null;
        bron.disconnect();
        processor.disconnect();
        stil.disconnect();
        stream.getTracks().forEach(track => track.stop());

        const wav = maakWav(stukken, aantal, context.sampleRate);
        // Audiocontext actief houden voor de stem van Jarvis.

        const bestand = new Blob([wav], { type: 'audio/wav' });
        const data = new FormData();
        data.append('audio', bestand, 'spraak.wav');

        status.textContent = 'Je opname wordt verwerkt...';
        fetch('/spraak', { method: 'POST', body: data })
          .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
          .then(result => {
            if (!result.ok || !result.data.tekst) {
              throw new Error(result.data.fout || 'Spraakherkenning is mislukt.');
            }
            invoer.value = result.data.tekst;
            status.textContent = 'Ik heb je gehoord. Jarvis denkt na...';
            return stuur();
          })
          .catch(err => {
            status.textContent = err.message || 'Spraak verwerken is mislukt.';
          });
      }
    };

    bron.connect(processor);
    processor.connect(stil);
    stil.connect(context.destination);

    jarvisStatus('luistert', 'LUISTERT NAAR JE');
    status.textContent = '🎙️ Jarvis luistert 5 seconden. Spreek nu.';
  } catch (err) {
    if (stream) stream.getTracks().forEach(track => track.stop());
    if (context && context.state !== 'closed') context.close();
    status.textContent = 'Microfoon niet beschikbaar: ' + (err.message || err);
  }
}

function maakWav(stukken, aantal, sampleRate) {
  const buffer = new ArrayBuffer(44 + aantal * 2);
  const view = new DataView(buffer);
  function schrijfTekst(offset, tekst) {
    for (let i = 0; i < tekst.length; i++) {
      view.setUint8(offset + i, tekst.charCodeAt(i));
    }
  }

  schrijfTekst(0, 'RIFF');
  view.setUint32(4, 36 + aantal * 2, true);
  schrijfTekst(8, 'WAVE');
  schrijfTekst(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  schrijfTekst(36, 'data');
  view.setUint32(40, aantal * 2, true);

  let positie = 44;
  for (const stuk of stukken) {
    for (let i = 0; i < stuk.length; i++) {
      const sample = Math.max(-1, Math.min(1, stuk[i]));
      view.setInt16(positie, sample < 0 ? sample * 32768 : sample * 32767, true);
      positie += 2;
    }
  }
  return buffer;
}
async function stuur() {
  const tekst = document.getElementById('vraag').value.trim();
  const antwoord = document.getElementById('antwoord');
  if (!tekst) {
    antwoord.textContent = 'Typ eerst een vraag.';
    return;
  }
  jarvisStatus('denkt', 'JARVIS DENKT NA...');
  antwoord.textContent = 'Jarvis denkt na...';
  try {
    const r = await fetch('/vraag', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({vraag: tekst})
    });
    const data = await r.json();
    antwoord.textContent = data.antwoord || data.fout || 'Geen antwoord.';
    if (data.antwoord) {
      const audio = document.getElementById('spraak');
      const audioUrl = "/static/jarvis_antwoord.mp3?t=" + Date.now();
      let pogingen = 0;
      const controleerAudio = async () => {
        while (pogingen < 120) {
          pogingen++;
          try {
            const controle = await fetch(audioUrl, {method: "HEAD", cache: "no-store"});
            if (controle.ok && Number(controle.headers.get("content-length") || 0) > 0) {
              audio.src = audioUrl;
              audio.onended = () => { jarvisStatus('gereed', 'SYSTEM GEREED'); luisterOpnieuw(); };

              (async () => {
                try {
                  if (!jarvisAudioContext || jarvisAudioContext.state === 'closed') {
                    jarvisAudioContext = new (window.AudioContext || window.webkitAudioContext)();
                  }
                  const ctx = jarvisAudioContext;
                  await ctx.resume();
                  const response = await fetch(audioUrl, { cache: 'no-store' });
                  if (!response.ok) throw new Error('Stem niet beschikbaar');
                  const buffer = await response.arrayBuffer();
                  const decoded = await ctx.decodeAudioData(buffer);
                  const bronStem = ctx.createBufferSource();
                  bronStem.buffer = decoded;
                  bronStem.connect(ctx.destination);
                  bronStem.onended = () => { jarvisStatus('gereed', 'SYSTEM GEREED'); luisterOpnieuw(); };
                  bronStem.start();
                  jarvisStatus('spreekt', 'JARVIS SPREEKT');
                } catch (e) {
                  try {
                    await audio.play();
                    jarvisStatus('spreekt', 'JARVIS SPREEKT');
                  } catch (e2) {
                    antwoord.textContent += " Tik op 🔊 Speel Jarvis af als je geen geluid hoort.";
                    jarvisStatus('gereed', 'SYSTEM GEREED');
                  }
                }
              })();
              return;
            }
          } catch(e) {}
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        antwoord.textContent += " De stem is nog niet klaar. Probeer opnieuw.";
      };
      controleerAudio();
    }
  } catch(e) {
    antwoord.textContent = 'Verbinding of spraak mislukt. Probeer opnieuw.';
  }
}
</script>
</body>
</html>
"""

@app.post("/spraak")
def spraak():
    if "audio" not in request.files:
        return jsonify({"fout": "Geen audio ontvangen."}), 400

    try:
        bestand = request.files["audio"]
        recognizer = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(bestand.read())) as bron:
            audio = recognizer.record(bron)
        tekst = recognizer.recognize_google(audio, language="nl-NL")
        return jsonify({"tekst": tekst})
    except sr.UnknownValueError:
        return jsonify({"fout": "Ik heb je niet goed verstaan. Probeer opnieuw."}), 400
    except sr.RequestError as e:
        print("Spraakherkenningsfout:", e)
        return jsonify({"fout": "Spraakherkenning is tijdelijk niet bereikbaar."}), 503
    except Exception as e:
        print("Audiofout:", e)
        return jsonify({"fout": "De audio kon niet worden verwerkt."}), 400


@app.get("/")
def start():
    return render_template_string(HTML)

@app.post("/vraag")
def vraag():
    global gespreksgeheugen

    tekst = (request.json or {}).get("vraag", "").strip()
    if not tekst:
        return jsonify({"fout": "Typ eerst een vraag."}), 400

    # Toon opgeslagen langetermijnherinneringen op verzoek.
    if opdracht_is_opvragen := tekst.strip().lower() in (
        "jarvis, wat onthoud je over mij?",
        "jarvis wat onthoud je over mij?",
        "wat onthoud je over mij?",
        "jarvis, wat weet je nog over mij?",
    ):
        try:
            with open(GEHEUGEN_PAD, "r", encoding="utf-8") as bestand:
                gegevens = json.load(bestand)
            herinneringen = haal_alle_herinneringen_op(gegevens)
            if not isinstance(herinneringen, list):
                herinneringen = []
        except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
            herinneringen = []

        antwoord = (
            "Dit heb ik in mijn langetermijngeheugen opgeslagen: "
            + "; ".join(herinneringen)
            if herinneringen
            else "Er staan nog geen herinneringen in mijn langetermijngeheugen."
        )
        return jsonify({"antwoord": antwoord})

    # Verwijder alleen een specifieke herinnering op expliciet verzoek.
    opdracht_vergeten = tekst.strip()
    opdracht_vergeten_lager = opdracht_vergeten.lower()
    voorvoegsels_vergeten = (
        "jarvis, vergeet mijn herinnering over ",
        "jarvis vergeet mijn herinnering over ",
        "vergeet mijn herinnering over ",
        "jarvis, vergeet dat ",
        "jarvis vergeet dat ",
        "vergeet dat ",
    )
    for voorvoegsel_vergeten in voorvoegsels_vergeten:
        if opdracht_vergeten_lager.startswith(voorvoegsel_vergeten):
            zoekterm = opdracht_vergeten[len(voorvoegsel_vergeten):].strip()
            if not zoekterm:
                return jsonify({
                    "antwoord": "Welke herinnering wil je dat ik vergeet?"
                })

            try:
                with open(GEHEUGEN_PAD, "r", encoding="utf-8") as bestand_geheugen:
                    gegevens = json.load(bestand_geheugen)
                herinneringen = haal_alle_herinneringen_op(gegevens)
                if not isinstance(herinneringen, list):
                    herinneringen = []
            except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
                herinneringen = []

            matches = [
                herinnering for herinnering in herinneringen
                if zoekterm.lower() in herinnering.lower()
            ]

            if not matches:
                return jsonify({
                    "antwoord": "Ik heb geen opgeslagen herinnering gevonden die daarbij past. Ik heb niets verwijderd."
                })

            if len(matches) > 1:
                return jsonify({
                    "antwoord": "Er zijn meerdere herinneringen die daarbij passen. Geef een specifiekere omschrijving. Ik heb niets verwijderd."
                })

            verwijderd = matches[0]
            for categorie in ("feiten", "voorkeuren", "doelen", "projecten", "herinneringen"):
                items = gegevens.get(categorie, [])
                if isinstance(items, list):
                    gegevens[categorie] = [
                        herinnering for herinnering in items
                        if herinnering != verwijderd
                    ]
            try:
                with open(GEHEUGEN_PAD, "w", encoding="utf-8") as bestand_geheugen:
                    json.dump(gegevens, bestand_geheugen, ensure_ascii=False, indent=2)
                    bestand_geheugen.write("\n")
            except (OSError, TypeError, ValueError) as fout:
                print("Verwijderen herinnering mislukt:", fout)
                return jsonify({
                    "antwoord": "Het is niet gelukt om de herinnering te verwijderen."
                }), 500

            return jsonify({
                "antwoord": "Ik heb deze herinnering verwijderd: " + verwijderd
            })

    # Sla alleen op wanneer Timo dit expliciet vraagt.
    opdracht = tekst.strip()
    opdracht_lager = opdracht.lower()
    for voorvoegsel in (
        "jarvis, onthoud dat ",
        "jarvis onthoud dat ",
        "onthoud dat ",
    ):
        if opdracht_lager.startswith(voorvoegsel):
            herinnering = opdracht[len(voorvoegsel):].strip()
            if herinnering:
                try:
                    sla_herinnering_op(herinnering)
                    return jsonify({
                        "antwoord": "Ik heb dit opgeslagen in mijn langetermijngeheugen: " + herinnering
                    })
                except (OSError, TypeError, ValueError) as fout:
                    print("Opslaan herinnering mislukt:", fout)
                    return jsonify({
                        "antwoord": "Het is niet gelukt om die herinnering op te slaan."
                    }), 500

    try:
        systeem = {
            "role": "system",
            "content": (
                "Je bent JARVIS, de persoonlijke AI-assistent van Timo. "
                "Je bent niet van Google. Je bent slim, rustig, vriendelijk en behulpzaam. "
                "Spreek standaard Nederlands, tenzij Timo een andere taal vraagt. "
                "Antwoord duidelijk en natuurlijk, meestal in 1 tot 3 korte zinnen. "
                "Lees eerdere berichten zorgvuldig voordat je antwoordt en gebruik ze om vervolgvragen te begrijpen. "
                "Onthoud het verschil tussen wat Timo zegt, wat jij eerder hebt geantwoord en wat daadwerkelijk een feit is. "
                "Gebruik opgeslagen herinneringen om persoonlijke vragen over Timo te beantwoorden. "
                "Als een herinnering de vraag duidelijk beantwoordt, antwoord dan rechtstreeks en natuurlijk. "
                "Maak van opgeslagen informatie geen andere naam, betekenis of feit. "
                "Verzin geen gebeurtenissen, herinneringen, namen of feiten. "
                "Als je iets niet zeker weet, zeg dat eerlijk en geef geen gok alsof het waar is. "
                "Als een vraag meerdere betekenissen kan hebben, stel dan een korte verduidelijkende vraag. "
                "Beantwoord de vraag van Timo rechtstreeks en blijf bij het onderwerp. "
                "Help Timo als muziekproductie-assistent bij zijn artiestenproject MOTIWAY. "
                "Geef praktische, beginnersvriendelijke stappen voor Logic Pro, arrangementen, drops, drums, bass, leads, sound design, effecten, mixen en mastering. "
                "Houd rekening met big-room EDM en genrecombinaties, maar volg altijd de specifieke stijl waar Timo om vraagt. "
                "Geef concrete instellingen wanneer die betrouwbaar bekend zijn en leg kort uit waarom ze werken. "
                "Verzin geen BPM, toonsoorten, pluginfuncties of technische feiten; benoem onzekerheid eerlijk. "
                "Geef bij complexe taken één duidelijke volgende stap tegelijk."
            )
        }

        # Lees blijvende herinneringen in; laat het gespreksgeheugen intact.
        try:
            with open(GEHEUGEN_PAD, "r", encoding="utf-8") as bestand:
                gegevens = json.load(bestand)
            herinneringen = haal_alle_herinneringen_op(gegevens)
            if not isinstance(herinneringen, list):
                herinneringen = []
        except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
            herinneringen = []

        if herinneringen:
            systeem["content"] += (
                " Gebruik deze opgeslagen herinneringen over Timo alleen wanneer relevant: "
                + json.dumps(herinneringen, ensure_ascii=False)
                + ". Behandel ze als context, niet als bewijs dat elke bewering altijd actueel is."
            )

        berichten = [systeem] + gespreksgeheugen + [
            {"role": "user", "content": tekst}
        ]

        if not OLLAMA_API_KEY:
            raise RuntimeError("OLLAMA_API_KEY ontbreekt in de serverinstellingen.")

        r = requests.post(
            OLLAMA_API_URL,
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
            json={
                "model": OLLAMA_MODEL,
                "options": {"num_predict": 100},
                "messages": berichten,
                "stream": False
            },
            timeout=120
        )
        r.raise_for_status()
        antwoord = r.json()["message"]["content"]

        gespreksgeheugen.extend([
            {"role": "user", "content": tekst},
            {"role": "assistant", "content": antwoord}
        ])
        gespreksgeheugen = gespreksgeheugen[-20:]
        with open(GEHEUGEN_BESTAND, "w", encoding="utf-8") as bestand:
            json.dump(gespreksgeheugen, bestand, ensure_ascii=False, indent=2)

        try:
            os.remove("static/jarvis_antwoord.mp3")
        except FileNotFoundError:
            pass

        def maak_spraak_achtergrond():
            async def maak_spraak():
                gesproken_antwoord = antwoord.replace("MOTIWAY", "moti way")
                stem = edge_tts.Communicate(
                    gesproken_antwoord,
                    voice="nl-NL-MaartenNeural",
                    rate="+25%",
                    pitch="-12Hz"
                )
                )
                tijdelijk = "static/jarvis_antwoord_nieuw.mp3"
                await stem.save(tijdelijk)
                os.replace(tijdelijk, "static/jarvis_antwoord.mp3")

            try:
                asyncio.run(maak_spraak())
            except Exception as e:
                print("Jarvis-spraakfout:", e)

        threading.Thread(
            target=maak_spraak_achtergrond,
            daemon=True
        ).start()

        return jsonify({"antwoord": antwoord})

    except Exception as e:
        print("Jarvis-fout:", e)
        return jsonify({
            "fout": "Jarvis kan niet antwoorden. Controleer of Ollama werkt."
        }), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5050")))
