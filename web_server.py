"""Web adapter for LIGHTDARK.py. Run: python web_server.py"""
from __future__ import annotations
import os
import re
import sqlite3
import sys
import types
from datetime import datetime, timedelta, date
from pathlib import Path
from threading import Lock
from contextlib import contextmanager

import truststore
truststore.inject_into_ssl()

import requests
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import LIGHTDARK as core

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('F1VE_DATA_DIR', str(ROOT))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
core.DATABASE = DATA / 'uniride_curse_locale.db'
# Reuse the account and traffic service included in LIGHTDARK, without Tkinter mainloop.
class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


services = types.ModuleType('lightdark_web_services')
services.__file__ = str(DATA / 'lightdark_services.py')
sys.modules[services.__name__] = services
services.ClosingConnection = ClosingConnection
service_source = core._TRAFFIC_SERVER_SOURCE.replace('sqlite3.connect(DB, timeout=10)', 'sqlite3.connect(DB, timeout=10, factory=ClosingConnection)')
exec(compile(service_source, 'LIGHTDARK.py:services', 'exec'), services.__dict__)
app = services.app
app.title = 'F1VE DR1VE · LIGHTDARK Web'
user_required = services.current_user
route_lock = Lock()


@contextmanager
def database():
    db = core.deschide_baza()
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


with database() as db:
    db.executescript('''
    CREATE TABLE IF NOT EXISTS web_route_owners(route_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS web_ride_owners(ride_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS orar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, utilizator TEXT NOT NULL, zi INTEGER NOT NULL,
        inceput TEXT NOT NULL, sfarsit TEXT NOT NULL, materie TEXT NOT NULL, tip TEXT NOT NULL, sala TEXT NOT NULL
    );
    ''')


@app.middleware('http')
async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        from urllib.parse import urlsplit
        if urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Origine nepermisă.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.url.path.startswith(('/api', '/v1')):
        response.headers['Cache-Control'] = 'no-store'
    return response


class RouteInput(BaseModel):
    origin: str = Field(min_length=2, max_length=300)
    destination: str = Field(min_length=2, max_length=300)
    time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')


def coordinates(value):
    match = re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*', value)
    if match:
        lat, lon = map(float, match.groups())
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Coordonate invalide.')
        return lon, lat
    return core.coordonate(value)


@app.get('/api/status')
def status():
    return {'ok': True, 'engine': 'LIGHTDARK.py', 'mode': 'local-server'}


