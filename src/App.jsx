import { useEffect, useRef, useState } from 'react'
import { api, send, setToken, hasToken } from './api'
import './App.css'

const navigation = [['home', '⌂', 'Acasă'], ['routes', '↗', 'Traseele mele'], ['rides', '♧', 'Curse comune'], ['schedule', '▦', 'Orarul meu'], ['settings', '⚙', 'Setări']]
function useSaved(key, initial) {
  const [value, update] = useState(() => { try { return JSON.parse(localStorage.getItem(key)) ?? initial } catch { return initial } })
  function save(next) { update(next); try { localStorage.setItem(key, JSON.stringify(next)) } catch { /* Session remains usable without storage. */ } }
  return [value, save]
}
const mapUrl = (place) => `https://maps.google.com/maps?q=${encodeURIComponent(place)}&z=13&output=embed`
const directions = (from, to) => `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(from)}&destination=${encodeURIComponent(to)}&travelmode=driving`
export default function App() {
  const [page, setPage] = useState('home')
  const [theme, setTheme] = useSaved('f1ve-theme', 'dark')
  const [name, setName] = useSaved('f1ve-name', '')
  const [history, setHistory] = useState([])
  const [rides, setRides] = useState([])
  const [classes, setClasses] = useState([])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [time, setTime] = useState('08:00')
  const [map, setMap] = useState('Iași, România')
  const [selected, setSelected] = useState(null)
  const [notice, setNotice] = useState('')
  const [modal, setModal] = useState(false)
  const [filter, setFilter] = useState('')
  const [user, setUser] = useState(null)
  const [busy, setBusy] = useState(false)
  const [online, setOnline] = useState(false)
  const [routeIndex, setRouteIndex] = useState(0)
  const dialogRef = useRef(null)
  useEffect(() => { if (modal) dialogRef.current?.showModal() }, [modal])
  useEffect(() => {
    api('/api/status').then(() => setOnline(true)).catch(() => setOnline(false))
    if (hasToken()) api('/v1/users/me').then(async account => {
      setUser(account); setName(account.nume)
      const [routes, allRides, lessons] = await Promise.all([api('/api/routes'), api('/api/rides'), api('/api/schedule')])
      setHistory(routes); setRides(allRides); setClasses(lessons)
    }).catch(error => { if (error.status === 401) setToken(''); setNotice(error.message) })
  }, [])
  async function refresh() {
    const [routes, allRides, lessons] = await Promise.all([api('/api/routes'), api('/api/rides'), api('/api/schedule')])
    setHistory(routes); setRides(allRides); setClasses(lessons)
  }
  function requireUser() {
    if (user) return true
    setPage('settings'); setNotice('Conectează-te sau creează un cont pentru a folosi funcțiile LIGHTDARK.'); return false
  }
  async function action(path, data, method = 'POST') {
    if (!requireUser()) return
    try { await send(path, data, method); await refresh(); setNotice('Modificările au fost salvate pe server.') }
    catch (error) { setNotice(error.message) }
  }
  async function plan(e) {
    e.preventDefault()
    if (!requireUser() || busy) return
    setBusy(true); setNotice('LIGHTDARK calculează variantele de traseu…')
    try {
      const route = await send('/api/routes', { origin: from.trim(), destination: to.trim(), time })
      setSelected(route); setRouteIndex(0); setMap(route.to); await refresh()
      setNotice('Traseu calculat cu LIGHTDARK.py. Duratele OSRM nu includ traficul în timp real.')
    } catch (error) { setNotice(error.message) }
    finally { setBusy(false) }
  }
  function locate() {
    if (!navigator.geolocation) return setNotice('Localizarea nu este disponibilă în acest browser.')
    setNotice('Se caută locația…')
    navigator.geolocation.getCurrentPosition(({ coords }) => { setFrom(`${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`); setNotice('Locația a fost completată. Alege destinația.') }, () => setNotice('Locația nu a putut fi citită. Permite accesul sau introdu manual plecarea.'), { timeout: 10000 })
  }
  async function publish(e) {
    e.preventDefault()
    if (!requireUser() || busy) return
    const data = Object.fromEntries(new FormData(e.currentTarget))
    setBusy(true)
    try {
      await send('/api/rides', { origin: data.from, destination: data.to, date: data.date, time: data.time, seats: Number(data.seats) })
      setModal(false); await refresh(); setNotice('Cursa a fost publicată pe server.')
    } catch (error) { setNotice(error.message) }
    finally { setBusy(false) }
  }
  async function addClass(e) {
    e.preventDefault(); if (!requireUser()) return
    const form = e.currentTarget
    const data = Object.fromEntries(new FormData(form))
    try { await send('/api/schedule', data); await refresh(); form.reset(); setNotice('Curs salvat în baza LIGHTDARK.') }
    catch (error) { setNotice(error.message) }
  }
  async function login(account, accessToken) {
    setToken(accessToken); setUser(account); setName(account.nume); setOnline(true)
    setHistory([]); setRides([]); setClasses([]); setSelected(null)
    try { await refresh(); setNotice('Ești conectat. Datele sunt încărcate de pe server.') } catch (error) { setNotice(error.message) }
  }
  async function actionRefresh() { if (!requireUser()) return; try { await refresh(); setNotice('Lista a fost actualizată.') } catch (error) { setNotice(error.message) } }
  async function logout() {
    try { await send('/v1/users/logout'); setToken(''); setUser(null); setHistory([]); setRides([]); setClasses([]); setSelected(null); setNotice('Te-ai deconectat.') }
    catch (error) { setNotice(error.message) }
  }
  const routeOption = selected?.options?.[routeIndex]
  const titles = { home: ['Drumul tău. În ritmul tău.', 'Mai puțin timp în trafic. Mai mult timp pentru tine.'], routes: ['Fiecare drum, la îndemână.', 'Regăsește traseele planificate și pornește când ești pregătit.'], rides: ['Drumurile sunt mai bune împreună.', 'Publică o cursă sau rezervă un loc din browser.'], schedule: ['Un pic de ordine. Mai mult timp.', 'Adaugă cursurile și planifică drumul spre facultate.'], settings: ['Fă-l să fie al tău.', 'Contul și datele tale sunt gestionate de serverul LIGHTDARK.'] }
  return <div className={`app ${theme}`}>
    <aside className="sidebar"><a className="brand" href="#" onClick={e => { e.preventDefault(); setPage('home') }}><span className="brand-icon">↗</span><span>F1VE<span className="brand-light"> DR1VE</span><small>YOUR EVERYDAY COPILOT</small></span></a><div className="workspace-label">SPAȚIUL TĂU</div><nav aria-label="Navigare principală">{navigation.map(([id, icon, label]) => <button key={id} className={page === id ? 'nav-item active' : 'nav-item'} onClick={() => { setPage(id); setNotice('') }}><span>{icon}</span><span>{label}</span>{page === id && <i />}</button>)}</nav><div className="sidebar-bottom"><div className="community-card"><span>ÎMPREUNĂ, MAI DEPARTE</span><h3>Același drum.<br />O companie bună.</h3><p>Organizează o cursă cu colegii tăi.</p><button onClick={() => setPage('rides')}>Vezi cursele <span>↗</span></button></div><div className="profile"><span className="avatar">{(name || 'T')[0].toUpperCase()}</span><div><strong>{name || 'Călător'}</strong><small>{user ? 'Cont LIGHTDARK' : 'Neconectat'}</small></div><button aria-label="Setările profilului" onClick={() => setPage('settings')}>⚙</button></div></div></aside>
    <div className="main-shell"><header className="topbar"><span className="breadcrumb">Spațiul tău <span>/</span> <strong>{navigation.find(n => n[0] === page)[2]}</strong></span><div className="top-actions"><span className="local-badge"><i /> {online ? 'LIGHTDARK CONECTAT' : 'SERVER DECONECTAT'}</span><button className="icon-button" aria-label="Schimbă tema" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? '☀' : '☾'}</button><span className="avatar small">{(name || 'T')[0].toUpperCase()}</span></div></header>
    <main><div className="page-heading"><div><div className="eyebrow">BINE AI VENIT{name ? `, ${name.toUpperCase()}` : ' LA F1VE DR1VE'} <span>✦</span></div><h1>{titles[page][0]}</h1><p>{titles[page][1]}</p></div><span className="date-chip">{new Date().toLocaleDateString('ro-RO', { day: 'numeric', month: 'long', year: 'numeric' })}</span></div>
    {notice && <div className="notice" role="status">{notice}<button aria-label="Închide mesajul" onClick={() => setNotice('')}>×</button></div>}
    {page === 'home' && <><div className="dashboard-grid"><section className="panel planner"><div className="section-title"><span className="section-icon">↗</span><div><h2>Unde mergem astăzi?</h2><p>Planifică următorul tău drum.</p></div></div><form onSubmit={plan}><div className="route-inputs"><label><span>PLECARE</span><div className="input-wrap"><i className="point origin" /><input required value={from} onChange={e => setFrom(e.target.value)} placeholder="Adresă, zonă sau localitate" aria-label="Plecare"/><button type="button" className="locate" title="Folosește locația mea" aria-label="Folosește locația mea" onClick={locate}>⌖</button></div></label><button type="button" className="swap" aria-label="Inversează plecarea și destinația" onClick={() => { setFrom(to); setTo(from) }}>⇅</button><label><span>DESTINAȚIE</span><div className="input-wrap"><i className="point destination" /><input required value={to} onChange={e => setTo(e.target.value)} placeholder="Unde vrei să ajungi?" aria-label="Destinație" /></div></label></div><div className="time-row"><label><span>ORA PLECĂRII</span><input type="time" required value={time} onChange={e => setTime(e.target.value)} /></label><span className="transport">▰ <span>Cu mașina</span></span></div><button className="primary full" type="submit" disabled={busy}>{busy ? 'Se calculează…' : 'Calculează traseul'} <span>↗</span></button></form><div className="quick-places"><span>DESTINAȚII RAPIDE</span><div>{['Palas Iași', 'Universitatea Alexandru Ioan Cuza, Iași', 'Universitatea Tehnică Gheorghe Asachi, Iași'].map((place, i) => <button key={place} onClick={() => { setTo(place); setMap(place) }}>{['⌂ Palas', '▦ UAIC', '▦ TUIASI'][i]}</button>)}</div></div><div className="planner-note"><span>◈</span><p>Un drum bine planificat începe cu un pic de liniște.</p></div></section>
    <section className="map-panel" aria-label="Hartă interactivă"><iframe title="Harta destinației" src={mapUrl(map)} loading="lazy" referrerPolicy="no-referrer-when-downgrade" allowFullScreen /><div className="map-label"><i /> EXPLOREAZĂ ORAȘUL <span>Iași & oriunde te duce drumul</span></div><div className="map-bottom"><div><span className="map-pin">⌖</span><div><strong>{selected ? selected.to : 'Următoarea oprire? Tu alegi.'}</strong><small>{selected ? `Plecare ${selected.time} · ${routeOption?.distance ?? '—'} km · ${routeOption?.duration ?? '—'} min` : 'Alege o destinație și pregătește-te de drum.'}</small></div></div>{selected && <a className="primary" href={directions(selected.from, selected.to)} target="_blank" rel="noreferrer">Navighează ↗</a>}</div></section></div>
    {selected?.options && <section className="panel route-results"><div className="card-heading"><h2>Variante calculate de LIGHTDARK</h2><span className="helper">OSRM · estimări fără trafic live</span></div><div className="route-options">{selected.options.map((option, index) => <button key={index} className={routeIndex === index ? 'route-choice chosen' : 'route-choice'} onClick={() => setRouteIndex(index)}><span>Varianta {index + 1}</span><strong>{option.duration} min <small>· {option.distance} km</small></strong><span>Sosire estimată {option.arrival}</span><span>Trafic: {option.traffic} · acoperire {Math.round(option.coverage * 100)}%</span></button>)}</div><details><summary>Indicații pe traseu ({routeOption?.steps.length || 0})</summary><ol className="directions-list">{routeOption?.steps.map((step, index) => <li key={index}>{instruction(step)} <span>{step.distance >= 1000 ? `${(step.distance / 1000).toFixed(1)} km` : `${step.distance} m`}</span></li>)}</ol></details><p className="helper">Google Maps poate alege altă rută. Traficul colaborativ necesită observații reale de la participanți; fără ele apare „Date insuficiente”.</p></section>}
    <div className="bottom-grid"><section className="panel recent"><div className="card-heading"><h2>Trasee recente</h2><button className="text-button" onClick={() => setPage('routes')}>Vezi toate ↗</button></div>{history.length ? history.slice(0, 2).map(route => <RouteRow key={route.id} route={route} />) : <div className="empty-inline"><span>↗</span><div><h3>Primul drum începe aici.</h3><p>Traseele planificate vor apărea în această listă.</p></div></div>}</section><section className="ride-banner"><div className="eyebrow">MAI MULT DECÂT UN DRUM</div><h2>Împarte drumul.<br /><span>Adună amintiri.</span></h2><p>Ai un loc liber? Planifică o cursă cu colegii.</p><button onClick={() => { if (requireUser()) { setPage('rides'); setModal(true) } }}>Organizează o cursă <span>↗</span></button><div className="banner-art" aria-hidden="true">↗</div></section></div><div className="footer-note"><span>✦ Fă loc lucrurilor care contează.</span><span>F1VE DR1VE · Drumuri cu sens.</span></div></>}
    {page === 'routes' && <section className="panel content-panel"><div className="card-heading"><h2>Istoricul traseelor <span className="count">{history.length}</span></h2></div>{history.length ? history.map(route => <RouteRow key={route.id} route={route} onDelete={() => action(`/api/routes/${route.id}`, undefined, 'DELETE')}/>) : <Empty text="Nu ai planificat încă un traseu." action="Planifică primul drum" onClick={() => setPage('home')} />}</section>}
    {page === 'rides' && <section className="panel content-panel"><div className="card-heading"><h2>Curse disponibile</h2><button className="text-button" onClick={() => actionRefresh()}>Actualizează ↻</button><button className="primary" onClick={() => { if (requireUser()) setModal(true) }}>+ Adaugă o cursă</button></div><p className="helper">Cursele sunt partajate între utilizatorii conectați la acest server. Identitatea și vehiculele nu sunt verificate; alege un punct public de întâlnire.</p><input className="search" placeholder="Caută după destinație sau plecare…" aria-label="Caută curse" value={filter} onChange={e => setFilter(e.target.value)}/>{rides.filter(r => `${r.from} ${r.to}`.toLocaleLowerCase('ro').includes(filter.toLocaleLowerCase('ro'))).map(ride => <div className="ride-row" key={ride.id}><span className="route-symbol">♧</span><div><h3>{ride.from} → {ride.to}</h3><p>{ride.date} · {ride.time} · {ride.seats} {ride.seats === 1 ? 'loc' : 'locuri'} · {ride.driver}</p></div>{ride.mine ? <button className="text-button danger" onClick={() => action(`/api/rides/${ride.id}`, undefined, 'DELETE')}>Șterge</button> : <button className="text-button" disabled={!ride.booked && !ride.seats} onClick={() => action(`/api/rides/${ride.id}/reservation`, undefined, ride.booked ? 'DELETE' : 'POST')}>{ride.booked ? 'Anulează rezervarea' : 'Rezervă un loc'}</button>}</div>)}{!rides.length && <Empty text="Ai un loc liber sau un drum în plan?" action="Adaugă prima cursă" onClick={() => { if (requireUser()) setModal(true) }} />}{rides.length > 0 && !rides.some(r => `${r.from} ${r.to}`.toLocaleLowerCase('ro').includes(filter.toLocaleLowerCase('ro'))) && <p className="helper">Nicio cursă nu corespunde căutării.</p>}</section>}
    {page === 'schedule' && <div className="schedule-grid"><section className="panel content-panel"><h2>Adaugă un curs</h2><form className="stack-form" onSubmit={addClass}><label>Denumirea cursului<input name="title" required placeholder="Ex. Programare web" maxLength={100}/></label><label>Locația<input name="location" required placeholder="Facultate, corp, adresă" maxLength={200}/></label><div className="form-columns"><label>Ziua<select name="day">{['Luni','Marți','Miercuri','Joi','Vineri','Sâmbătă','Duminică'].map(day => <option key={day}>{day}</option>)}</select></label><label>Ora<input name="time" type="time" required /></label></div><button className="primary">Salvează cursul +</button></form></section><section className="panel content-panel"><h2>Programul tău</h2>{classes.length ? classes.map(item => <div className="class-row" key={item.id}><span className="class-time">{item.time}<small>{item.day}</small></span><div><h3>{item.title}</h3><p>{item.location}</p><button className="text-button" onClick={() => { setTo(item.location); setPage('home') }}>Planifică drumul ↗</button></div><button className="icon-button" aria-label={`Șterge ${item.title}`} onClick={() => action(`/api/schedule/${item.id}`, undefined, 'DELETE')}>×</button></div>) : <p className="helper">Adaugă primul curs pentru a-ți organiza săptămâna.</p>}</section></div>}
    {page === 'settings' && <section className="panel content-panel settings-panel"><h2>Cont LIGHTDARK și aspect</h2>{user ? <div className="account-summary"><div><strong>{user.nume}</strong><p>{user.email} · {user.facultate || 'Facultate nespecificată'}</p></div><button className="text-button" onClick={logout}>Deconectare</button></div> : <AccountForm onLogin={login} />}<label className="settings-label">Cum te numești?<input value={name} maxLength={50} onChange={e => setName(e.target.value)} placeholder="Numele tău" /></label><div className="setting-row"><div><h3>Temă luminoasă</h3><p>Alege aspectul care îți place.</p></div><button className={`toggle ${theme === 'light' ? 'on' : ''}`} role="switch" aria-checked={theme === 'light'} aria-label="Temă luminoasă" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}><span /></button></div><div className="setting-row"><div><h3>Date salvate în LIGHTDARK</h3><p>Traseele, conturile, orarul și cursele folosesc bazele SQLite ale LIGHTDARK.py de pe server. Telefonul trebuie să se conecteze la același server.</p></div><span>◈</span></div></section>}
    </main></div>
    {modal && <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget) setModal(false) }}><dialog ref={dialogRef} aria-labelledby="ride-title" onCancel={() => setModal(false)}><div className="card-heading"><h2 id="ride-title">Organizează o cursă</h2><button className="icon-button" autoFocus aria-label="Închide" onClick={() => setModal(false)}>×</button></div><form className="stack-form" onSubmit={publish}><label>Numele tău<input name="driver" required value={user?.nume || name} readOnly maxLength={60}/></label><label>Plecare<input name="from" required maxLength={200}/></label><label>Destinație<input name="to" required maxLength={200}/></label><div className="form-columns"><label>Data<input type="date" name="date" required min={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)} /></label><label>Ora<input type="time" name="time" required /></label></div><label>Locuri disponibile<input type="number" name="seats" defaultValue="1" min="1" max="8" required /></label><p className="helper">Alege un punct public de întâlnire. Cursa va fi vizibilă celorlalți utilizatori conectați la server.</p><button className="primary full" disabled={busy}>{busy ? 'Se publică…' : 'Publică cursa ↗'}</button>{notice && <p className="helper" role="status">{notice}</p>}</form></dialog></div>}
  </div>
}
function RouteRow({ route, onDelete }) { return <div className="route-row"><span className="route-symbol">↗</span><div><h3>{route.from} <span>→</span> {route.to}</h3><p>{route.date} <span>·</span> Plecare la {route.time}</p></div><a className="icon-button" href={directions(route.from, route.to)} target="_blank" rel="noreferrer" aria-label={`Navighează spre ${route.to}`}>↗</a>{onDelete && <button className="icon-button" onClick={onDelete} aria-label="Șterge traseul">×</button>}</div> }
function Empty({ text, action, onClick }) { return <div className="empty"><span>↗</span><h3>{text}</h3><button className="primary" onClick={onClick}>{action}</button></div> }

