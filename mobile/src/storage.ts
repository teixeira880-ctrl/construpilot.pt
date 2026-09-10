/**
 * CRUD projets locaux — AsyncStorage.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { StoredProject } from './types';

const KEY = 'stairpilot_projects_v1';

function uuid(): string {
  // simple non-cryptographic UUID
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function listProjects(): Promise<StoredProject[]> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
  } catch {
    return [];
  }
}

export async function getProject(id: string): Promise<StoredProject | null> {
  const all = await listProjects();
  return all.find((p) => p.id === id) ?? null;
}

export async function saveProject(
  input: Omit<StoredProject, 'id' | 'created_at' | 'updated_at'> & {
    id?: string;
  }
): Promise<StoredProject> {
  const all = await listProjects();
  const now = new Date().toISOString();
  if (input.id) {
    const idx = all.findIndex((p) => p.id === input.id);
    if (idx >= 0) {
      const updated: StoredProject = {
        ...all[idx],
        ...input,
        id: input.id,
        updated_at: now,
      };
      all[idx] = updated;
      await AsyncStorage.setItem(KEY, JSON.stringify(all));
      return updated;
    }
  }
  const created: StoredProject = {
    ...input,
    id: input.id ?? uuid(),
    created_at: now,
    updated_at: now,
  };
  all.unshift(created);
  await AsyncStorage.setItem(KEY, JSON.stringify(all));
  return created;
}

export async function deleteProject(id: string): Promise<void> {
  const all = await listProjects();
  const filtered = all.filter((p) => p.id !== id);
  await AsyncStorage.setItem(KEY, JSON.stringify(filtered));
}

export async function duplicateProject(id: string): Promise<StoredProject | null> {
  const src = await getProject(id);
  if (!src) return null;
  return saveProject({
    name: `${src.name} (copie)`,
    type: src.type,
    input: src.input,
    result: src.result,
  });
}
