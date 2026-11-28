# Audit 28/11/2026 — correctifs pour construpilot.pt

Ordre : l109 → l119 (lots du .fr, appliqués avec l'argument `pt` : chaque correctif dont l'ancre n'existe pas sur le .pt
est simplement « IGNORÉ / ABSENT / N/A », rien n'est modifié), puis l122pt (mêmes erreurs adaptées au code portugais).

    cd /app && for n in 109 110 111 112 113 114 115 116 117 118 119; do python3 lots/audit_28_11/l$n/apply_l$n.py /app pt; done
    python3 lots/audit_28_11/l122pt/apply_l122pt.py /app pt
