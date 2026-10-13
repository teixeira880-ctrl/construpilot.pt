import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const DEFAULTS = { radar_enabled: true, postal_enabled: false, country: "PT" };

let _cache = null;
let _promise = null;

export async function fetchAppConfig() {
  if (_cache) return _cache;
  if (!_promise) {
    _promise = api
      .get("/config")
      .then(({ data }) => {
        _cache = { ...DEFAULTS, ...(data || {}) };
        return _cache;
      })
      .catch(() => {
        _cache = { ...DEFAULTS };
        return _cache;
      });
  }
  return _promise;
}

export function useAppConfig() {
  const [config, setConfig] = useState(_cache || DEFAULTS);
  const [ready, setReady] = useState(!!_cache);
  useEffect(() => {
    let active = true;
    fetchAppConfig().then((cfg) => {
      if (active) {
        setConfig(cfg);
        setReady(true);
      }
    });
    return () => {
      active = false;
    };
  }, []);
  return { config, ready };
}
