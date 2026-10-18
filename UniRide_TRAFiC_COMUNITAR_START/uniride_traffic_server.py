"""UniRide collaborative traffic MVP. pip install fastapi uvicorn
Run: uvicorn uniride_traffic_server:app --host 0.0.0.0 --port 8765
No precise positions are persisted: observations are bucketed into ~100m cells.
HTTPS, accounts, rate limiting, authentication and a privacy review are REQUIRED before public deployment.
"""
from __future__ import annotations
import math, os, sqlite3, time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

DB = Path(__file__).with_name('uniride_traffic.db')
API_KEY = os.environ.get('UNIRIDE_TRAFFIC_KEY', 'local-test-only')
WINDOW = 600
MIN_USERS = 3
app = FastAPI(title='UniRide Traffic MVP', version='0.1')

def connection():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS samples (
      cell TEXT NOT NULL, participant TEXT NOT NULL, speed REAL NOT NULL,
      recorded INTEGER NOT NULL, PRIMARY KEY(cell,participant))''')
    return db

def cell(lat, lon):
    # Latitude-adjusted ~100m grid; NOT road map matching.
    return f'{round(lat*1000)}:{round(lon*1000*max(0.2,math.cos(math.radians(lat))))}'

class Sample(BaseModel):
    participant: str = Field(min_length=16, max_length=128)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0, le=180)
    accuracy_m: float = Field(ge=0, le=10000)
    consent: bool = False

def authorized(key):
    if key != API_KEY:
        raise HTTPException(401, 'Cheie API invalidă')

@app.post('/v1/observation')
def observation(sample: Sample, x_api_key: str | None = Header(default=None)):
    authorized(x_api_key)
    if not sample.consent:
        raise HTTPException(403, 'Consimțământul explicit este necesar')
    if sample.accuracy_m > 35:
        return {'accepted': False, 'reason': 'accuracy_insufficient'}
    # Basic walking / stationary filter. Traffic estimation needs actual vehicle telemetry.
    if sample.speed_kmh < 3:
        return {'accepted': False, 'reason': 'stationary_or_unknown_mode'}
    now = int(time.time())
    with connection() as db:
        db.execute('DELETE FROM samples WHERE recorded < ?', (now-WINDOW,))
        db.execute('INSERT INTO samples VALUES(?,?,?,?) ON CONFLICT(cell,participant) DO UPDATE SET speed=excluded.speed,recorded=excluded.recorded',
                   (cell(sample.lat,sample.lon),sample.participant,sample.speed_kmh,now))
    return {'accepted': True}

class RouteQuery(BaseModel):
    points: list[list[float]] = Field(min_length=2, max_length=3000)
    baseline_kmh: float = Field(default=40, ge=5, le=130)

def classification(ratio):
    if ratio >= .75: return 'Liber'
    if ratio >= .4: return 'Moderat'
    return 'Aglomerat'

@app.post('/v1/route-traffic')
def route_traffic(route: RouteQuery, x_api_key: str | None = Header(default=None)):
    authorized(x_api_key)
    cells = []
    for p in route.points:
        if len(p) != 2 or not (-90<=p[0]<=90 and -180<=p[1]<=180):
            raise HTTPException(422, 'Coordonate invalide')
        c = cell(*p)
        if c not in cells: cells.append(c)
    now = int(time.time())
    segments = []
    with connection() as db:
        db.execute('DELETE FROM samples WHERE recorded < ?', (now-WINDOW,))
        for c in cells:
            rows = db.execute('SELECT speed FROM samples WHERE cell=? AND recorded>=?', (c,now-WINDOW)).fetchall()
            n = len(rows)
            if n < MIN_USERS:
                segments.append({'cell':c,'status':'Date insuficiente','participants':n})
            else:
                speed = sum(r[0] for r in rows)/n
                segments.append({'cell':c,'status':classification(speed/route.baseline_kmh),
                                 'participants':n,'speed_kmh':round(speed,1)})
    valid = [s for s in segments if s['status'] != 'Date insuficiente']
    # Do not infer congestion for an entire route from a tiny sampled fraction.
    coverage = len(valid)/max(1,len(segments))
    if coverage < .5:
        status = 'Date insuficiente'
    else:
        scores = {'Liber':0,'Moderat':1,'Aglomerat':2}
        score = sum(scores[s['status']] for s in valid)/len(valid)
        status = ('Liber' if score < .5 else 'Moderat' if score < 1.5 else 'Aglomerat')
    return {'status':status,'coverage':round(coverage,2),'segments':segments,
            'method':'crowdsourced grid estimate; not road-matched; no live traffic guarantee'}

@app.get('/health')
def health(): return {'ok':True,'minimum_participants':MIN_USERS}
