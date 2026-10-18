UNIRIDE - PROTOTIP TRAFIC COLABORATIV
====================================
Fisiere:
- UniRide_TRAFiC_COMUNITAR.py: aplicatia Tkinter existenta, cu interogare trafic comunitar.
- uniride_traffic_server.py: server FastAPI care primeste observatii si calculeaza niveluri de trafic.

1) Instaleaza dependentele in terminalul VS Code:
   python -m pip install fastapi uvicorn requests tkintermapview

2) Porneste serverul in PRIMUL terminal (Windows PowerShell):
   $env:UNIRIDE_TRAFFIC_KEY="test-local-123"
   python -m uvicorn uniride_traffic_server:app --host 127.0.0.1 --port 8765

3) Porneste aplicatia in AL DOILEA terminal:
   $env:UNIRIDE_TRAFFIC_KEY="test-local-123"
   $env:UNIRIDE_TRAFFIC_URL="http://127.0.0.1:8765"
   python -u UniRide_TRAFiC_COMUNITAR.py

4) Test API: deschide http://127.0.0.1:8765/docs pentru interfata de testare.
   POST /v1/observation necesita header X-API-Key si campurile:
   {"participant":"identificator-test-123456", "lat":47.15,"lon":27.58,
    "speed_kmh":25,"accuracy_m":10,"consent":true}
   Trebuie 3 identificatori distincti in ACEEASI zona de ~100m in ultimele 10 minute.
   Nu trimite locatii reale ale altor persoane fara consimtamantul lor.

LIMITARI IMPORTANTE:
- Serverul de test NU trebuie expus pe internet. Nu are conturi, TLS, rate-limiting,
  autentificare individuala, protectie anti-frauda sau audit de confidentialitate.
- Cheia comuna este doar pentru test local, NU autentifica fiecare persoana.
- Serverul nu poate distinge soferi de pietoni si nu face map matching pe drumuri.
- Datele sunt agregate in celule geografice, nu pe segmente reale de sosea.
- Datele insuficiente NU sunt etichetate artificial ca trafic liber.
- Estimarile de durata din UI folosesc in continuare un scenariu DEMO, separat de
  indicatorul comunitar de trafic. Nu exista inca ETA corectat de trafic real.
- Aplicatia Tkinter NU transmite automat locatia. Necesita client Android cu
  consimtamant, actualizare in fundal, TLS si autentificare pentru lansare publica.
- Serviciile publice Nominatim/OSRM nu sunt potrivite pentru utilizare masiva.
