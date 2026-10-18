"""Vérifie le calcul des séries : python cards/test_streaks.py"""
from datetime import date

from build import streaks

d = date.fromisoformat
days = {d("2026-05-01"): 1, d("2026-05-02"): 2, d("2026-05-03"): 0, d("2026-05-04"): 3, d("2026-05-05"): 0}

# Aujourd'hui à zéro : la série d'hier compte encore.
assert streaks(days, d("2026-05-05")) == ((1, d("2026-05-04"), d("2026-05-04")), (2, d("2026-05-01"), d("2026-05-02")))
# Aujourd'hui actif : la série l'inclut.
assert streaks(days | {d("2026-05-05"): 4}, d("2026-05-05"))[0] == (2, d("2026-05-04"), d("2026-05-05"))
# Hier et aujourd'hui à zéro : plus de série en cours.
assert streaks(days | {d("2026-05-06"): 0}, d("2026-05-06"))[0][0] == 0
print("ok")
