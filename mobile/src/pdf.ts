/**
 * Génération et partage du dossier technique PDF.
 *
 * - Web (Expo web / preview browser) : télécharge via un <a download> depuis un blob.
 * - Natif iOS/Android : sauvegarde dans le cache Expo puis ouvre la feuille de partage.
 */
import { Platform } from 'react-native';
import * as Sharing from 'expo-sharing';

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

interface DossierPayload {
  project_name: string;
  stair_input: any;
  stair_result: any;
  concrete_analysis?: any | null;
  author?: string | null;
}

function sanitizeFilename(name: string): string {
  const clean = name.replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 40);
  return clean || 'dossier';
}

async function postDossier(payload: DossierPayload): Promise<Response> {
  if (!BASE) throw new Error('EXPO_PUBLIC_BACKEND_URL non défini.');
  const res = await fetch(`${BASE}/api/dossier/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = '';
    try { detail = JSON.stringify((await res.json()).detail); } catch {}
    throw new Error(`Erreur backend (HTTP ${res.status}). ${detail}`);
  }
  return res;
}

/**
 * Génère + partage/téléchargement du PDF.
 * @returns nom du fichier produit
 */
export async function generateAndSharePDF(payload: DossierPayload): Promise<string> {
  const res = await postDossier(payload);
  const filename = `stairpilot_${sanitizeFilename(payload.project_name)}.pdf`;

  if (Platform.OS === 'web') {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    return filename;
  }

  // Natif : bytes → cache → sharing
  const buf = await res.arrayBuffer();
  const bytes = new Uint8Array(buf);
  const { File, Paths } = await import('expo-file-system');
  const file = new File(Paths.cache, filename);
  try { file.delete(); } catch {}
  file.create();
  file.write(bytes);

  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(file.uri, {
      mimeType: 'application/pdf',
      dialogTitle: 'Partager le dossier STAIRPILOT',
      UTI: 'com.adobe.pdf',
    });
  }
  return filename;
}
