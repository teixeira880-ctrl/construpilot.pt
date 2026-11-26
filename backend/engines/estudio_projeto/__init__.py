"""Estúdio de Projeto — modelo único do edifício.

Um só modelo (pisos, paredes multicamada, vãos ligados às paredes, cobertura) é a fonte de tudo o que se vê e mede:
planta 2D, 3D, alçados, cortes, áreas e medições geométricas (`derivar.py`, `desenhos.py`). Nada é gerado por IA e
nada é estimado por rácios: o que não pode ser calculado com exatidão sai como aviso, nunca como valor inventado.
"""
from engines.estudio_projeto.modelo import ErroModelo, de_processo, normalizar, modelo_vazio  # noqa: F401
from engines.estudio_projeto.derivar import derivar  # noqa: F401
