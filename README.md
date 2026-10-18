# F1VE DR1VE · LIGHTDARK în browser

Interfața React/HTML apelează serverul Python `web_server.py`, care importă `LIGHTDARK.py` fără a porni fereastra Tkinter. Calculatorul rulează Python; calculatorul și telefonul folosesc aceeași pagină web.

## Instalare și pornire pe Windows

Din folderul proiectului, instalează o singură dată:

```powershell
python -m pip install -r requirements-web.txt
npm install
```

Apoi deschide `start-web.cmd`. Acesta construiește interfața și pornește serverul pe portul 8000.

Pe calculator: http://localhost:8000

Pe telefon: conectează telefonul la aceeași rețea Wi-Fi și deschide `http://ADRESA-IP-A-CALCULATORULUI:8000`. Adresa IPv4 se găsește cu `ipconfig`. Permite Python în firewall pentru rețeaua privată, dacă Windows solicită. Calculatorul și serverul trebuie să rămână pornite.

În Setări creează un cont sau conectează-te cu un cont LIGHTDARK existent. Nu sunt necesare chei API introduse în browser.

Pornire manuală:

```powershell
npm run build
python web_server.py --host 0.0.0.0 --port 8000
```

Doar pe calculator, fără acces din rețea:

```powershell
python web_server.py
```

## Funcții conectate la Python

- Conturi: înregistrare, conectare, deconectare; parolele sunt procesate de serviciul inclus în LIGHTDARK, fără stocare în clar. Sesiunea web se păstrează în tabul browserului.
- Trasee: `coordonate` și `calculeaza_rute` din LIGHTDARK; variante OSRM cu distanță, durată, oră estimată a sosirii și indicații. Localizarea se cere numai la apăsarea butonului dedicat.
- Trafic: serviciul colaborativ inclus în LIGHTDARK; fără observații reale suficiente apare „Date insuficiente”. Duratele OSRM nu includ trafic live.
- Istoric: traseele create din web sunt salvate în SQLite și accesibile numai contului care le-a creat.
- Curse comune: publicare, listare, ștergerea propriei curse, rezervare și anulare. Ultimul loc este protejat prin tranzacție SQLite.
- Orar: creare, listare și ștergere, în aceeași structură de date pe utilizator folosită de aplicația desktop.
- Aspect pentru calculator și telefon, teme luminoasă/închisă și navigare externă în Google Maps.

Bazele `uniride_curse_locale.db` și `uniride_traffic.db` rămân pe calculator și sunt excluse din Git. Conturile și orarul existente sunt reutilizate. Curse și trasee vechi fără autor verificabil nu sunt atribuite automat unui cont web. Datele din vechiul localStorage nu sunt importate automat.

## Limite

Acesta este un server pentru utilizare locală sau într-o rețea privată de încredere. Nu îl expune direct pe internet: pentru publicare sunt necesare HTTPS și protecții operaționale suplimentare. Pe telefon, geolocalizarea cere HTTPS; la acces prin IP și HTTP poți introduce manual plecarea. Identitatea și vehiculele participanților nu sunt verificate.

Browserul nu execută Tkinter. Modulele desktop FlowFriends, FlowPoints, FlowShop, comenzile vocale Windows și navigarea 3D nu au fost portate în această integrare. Navigarea se deschide în Google Maps, care poate alege altă rută decât OSRM. Harta și serviciile externe necesită internet și pot fi indisponibile.

## Dezvoltare și verificare

În două terminale:

```powershell
python web_server.py
npm run dev -- --host 0.0.0.0
```

Vite redirecționează `/api` și `/v1` spre serverul Python de pe portul 8000. Pentru utilizarea normală și pentru telefon este suficient serverul Python cu interfața construită.

```powershell
npm run build
python -m unittest discover -s tests -v
```

Testele folosesc baze SQLite temporare și HTTP real, verificând conturi, accesul la date, concurența rezervărilor, anularea, rutarea și erorile serviciului extern. Rutele externe sunt simulate în teste; calculele obișnuite folosesc serviciile reale din LIGHTDARK.
