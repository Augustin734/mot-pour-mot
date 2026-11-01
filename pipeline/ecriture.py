"""Écriture idempotente en base, partagée par tous les chargements du pipeline.

Chaque ligne est insérée ou mise à jour selon sa clé (identifiant AN le plus souvent). La
mise à jour n'a lieu que si une valeur a réellement changé : recharger des données
identiques ne touche à rien, et maj_le n'avance que sur une vraie correction de l'open
data. Rien n'est supprimé.
"""

from sqlalchemy import Connection, Table, or_
from sqlalchemy.dialects.postgresql import insert

# PostgreSQL limite une requête à 65 535 paramètres : les lignes sont écrites par paquets.
TAILLE_PAQUET = 1000


def upsert(connexion: Connection, table: Table, lignes: list[dict], cles: list[str]) -> int:
    """INSERT … ON CONFLICT DO UPDATE, seulement si une colonne diffère. Renvoie le nombre
    de lignes insérées ou modifiées."""
    ecrites = 0
    for debut in range(0, len(lignes), TAILLE_PAQUET):
        paquet = lignes[debut : debut + TAILLE_PAQUET]
        requete = insert(table).values(paquet)
        colonnes = [c for c in paquet[0] if c not in cles]
        requete = requete.on_conflict_do_update(
            index_elements=cles,
            set_={c: requete.excluded[c] for c in colonnes},
            where=or_(*(table.c[c].is_distinct_from(requete.excluded[c]) for c in colonnes)),
        )
        # RETURNING plutôt que rowcount, qui n'est pas fiable pour un INSERT multi-lignes.
        ecrites += len(connexion.execute(requete.returning(table.c[cles[0]])).all())
    return ecrites
