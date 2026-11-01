"""Législatures connues d'avance, pour charger une séance avant le jeu « acteurs et organes ».

Les dates de l'open data (pipeline.acteurs_organes) remplacent ensuite celles-ci : par
exemple, la 17e y commence le 1er juillet 2024, et non le 18 (première séance).
"""

from datetime import date

from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert

from db.modeles import Legislature

# Dates officielles de début et de fin des législatures de la Ve République couvertes.
# La 16e s'est terminée par la dissolution du 9 juin 2024.
LEGISLATURES = {
    14: (date(2012, 6, 20), date(2017, 6, 20)),
    15: (date(2017, 6, 21), date(2022, 6, 21)),
    16: (date(2022, 6, 22), date(2024, 6, 9)),
    17: (date(2024, 7, 18), None),
}


def assurer_legislature(connexion: Connection, numero: int) -> None:
    """Crée la législature si elle manque (sans écraser une ligne déjà chargée)."""
    debut, fin = LEGISLATURES[numero]
    connexion.execute(
        insert(Legislature)
        .values(numero=numero, debut=debut, fin=fin)
        .on_conflict_do_nothing(index_elements=["numero"])
    )
