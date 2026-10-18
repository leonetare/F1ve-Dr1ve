let token = ''
try { token = sessionStorage.getItem('f1ve-session') || '' } catch { /* Memory-only session. */ }
export function setToken(value) { token = value; try { if (value) sessionStorage.setItem('f1ve-session', value); else sessionStorage.removeItem('f1ve-session') } catch { /* Memory-only session. */ } }
export function hasToken() { return Boolean(token) }
export async function api(path, options = {}) {
  let response
  try {
    response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers }, signal: AbortSignal.timeout(90000) })
  } catch { throw new Error('Serverul Python nu este disponibil. Pornește python web_server.py și reîncearcă.') }
  let data
  try { data = await response.json() } catch { throw new Error('Serverul Python nu este disponibil la această adresă.') }
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(d => `${d.loc.at(-1)}: ${d.msg}`).join('; ') : 'Operația nu a reușit.'
    const error = new Error(message); error.status = response.status; throw error
  }
  return data
}
export const send = (path, data, method = 'POST') => api(path, { method, ...(data !== undefined ? { body: JSON.stringify(data) } : {}) })
