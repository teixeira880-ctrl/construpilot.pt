#!/bin/sh
# Arranque do backend: UM processo uvicorn (os workers de fila e o agendador vivem neste processo;
# o lease em core/scheduler_lock.py protege mesmo assim contra duplicados se houver mais do que um).
set -eu

# Dr.Jit (Mitsuba) precisa de encontrar o libLLVM; o caminho depende da arquitetura (aarch64 / x86_64).
if [ -z "${DRJIT_LIBLLVM_PATH:-}" ]; then
  for f in /usr/lib/*-linux-gnu/libLLVM-15.so.1 /usr/lib/*-linux-gnu/libLLVM-15.so; do
    if [ -e "$f" ]; then export DRJIT_LIBLLVM_PATH="$f"; break; fi
  done
fi

exec uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1 \
  --proxy-headers --forwarded-allow-ips="*" --timeout-keep-alive 75
