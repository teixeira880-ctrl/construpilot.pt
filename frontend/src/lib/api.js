import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("construpilot_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const eur = (v) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 })
    .format(Number(v || 0));

export const eur2 = (v) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", minimumFractionDigits: 2 })
    .format(Number(v || 0));

export const num = (v, d = 0) =>
  new Intl.NumberFormat("fr-FR", { maximumFractionDigits: d }).format(Number(v || 0));

export const DIFF_STYLE = {
  easy: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  intermediate: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30",
  hard: "bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30",
  pro: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30",
};

export const IMAGES = {
  hero: "https://images.unsplash.com/photo-1670589953882-b94c9cb380f5?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzV8MHwxfHNlYXJjaHwzfHxsdXh1cnklMjBtb2Rlcm4lMjBhcmNoaXRlY3R1cmUlMjBleHRlcmlvcnxlbnwwfHx8fDE3ODY0NDc4OTF8MA&ixlib=rb-4.1.0&q=85",
  project_card_exterior:
    "https://images.unsplash.com/photo-1748063578185-3d68121b11ff?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzV8MHwxfHNlYXJjaHw0fHxsdXh1cnklMjBtb2Rlcm4lMjBhcmNoaXRlY3R1cmUlMjBleHRlcmlvcnxlbnwwfHx8fDE3ODY0NDc4OTF8MA&ixlib=rb-4.1.0&q=85",
  project_card_bathroom:
    "https://images.unsplash.com/photo-1661107259637-4e1c55462428?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxOTJ8MHwxfHNlYXJjaHwzfHxtb2Rlcm4lMjBtaW5pbWFsaXN0JTIwYmF0aHJvb20lMjByZW5vdmF0aW9ufGVufDB8fHx8MTc4NjQ0Nzg5MXww&ixlib=rb-4.1.0&q=85",
  project_card_interior:
    "https://images.unsplash.com/photo-1598928506311-c55ded91a20c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxNzV8MHwxfHNlYXJjaHwxfHxlbGVnYW50JTIwaW50ZXJpb3IlMjBob21lJTIwZGVzaWdufGVufDB8fHx8MTc4NjQ0Nzg5MXww&ixlib=rb-4.1.0&q=85",
  dashboard_banner:
    "https://images.unsplash.com/photo-1608303588026-884930af2559?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzOTB8MHwxfHNlYXJjaHwzfHxjb25zdHJ1Y3Rpb24lMjBibHVlcHJpbnQlMjBwbGFubmluZ3xlbnwwfHx8fDE3ODY0NDc4OTF8MA&ixlib=rb-4.1.0&q=85",
};