function instruction(step) {
  const directions = { left: 'stânga', right: 'dreapta', 'slight left': 'ușor la stânga', 'slight right': 'ușor la dreapta', 'sharp left': 'strâns la stânga', 'sharp right': 'strâns la dreapta', straight: 'înainte', uturn: 'întoarcere' }
  if (step.type === 'arrive') return 'Ai ajuns la destinație'
  if (step.type === 'depart') return `Pornește pe ${step.name}`
  if (step.type.includes('roundabout') || step.type.includes('rotary')) return `Sens giratoriu · ${step.name}`
  return `Continuă ${directions[step.modifier] || ''} pe ${step.name}`
}
function AccountForm({ onLogin }) {
  const [register, setRegister] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(e) {
    e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); setBusy(true); setError('')
    try {
      if (register) await send('/v1/users/register', data)
      const result = await send('/v1/users/login', { email: data.email, parola: data.parola })
      await onLogin(result.user, result.access_token)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <form className="stack-form account-form" onSubmit={submit}><h3>{register ? 'Creează un cont' : 'Conectează-te'}</h3>{register && <><label>Nume<input name="nume" minLength={2} maxLength={100} autoComplete="name" required /></label><label>Facultate<input name="facultate" maxLength={120} /></label></>}<label>E-mail<input name="email" type="email" maxLength={254} autoComplete="email" required /></label><label>Parolă<input name="parola" type="password" minLength={register ? 10 : 1} maxLength={128} autoComplete={register ? 'new-password' : 'current-password'} required /></label>{register && <p className="helper">Folosește cel puțin 10 caractere.</p>}{error && <p role="alert" className="auth-error">{error}</p>}<button className="primary" disabled={busy}>{busy ? 'Se conectează…' : register ? 'Creează contul' : 'Conectare'}</button><button type="button" className="text-button" onClick={() => { setRegister(!register); setError('') }}>{register ? 'Am deja cont' : 'Nu ai cont? Înregistrează-te'}</button></form>
}