@app.post('/api/routes')
def calculate(data: RouteInput, user: dict = Depends(user_required)):
    try:
        # Serialize requests to the public geocoder (desktop cache is reused).
        import time
        with route_lock:
            start = coordinates(data.origin.strip())
            time.sleep(1.05)
            end = coordinates(data.destination.strip())
            routes = core.calculeaza_rute(start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, 'Serviciul de hărți nu răspunde. Încearcă din nou.') from exc
    options = []
    for index, route in enumerate(routes[:3]):
        coords = route['geometry']['coordinates']
        points = [[p[1], p[0]] for p in coords]
        sample = points[::max(1, len(points) // 250)]
        if sample[-1] != points[-1]:
            sample.append(points[-1])
        traffic = services.route_traffic(services.RouteQuery(points=sample), services.API_KEY)
        minutes = max(1, round(route['duration'] / 60))
        departure = datetime.combine(date.today(), datetime.strptime(data.time, '%H:%M').time())
        options.append({'index': index, 'distance': round(route['distance'] / 1000, 1), 'duration': minutes,
                        'arrival': (departure + timedelta(minutes=minutes)).strftime('%H:%M'),
                        'traffic': traffic['status'], 'coverage': traffic['coverage'], 'geometry': coords,
                        'steps': [{'name': step.get('name') or 'Drum fără nume',
                                   'distance': round(step['distance']),
                                   'type': step['maneuver']['type'],
                                   'modifier': step['maneuver'].get('modifier', '')}
                                  for leg in route['legs'] for step in leg['steps']]})
    first = options[0]
    with database() as db:
        row = db.execute('''INSERT INTO istoric_trasee
            (origine,destinatie,plecare,distanta_km,durata_min,sosire_normala,sosire_prudenta,creat_la)
            VALUES(?,?,?,?,?,?,?,?)''', (data.origin, data.destination, data.time, first['distance'],
            first['duration'], first['arrival'], first['arrival'], datetime.now().isoformat()))
        route_id = row.lastrowid
        db.execute('INSERT INTO web_route_owners VALUES(?,?)', (route_id, user['id']))
    return {'id': route_id, 'from': data.origin, 'to': data.destination, 'time': data.time,
            'date': date.today().isoformat(), 'options': options}


@app.get('/api/routes')
def history(user: dict = Depends(user_required)):
    with database() as db:
        rows = db.execute('''SELECT r.* FROM istoric_trasee r JOIN web_route_owners o ON r.id=o.route_id
            WHERE o.user_id=? ORDER BY r.id DESC LIMIT 100''', (user['id'],)).fetchall()
    return [{'id': r['id'], 'from': r['origine'], 'to': r['destinatie'], 'time': r['plecare'],
             'date': r['creat_la'][:10], 'distance': r['distanta_km'], 'duration': r['durata_min']} for r in rows]


@app.delete('/api/routes/{route_id}')
def delete_route(route_id: int, user: dict = Depends(user_required)):
    with database() as db:
        if not db.execute('SELECT 1 FROM web_route_owners WHERE route_id=? AND user_id=?', (route_id, user['id'])).fetchone():
            raise HTTPException(404, 'Traseul nu există.')
        db.execute('DELETE FROM web_route_owners WHERE route_id=?', (route_id,))
        db.execute('DELETE FROM istoric_trasee WHERE id=?', (route_id,))
    return {'ok': True}


class RideInput(BaseModel):
    origin: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    date: date
    time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    seats: int = Field(ge=1, le=8)


@app.get('/api/rides')
def rides(user: dict = Depends(user_required)):
    with database() as db:
        rows = db.execute('''SELECT c.*, o.user_id FROM curse c JOIN web_ride_owners o ON c.id=o.ride_id
            WHERE c.zi>=? ORDER BY c.zi,c.ora''', (date.today().isoformat(),)).fetchall()
        booked = {r['cursa_id'] for r in db.execute("SELECT cursa_id FROM rezervari WHERE pasager=? AND status='activa'", (str(user['id']),))}
    return [{'id': r['id'], 'from': r['zona_plecare'], 'to': r['zona_sosire'], 'date': r['zi'],
             'time': r['ora'], 'driver': r['pseudonim'], 'seats': r['locuri'],
             'mine': r['user_id'] == user['id'], 'booked': r['id'] in booked} for r in rows]


@app.post('/api/rides', status_code=201)
def publish(data: RideInput, user: dict = Depends(user_required)):
    if data.date < date.today():
        raise HTTPException(422, 'Data cursei este în trecut.')
    with database() as db:
        row = db.execute('''INSERT INTO curse(pseudonim,facultate,zona_plecare,zona_sosire,zi,ora,rol,locuri,mesaj,creat_la)
            VALUES(?,?,?,?,?,?,?,?,?,?)''', (user['nume'], user['facultate'], data.origin, data.destination,
            data.date.isoformat(), data.time, 'Șofer', data.seats, '', datetime.now().isoformat()))
        db.execute('INSERT INTO web_ride_owners VALUES(?,?)', (row.lastrowid, user['id']))
    return {'ok': True}


@app.delete('/api/rides/{ride_id}')
def delete_ride(ride_id: int, user: dict = Depends(user_required)):
    with database() as db:
        if not db.execute('SELECT 1 FROM web_ride_owners WHERE ride_id=? AND user_id=?', (ride_id, user['id'])).fetchone():
            raise HTTPException(404, 'Cursa nu există sau nu îți aparține.')
        db.execute('DELETE FROM rezervari WHERE cursa_id=?', (ride_id,))
        db.execute('DELETE FROM web_ride_owners WHERE ride_id=?', (ride_id,))
        db.execute('DELETE FROM curse WHERE id=?', (ride_id,))
    return {'ok': True}


@app.post('/api/rides/{ride_id}/reservation')
def reserve(ride_id: int, user: dict = Depends(user_required)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        ride = db.execute('SELECT c.*,o.user_id FROM curse c JOIN web_ride_owners o ON c.id=o.ride_id WHERE c.id=?', (ride_id,)).fetchone()
        if not ride:
            raise HTTPException(404, 'Cursa nu există.')
        if ride['user_id'] == user['id']:
            raise HTTPException(409, 'Nu poți rezerva propria cursă.')
        if ride['zi'] < date.today().isoformat() or ride['locuri'] < 1:
            raise HTTPException(409, 'Cursa nu mai are locuri disponibile.')
        existing = db.execute('SELECT * FROM rezervari WHERE cursa_id=? AND pasager=?', (ride_id, str(user['id']))).fetchone()
        if existing and existing['status'] == 'activa':
            raise HTTPException(409, 'Ai deja o rezervare.')
        db.execute('''INSERT INTO rezervari(cursa_id,pasager,locuri,status,creat_la) VALUES(?,?,1,'activa',?)
            ON CONFLICT(cursa_id,pasager) DO UPDATE SET status='activa',creat_la=excluded.creat_la''', (ride_id, str(user['id']), datetime.now().isoformat()))
        db.execute('UPDATE curse SET locuri=locuri-1 WHERE id=?', (ride_id,))
    return {'ok': True}


@app.delete('/api/rides/{ride_id}/reservation')
def cancel(ride_id: int, user: dict = Depends(user_required)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        cursor = db.execute("UPDATE rezervari SET status='anulata' WHERE cursa_id=? AND pasager=? AND status='activa'", (ride_id, str(user['id'])))
        if cursor.rowcount:
            db.execute('UPDATE curse SET locuri=locuri+1 WHERE id=?', (ride_id,))
    return {'ok': True}


DAYS = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']
class ClassInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=200)
    day: str
    time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')


@app.get('/api/schedule')
def schedule(user: dict = Depends(user_required)):
    with database() as db:
        rows = db.execute('SELECT * FROM orar WHERE utilizator=? ORDER BY zi,inceput', (str(user['id']),)).fetchall()
    return [{'id': r['id'], 'title': r['materie'], 'location': r['sala'], 'day': DAYS[r['zi']], 'time': r['inceput']} for r in rows]


@app.post('/api/schedule', status_code=201)
def add_class(data: ClassInput, user: dict = Depends(user_required)):
    if data.day not in DAYS:
        raise HTTPException(422, 'Zi invalidă.')
    with database() as db:
        db.execute('INSERT INTO orar(utilizator,zi,inceput,sfarsit,materie,tip,sala) VALUES(?,?,?,?,?,?,?)',
                   (str(user['id']), DAYS.index(data.day), data.time, data.time, data.title, 'Curs', data.location))
    return {'ok': True}


@app.delete('/api/schedule/{class_id}')
def delete_class(class_id: int, user: dict = Depends(user_required)):
    with database() as db:
        db.execute('DELETE FROM orar WHERE id=? AND utilizator=?', (class_id, str(user['id'])))
    return {'ok': True}


if (ROOT / 'dist' / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=ROOT / 'dist' / 'assets'), name='assets')


@app.get('/')
def index():
    if not (ROOT / 'dist' / 'index.html').is_file():
        raise HTTPException(503, 'Construiește interfața: npm run build')
    return FileResponse(ROOT / 'dist' / 'index.html')


if __name__ == '__main__':
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description='F1VE DR1VE web server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    print(f'F1VE DR1VE · LIGHTDARK.py: http://{args.host}:{args.port}')
    uvicorn.run(app, host=args.host, port=args.port)

