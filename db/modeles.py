"""Tables V1 de Mot pour mot (dictionnaire : docs/cadrage/05-dictionnaire-de-donnees.md).

Choix de conception :
- Les identifiants de l'AN (PA…, PO…, DLR…) sont les clés : la collecte est idempotente.
- Les valeurs fermées (statut, position…) sont du texte contraint par un CHECK plutôt qu'un
  ENUM PostgreSQL : un ENUM se modifie mal par migration (impossible de retirer une valeur).
- Les tables issues de l'open data portent cree_le et maj_le ; maj_le est avancé par un
  trigger à chaque mise à jour (voir la migration initiale). Rien n'est supprimé.
- La recherche plein texte utilise la configuration « francais » (stemming français et
  accents ignorés), créée par la migration initiale.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Configuration de recherche plein texte créée par la migration initiale.
CONFIG_RECHERCHE = "francais"

# Noms de contraintes stables : Alembic peut ainsi les retrouver dans les migrations suivantes.
CONVENTION_NOMMAGE = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENTION_NOMMAGE)
    # Dates toujours avec fuseau (timestamptz) ; texte sans longueur maximale.
    type_annotation_map = {datetime: DateTime(timezone=True), str: Text}


def valeurs_autorisees(colonne: str, valeurs: tuple[str, ...]) -> CheckConstraint:
    """CHECK limitant une colonne texte à une liste fermée de valeurs."""
    liste = ", ".join(f"'{v}'" for v in valeurs)
    return CheckConstraint(f"{colonne} IN ({liste})", name=colonne)


class Horodatage:
    """Dates de première insertion et de dernière mise à jour (tables open data)."""

    cree_le: Mapped[datetime] = mapped_column(server_default=func.now())
    maj_le: Mapped[datetime] = mapped_column(server_default=func.now())


# Valeurs fermées, réutilisées par le pipeline et l'API.
TYPES_DOSSIER = ("projet", "proposition")
STATUTS_DOSSIER = ("en_cours", "adopte", "rejete", "retire")
TYPES_ETAPE = ("depot", "commission", "seance", "cmp", "lecture_definitive", "promulgation")
CHAMBRES = ("an", "senat")
TYPES_TEXTE = ("depose", "commission", "adopte")
TYPES_SEANCE = ("seance_publique", "commission")
QUALITES_APPARTENANCE = ("membre", "apparente", "president", "non_inscrit")
QUALITES_ORATEUR = ("depute", "ministre", "rapporteur", "president", "autre")
TYPES_SCRUTIN = ("ordinaire", "solennel", "motion")
RESULTATS_SCRUTIN = ("adopte", "rejete")
POSITIONS_VOTE = ("pour", "contre", "abstention", "non_votant")
POSITIONS_GROUPE = ("pour", "contre", "divise", "pas_exprime")
STATUTS_FICHE = ("publiee", "a_relire", "rejetee")
STATUTS_RUN = ("en_cours", "succes", "echec")


# --- Référentiel -------------------------------------------------------------


class Legislature(Horodatage, Base):
    __tablename__ = "legislature"

    numero: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    debut: Mapped[date]
    fin: Mapped[date | None]


class Groupe(Horodatage, Base):
    __tablename__ = "groupe"

    id: Mapped[str] = mapped_column(primary_key=True)  # PO…
    legislature: Mapped[int] = mapped_column(ForeignKey("legislature.numero"))
    sigle: Mapped[str]
    nom: Mapped[str]
    couleur: Mapped[str | None]  # couleur officielle de l'AN (couleurAssociee), ex. #313567
    # Rang de gauche à droite dans l'hémicycle (pipeline/reference/ordre_hemicycle.csv) :
    # absent de l'open data. Un groupe renommé garde le rang de son prédécesseur.
    ordre_hemicycle: Mapped[int | None]


class Depute(Horodatage, Base):
    __tablename__ = "depute"

    id: Mapped[str] = mapped_column(primary_key=True)  # PA…
    nom: Mapped[str]
    prenom: Mapped[str]
    circonscription: Mapped[str | None]


class Appartenance(Horodatage, Base):
    """Mandat de groupe daté : donne le groupe d'un député à une date."""

    __tablename__ = "appartenance"
    __table_args__ = (
        CheckConstraint("fin IS NULL OR fin >= debut", name="periode"),
        valeurs_autorisees("qualite", QUALITES_APPARTENANCE),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # PM…, identifiant AN du mandat
    depute_id: Mapped[str] = mapped_column(ForeignKey("depute.id"), index=True)
    groupe_id: Mapped[str] = mapped_column(ForeignKey("groupe.id"), index=True)
    # Un président de groupe a deux mandats qui se chevauchent : membre et président.
    qualite: Mapped[str]
    debut: Mapped[date]
    fin: Mapped[date | None]  # vide si en cours


# --- Travaux législatifs -----------------------------------------------------


class Dossier(Horodatage, Base):
    __tablename__ = "dossier"
    __table_args__ = (
        valeurs_autorisees("type", TYPES_DOSSIER),
        valeurs_autorisees("statut", STATUTS_DOSSIER),
        Index("ix_dossier_recherche", "recherche", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # DLR…
    legislature: Mapped[int] = mapped_column(ForeignKey("legislature.numero"), index=True)
    titre_officiel: Mapped[str]
    titre_court: Mapped[str | None]
    alias: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    type: Mapped[str]
    statut: Mapped[str] = mapped_column(server_default="en_cours")
    date_depot: Mapped[date | None]
    date_derniere_activite: Mapped[datetime | None]
    score_importance: Mapped[Decimal | None]
    themes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    # Le titre court et les alias (noms médiatiques) pèsent plus que le titre officiel.
    recherche: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            f"setweight(to_tsvector('{CONFIG_RECHERCHE}', coalesce(titre_court, '')), 'A')"
            f" || setweight(to_tsvector('{CONFIG_RECHERCHE}', alias_en_texte(alias)), 'A')"
            f" || setweight(to_tsvector('{CONFIG_RECHERCHE}', titre_officiel), 'B')",
            persisted=True,
        ),
    )


class Etape(Horodatage, Base):
    __tablename__ = "etape"
    __table_args__ = (
        valeurs_autorisees("type", TYPES_ETAPE),
        valeurs_autorisees("chambre", CHAMBRES),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # identifiant de l'acte législatif
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossier.id"), index=True)
    type: Mapped[str]
    chambre: Mapped[str | None]  # vide pour la CMP et la promulgation, communes aux deux chambres
    date: Mapped[date | None]


class Texte(Horodatage, Base):
    """Un texte numéroté. L'AN renumérote à chaque législature, d'où la clé composée."""

    __tablename__ = "texte"
    __table_args__ = (valeurs_autorisees("type", TYPES_TEXTE),)

    legislature: Mapped[int] = mapped_column(ForeignKey("legislature.numero"), primary_key=True)
    numero: Mapped[str] = mapped_column(primary_key=True)  # ex. « 3851 », bibard nettoyé
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossier.id"), index=True)
    type: Mapped[str]


# --- Débats ------------------------------------------------------------------


class Seance(Horodatage, Base):
    __tablename__ = "seance"
    __table_args__ = (valeurs_autorisees("type", TYPES_SEANCE),)

    id: Mapped[str] = mapped_column(primary_key=True)  # identifiant AN de la réunion
    legislature: Mapped[int] = mapped_column(ForeignKey("legislature.numero"), index=True)
    type: Mapped[str] = mapped_column(server_default="seance_publique")
    organe_id: Mapped[str | None]
    debut: Mapped[datetime] = mapped_column(index=True)
    url_compte_rendu: Mapped[str | None]
    url_video: Mapped[str | None]


class PointOdj(Horodatage, Base):
    __tablename__ = "point_odj"

    id: Mapped[str] = mapped_column(primary_key=True)
    seance_id: Mapped[str] = mapped_column(ForeignKey("seance.id"), index=True)
    numero: Mapped[int | None]  # rang dans l'ordre du jour (valeur_ptsODJ)
    dossier_id: Mapped[str | None] = mapped_column(ForeignKey("dossier.id"), index=True)
    titre: Mapped[str]


class Intervention(Horodatage, Base):
    """Une prise de parole : l'entité centrale (recherche, frise, citations)."""

    __tablename__ = "intervention"
    __table_args__ = (
        # Clé naturelle : rend le rechargement d'une séance idempotent.
        UniqueConstraint("seance_id", "ordre"),
        valeurs_autorisees("qualite", QUALITES_ORATEUR),
        Index("ix_intervention_recherche", "recherche", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    seance_id: Mapped[str] = mapped_column(ForeignKey("seance.id"))
    point_id: Mapped[str | None] = mapped_column(ForeignKey("point_odj.id"), index=True)
    ordre: Mapped[int]  # ordre_absolu_seance
    type_debat: Mapped[str | None]
    # Type brut de prise de parole dans le compte rendu (ex. INTERRUPTION_1_10).
    code_grammaire: Mapped[str | None]
    # Pas de clé étrangère vers texte : une séance peut arriver avant son texte, ou porter
    # un numéro mal formé. La liaison (numero_texte + legislature de la séance) est
    # calculée par le pipeline, et les interventions non rattachées sont journalisées.
    numero_texte: Mapped[str | None] = mapped_column(index=True)
    # Dossier de l'intervention, calculé par pipeline.liaison : celui de son texte, sinon
    # celui de son point de l'ordre du jour (ex. budget sans numéro, rattaché par le titre).
    dossier_id: Mapped[str | None] = mapped_column(ForeignKey("dossier.id"), index=True)
    article: Mapped[str | None]
    amendement: Mapped[str | None]
    # Identifiant brut de l'orateur (PA…), y compris pour un ministre absent de depute.
    acteur_id: Mapped[str | None]
    depute_id: Mapped[str | None] = mapped_column(ForeignKey("depute.id"), index=True)
    orateur_libelle: Mapped[str]
    qualite: Mapped[str]
    groupe_id: Mapped[str | None] = mapped_column(ForeignKey("groupe.id"), index=True)
    texte: Mapped[str]
    nb_mots: Mapped[int | None]
    recherche: Mapped[str] = mapped_column(
        TSVECTOR, Computed(f"to_tsvector('{CONFIG_RECHERCHE}', texte)", persisted=True)
    )


# --- Votes -------------------------------------------------------------------


class Scrutin(Horodatage, Base):
    __tablename__ = "scrutin"
    __table_args__ = (
        valeurs_autorisees("type", TYPES_SCRUTIN),
        valeurs_autorisees("resultat", RESULTATS_SCRUTIN),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # VTANR…
    seance_id: Mapped[str | None] = mapped_column(ForeignKey("seance.id"), index=True)
    dossier_id: Mapped[str | None] = mapped_column(ForeignKey("dossier.id"), index=True)
    numero: Mapped[int | None]
    date: Mapped[date | None]
    objet: Mapped[str]
    type: Mapped[str]
    resultat: Mapped[str]
    pour: Mapped[int]
    contre: Mapped[int]
    abstentions: Mapped[int]
    non_votants: Mapped[int]


class Vote(Horodatage, Base):
    __tablename__ = "vote"
    __table_args__ = (valeurs_autorisees("position", POSITIONS_VOTE),)

    scrutin_id: Mapped[str] = mapped_column(ForeignKey("scrutin.id"), primary_key=True)
    depute_id: Mapped[str] = mapped_column(ForeignKey("depute.id"), primary_key=True)
    groupe_id: Mapped[str | None] = mapped_column(ForeignKey("groupe.id"), index=True)
    position: Mapped[str]
    par_delegation: Mapped[bool] = mapped_column(server_default="false")


# --- Sorties IA (versionnées, jamais écrasées : ADR-007) ----------------------


class Fiche(Base):
    __tablename__ = "fiche"
    __table_args__ = (
        UniqueConstraint("dossier_id", "version"),
        valeurs_autorisees("statut", STATUTS_FICHE),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    dossier_id: Mapped[str] = mapped_column(ForeignKey("dossier.id"))
    version: Mapped[int]
    synthese: Mapped[str | None]
    # Listes de points (T2) : chaque point cite les groupes concernés.
    accords: Mapped[list | None] = mapped_column(JSONB)
    desaccords: Mapped[list | None] = mapped_column(JSONB)
    modele: Mapped[str]
    prompt_version: Mapped[str]
    genere_le: Mapped[datetime] = mapped_column(server_default=func.now())
    statut: Mapped[str]  # résultat des contrôles après génération


class PositionGroupe(Base):
    __tablename__ = "position_groupe"
    __table_args__ = (
        UniqueConstraint("fiche_id", "groupe_id"),
        valeurs_autorisees("position", POSITIONS_GROUPE),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fiche_id: Mapped[int] = mapped_column(ForeignKey("fiche.id"))
    groupe_id: Mapped[str] = mapped_column(ForeignKey("groupe.id"))
    position: Mapped[str]


class Argument(Base):
    __tablename__ = "argument"
    __table_args__ = (
        UniqueConstraint("position_id", "ordre"),
        CheckConstraint("ordre BETWEEN 1 AND 4", name="ordre"),  # 4 arguments maximum
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("position_groupe.id"))
    ordre: Mapped[int]
    texte: Mapped[str]


class Citation(Base):
    __tablename__ = "citation"
    __table_args__ = (
        CheckConstraint("score_confiance BETWEEN 0 AND 1", name="score_confiance"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    argument_id: Mapped[int] = mapped_column(ForeignKey("argument.id"), index=True)
    intervention_id: Mapped[int] = mapped_column(ForeignKey("intervention.id"), index=True)
    extrait: Mapped[str]
    verifiee: Mapped[bool]
    score_confiance: Mapped[Decimal | None]


# --- Exploitation et contenu --------------------------------------------------


class RunPipeline(Base):
    __tablename__ = "run_pipeline"
    __table_args__ = (valeurs_autorisees("statut", STATUTS_RUN),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    debut: Mapped[datetime] = mapped_column(server_default=func.now())
    fin: Mapped[datetime | None]
    statut: Mapped[str] = mapped_column(server_default="en_cours")
    erreurs: Mapped[list | None] = mapped_column(JSONB)
    nb_nouveaux: Mapped[int | None]


class Guide(Base):
    __tablename__ = "guide"

    slug: Mapped[str] = mapped_column(primary_key=True)
    titre: Mapped[str]
    contenu: Mapped[str]  # Markdown


class Terme(Base):
    __tablename__ = "terme"

    terme: Mapped[str] = mapped_column(primary_key=True)
    definition: Mapped[str]
    guide_slug: Mapped[str | None] = mapped_column(ForeignKey("guide.slug"))


# Tables dont maj_le est avancé automatiquement par trigger.
TABLES_HORODATEES = sorted(
    m.local_table.name for m in Base.registry.mappers if issubclass(m.class_, Horodatage)
)
