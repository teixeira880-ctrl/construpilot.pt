// AK.3 — Widget reutilizável de pedidos recentes.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";

const KIND_LABELS = {
  contact: "Contacto",
  quote: "Orçamento",
  ai_chat: "Chat IA",
  permit: "Autorização",
  download: "Download",
  calculation: "Cálculo",
};

export default function PedidosRecentes({ limit = 5 }) {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get(`/admin/activity?state=novo&page_size=${limit}`)
       .then(({ data }) => setItems(data.items || []))
       .catch(() => {});
    api.get("/admin/activity/stats")
       .then(({ data }) => setStats(data))
       .catch(() => {});
  }, [limit]);

  return (
    <div data-testid="pedidos-recentes" className="rounded border p-4 bg-background">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Pedidos recentes</h3>
        <Link
          to="/admin/pedidos"
          data-testid="pedidos-ver-todos"
          className="text-xs text-primary hover:underline"
        >
          Ver todos →
        </Link>
      </div>
      {stats && (
        <div className="flex gap-2 flex-wrap mb-3 text-xs">
          <span className="px-2 py-0.5 rounded bg-muted">
            Total: <strong>{stats.total}</strong>
          </span>
          <span className="px-2 py-0.5 rounded bg-muted">
            7 dias: <strong>{stats.last_7_days}</strong>
          </span>
          <span className="px-2 py-0.5 rounded bg-muted">
            30 dias: <strong>{stats.last_30_days}</strong>
          </span>
        </div>
      )}
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Sem novos pedidos.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((it) => (
            <li key={it.id}>
              <Link
                to={`/admin/pedidos?id=${it.id}`}
                data-testid={`widget-pedido-${it.id}`}
                className="block rounded hover:bg-accent/40 p-2"
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <strong>{KIND_LABELS[it.kind] || it.kind}</strong>
                  <span className="text-muted-foreground">
                    {new Date(it.created_at).toLocaleDateString("pt-PT")}
                  </span>
                </div>
                <div className="text-sm truncate">{it.user_name || it.user_email}</div>
                <div className="text-xs text-muted-foreground truncate">{it.summary}</div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
