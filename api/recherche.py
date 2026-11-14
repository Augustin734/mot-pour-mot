"""Recherche plein texte : requête de l'utilisateur, pertinence et surlignage.

La configuration « francais » (stemming, accents ignorés) est celle des colonnes
recherche des tables dossier et intervention (db/modeles.py).
"""

from sqlalchemy import ColumnElement, func, literal
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, REGCONFIG

from db.modeles import CONFIG_RECHERCHE

# Le surlignage entoure les mots trouvés de <mark>…</mark> : le texte est échappé avant,
# pour que le front puisse afficher le résultat comme du HTML sans risque d'injection.
DEBUT_SURLIGNAGE = "<mark>"
FIN_SURLIGNAGE = "</mark>"


def requete(q: str) -> ColumnElement:
    """tsquery tirée de la saisie, avec la syntaxe d'un moteur de recherche.

    websearch_to_tsquery accepte "expression exacte", -exclu et « or » sans jamais lever
    d'erreur de syntaxe, contrairement à to_tsquery.
    """
    return func.websearch_to_tsquery(literal(CONFIG_RECHERCHE).cast(REGCONFIG), q)


def pertinence(colonne: ColumnElement, tsquery: ColumnElement) -> ColumnElement:
    # ts_rank renvoie un real (4 octets), arrondi en passant par Python : le curseur ne
    # retrouverait plus la valeur exacte et sauterait des lignes. Le double precision fait
    # l'aller-retour sans perte.
    return func.ts_rank(colonne, tsquery).cast(DOUBLE_PRECISION)


def echapper_html(texte: ColumnElement) -> ColumnElement:
    return func.replace(func.replace(func.replace(texte, "&", "&amp;"), "<", "&lt;"), ">", "&gt;")


def surligner(texte: ColumnElement, tsquery: ColumnElement, options: str = "") -> ColumnElement:
    """Texte (HTML échappé) où les mots trouvés sont entourés de <mark>."""
    reglages = f"StartSel={DEBUT_SURLIGNAGE}, StopSel={FIN_SURLIGNAGE}"
    if options:
        reglages = f"{reglages}, {options}"
    return func.ts_headline(
        literal(CONFIG_RECHERCHE).cast(REGCONFIG), echapper_html(texte), tsquery, reglages
    )
