"""Lecture des comptes rendus de séance au format XML « Syceron » de l'Assemblée.

Structure utile d'un <CompteRendu> :
- <Metadonnees> : DateSeance, Legislature, NumSeance… (balises parfois en minuscules) ;
- <Contenu> : des <Point> imbriqués (niveau 1 = point de l'ordre du jour, niveau 2 = phase
  du débat comme « Discussion générale »), qui contiennent des <inter_extraction> (bloc d'un
  orateur, avec sa qualité) puis des <paragraphe>.

Un <paragraphe> est une prise de parole d'un seul orateur : il devient une intervention.
Les interruptions sont des paragraphes à part (code_grammaire INTERRUPTION_…).

Ce module ne touche pas à la base : il transforme le XML en objets simples, testables seuls.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FUSEAU_AN = ZoneInfo("Europe/Paris")

# Préfixe des identifiants de séance construits pour l'échantillon, qui n'en a pas :
# il les distingue sans ambiguïté des identifiants officiels de l'AN.
PREFIXE_ECHANTILLON = "ECH"


@dataclass
class PointLu:
    id: str
    numero: int
    titre: str
    numero_texte: str | None


@dataclass
class InterventionLue:
    ordre: int
    point_id: str | None
    type_debat: str | None
    code_grammaire: str | None
    numero_texte: str | None
    article: str | None
    amendement: str | None
    acteur_id: str | None
    orateur_libelle: str
    qualite: str
    texte: str

    @property
    def nb_mots(self) -> int:
        return len(self.texte.split())


@dataclass
class SeanceLue:
    id: str
    legislature: int
    debut: datetime
    points: list[PointLu] = field(default_factory=list)
    interventions: list[InterventionLue] = field(default_factory=list)


# --- Nettoyage des valeurs ----------------------------------------------------


def nettoyer_numero_texte(valeur: str | None) -> str | None:
    """« (n[[o]] 3851) » → « 3851 ». Avec plusieurs numéros (« nos 2044, 2061 »), le premier
    est le texte discuté (les suivants sont les rapports) : c'est lui qu'on garde."""
    if not valeur or "n[[" not in valeur:
        return None
    numeros = re.findall(r"\d+", valeur.split("]]", 1)[1])
    return numeros[0] if numeros else None


def texte_brut(element: ET.Element | None) -> str:
    """Texte d'un élément <texte>, avec les <br/> en retours à la ligne.

    Les didascalies en italique (« (Applaudissements…) ») sont gardées : le texte reste
    celui du compte rendu, condition de la vérification mot pour mot des citations."""
    if element is None:
        return ""
    morceaux: list[str] = []

    def parcourir(el: ET.Element) -> None:
        morceaux.append(el.text or "")
        for enfant in el:
            if enfant.tag == "br":
                morceaux.append("\n")
            else:
                parcourir(enfant)
            morceaux.append(enfant.tail or "")

    parcourir(element)
    lignes = (ligne.strip() for ligne in "".join(morceaux).split("\n"))
    return "\n".join(ligne for ligne in lignes if ligne)


def qualite_orateur(nom: str, qualite_brute: str, role_debat: str | None) -> str:
    """Ramène la qualité libre du compte rendu aux valeurs du schéma."""
    if role_debat == "president" or re.match(r"(M\.|Mme)\s+(le|la) président", nom):
        return "president"
    q = qualite_brute.lower()
    if "ministre" in q or "secrétaire d’état" in q or "secrétaire d'état" in q:
        return "ministre"
    if "rapporte" in q:  # rapporteur, rapporteure
        return "rapporteur"
    return "depute"


def date_seance(valeur: str) -> datetime:
    """« 20140630160000000 » (heure de Paris) → datetime avec fuseau."""
    return datetime.strptime(valeur[:14], "%Y%m%d%H%M%S").replace(tzinfo=FUSEAU_AN)


def identifiant_seance_echantillon(legislature: int, debut: datetime) -> str:
    """L'échantillon n'a pas d'identifiant de séance : on le construit avec la date et l'heure
    de début, uniques et toujours présentes (les libellés de session, eux, sont irréguliers)."""
    return f"{PREFIXE_ECHANTILLON}-L{legislature}-{debut:%Y%m%d%H%M}"


# --- Lecture -----------------------------------------------------------------


def _meta(metadonnees: ET.Element, nom: str) -> str | None:
    """Métadonnée par nom, sans tenir compte de la casse (DateSeance ou dateSeance)."""
    for enfant in metadonnees:
        if enfant.tag.lower() == nom.lower():
            return enfant.text
    return None


def _entier(valeur: str | None) -> int | None:
    return int(valeur) if valeur and valeur.lstrip("-").isdigit() else None


def _vide_en_none(valeur: str | None) -> str | None:
    valeur = (valeur or "").strip()
    return valeur or None


def lire_compte_rendu(compte_rendu: ET.Element) -> SeanceLue:
    metadonnees = compte_rendu.find("Metadonnees")
    legislature = int(_meta(metadonnees, "Legislature"))
    debut = date_seance(_meta(metadonnees, "DateSeance"))
    seance = SeanceLue(
        id=identifiant_seance_echantillon(legislature, debut), legislature=legislature, debut=debut
    )
    points: dict[int, PointLu] = {}

    def parcourir(el: ET.Element, pile_points: list[ET.Element], bloc: ET.Element | None) -> None:
        for enfant in el:
            if enfant.tag == "Point":
                if enfant.get("nivPoint") == "1":
                    _ajouter_point(seance, points, enfant)
                parcourir(enfant, pile_points + [enfant], bloc)
            elif enfant.tag == "inter_extraction":
                parcourir(enfant, pile_points, enfant)
            elif enfant.tag == "paragraphe":
                intervention = _lire_paragraphe(seance, points, enfant, pile_points, bloc)
                if intervention:
                    seance.interventions.append(intervention)
            elif enfant.tag in ("ouverture_seance", "fin_seance"):
                parcourir(enfant, pile_points, bloc)

    parcourir(compte_rendu.find("Contenu"), [], None)
    return seance


def _ajouter_point(seance: SeanceLue, points: dict[int, PointLu], el: ET.Element) -> None:
    numero = _entier(el.get("valeur_ptsODJ"))
    if numero is None or numero in points:
        return
    points[numero] = PointLu(
        id=f"{seance.id}-P{numero}",
        numero=numero,
        titre=texte_brut(el.find("texte")),
        numero_texte=nettoyer_numero_texte(el.get("valeur")),
    )
    seance.points.append(points[numero])


def _lire_paragraphe(
    seance: SeanceLue,
    points: dict[int, PointLu],
    el: ET.Element,
    pile_points: list[ET.Element],
    bloc: ET.Element | None,
) -> InterventionLue | None:
    orateur = el.find("ORATEURS/ORATEUR")
    texte = texte_brut(el.find("texte"))
    ordre = _entier(el.get("ordre_absolu_seance"))
    # Sans orateur (didascalie seule, ex. « (La séance est ouverte.) ») : pas une intervention.
    if orateur is None or not texte or ordre is None:
        return None

    nom = (orateur.findtext("NOM") or "").replace("\xa0", " ").strip()
    acteur_id = _vide_en_none(el.get("ID_ACTEUR")) or _vide_en_none(orateur.findtext("ID"))
    qualite_brute = orateur.findtext("QUALITE") or ""
    # Une interruption est rangée dans le bloc de l'orateur interrompu : la qualité du bloc
    # n'est donc reprise que si le bloc appartient bien à l'orateur du paragraphe.
    if not qualite_brute and bloc is not None and bloc.get("id_acteur") == acteur_id:
        qualite_brute = bloc.get("QUALITE", "")
    point = points.get(_entier(el.get("valeur_ptsODJ")))

    # Le numéro du texte est sur le paragraphe (bibard) ou, à défaut, hérité du Point parent.
    numero_texte = nettoyer_numero_texte(el.get("bibard"))
    for p in reversed(pile_points):
        if numero_texte:
            break
        numero_texte = nettoyer_numero_texte(p.get("valeur"))

    return InterventionLue(
        ordre=ordre,
        point_id=point.id if point else None,
        type_debat=_type_debat(pile_points),
        code_grammaire=_vide_en_none(el.get("code_grammaire")),
        numero_texte=numero_texte,
        article=_vide_en_none(el.get("art")),
        amendement=_vide_en_none(el.get("adt")),
        acteur_id=acteur_id,
        orateur_libelle=nom or "Orateur non identifié",
        qualite=qualite_orateur(nom, qualite_brute, el.get("roleDebat")),
        texte=texte,
    )


def _type_debat(pile_points: list[ET.Element]) -> str | None:
    """Phase du débat : titre du Point de niveau 2 (« Discussion générale »…). À défaut, le
    titre du niveau 1 s'il ne porte pas de numéro de texte (« Questions au Gouvernement »)."""
    for niveau in ("2", "1"):
        for p in pile_points:
            if p.get("nivPoint") != niveau:
                continue
            # « Discussion des articles (suite) » est la même phase que « Discussion des articles ».
            titre = re.sub(r"\s*\(suite\)$", "", texte_brut(p.find("texte")))
            if titre and (niveau == "2" or not nettoyer_numero_texte(p.get("valeur"))):
                return titre
    return None


def lire_fichier(chemin: Path) -> Iterator[SeanceLue]:
    """Lit un fichier <syceronBrut> contenant un ou plusieurs comptes rendus."""
    racine = ET.parse(chemin).getroot()
    for compte_rendu in racine.iter("CompteRendu"):
        yield lire_compte_rendu(compte_rendu)
