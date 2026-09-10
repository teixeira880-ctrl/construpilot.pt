/**
 * Client API STAIRPILOT — appelle le moteur de calcul backend.
 * Base URL : EXPO_PUBLIC_BACKEND_URL (jamais en dur).
 */
import type {
  StairInput,
  QuarterTurnInput,
  HalfTurnInput,
  StairResult,
  StairType,
} from './types';

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

if (!BASE) {
  // On log l'erreur mais on ne crash pas pour permettre l'ouverture de l'app.
  console.warn('EXPO_PUBLIC_BACKEND_URL non défini. Les calculs vont échouer.');
}

const ENDPOINTS: Record<StairType, string> = {
  'straight': '/api/calculate/straight',
  'quarter-turn-bottom': '/api/calculate/quarter-turn-bottom',
  'quarter-turn-top': '/api/calculate/quarter-turn-top',
  'half-turn': '/api/calculate/half-turn',
  'helicoidal': '/api/calculate/helicoidal',
};

const TIMEOUT_MS = 12000;

async function fetchWithTimeout(url: string, opts: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function computeStair(
  type: StairType,
  input: StairInput | QuarterTurnInput | HalfTurnInput
): Promise<StairResult> {
  const endpoint = ENDPOINTS[type];
  const url = `${BASE}${endpoint}`;
  let res: Response;
  try {
    res = await fetchWithTimeout(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw new Error('Le moteur de calcul met trop de temps à répondre (timeout).');
    }
    throw new Error('Impossible d\'atteindre le moteur de calcul. Vérifiez votre connexion.');
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : '';
    } catch {}
    throw new Error(`Erreur backend (HTTP ${res.status}). ${detail}`);
  }
  return await res.json();
}

export async function getNormsFR(): Promise<Record<string, any>> {
  const url = `${BASE}/api/norms/fr`;
  const res = await fetchWithTimeout(url, { method: 'GET' });
  if (!res.ok) throw new Error(`Erreur norms/fr HTTP ${res.status}`);
  return await res.json();
}

export async function runOptimize(body: any): Promise<any> {
  const url = `${BASE}/api/optimize`;
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = JSON.stringify((await res.json()).detail); } catch {}
    throw new Error(`Erreur backend (HTTP ${res.status}). ${detail}`);
  }
  return await res.json();
}

export async function analyzeConcrete(body: any): Promise<any> {
  const url = `${BASE}/api/concrete/analyze`;
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = JSON.stringify((await res.json()).detail); } catch {}
    throw new Error(`Erreur backend (HTTP ${res.status}). ${detail}`);
  }
  return await res.json();
}
