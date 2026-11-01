"""Lecture des comptes rendus de séance au format XML « Syceron » de l'Assemblée.

Deux variantes existent : l'échantillon officiel (<CompteRendu>, <inter_extraction>,
ID_ACTEUR…) et l'export réel de la 17e législature (<compteRendu> dans un espace de noms,
<interExtraction>, id_acteur…). Mêmes informations, noms écrits autrement : les noms sont
donc normalisés après lecture (voir normaliser), et la suite du module n'en connaît qu'une
forme.

Structure utile d'un <compterendu> (noms normalisés) :
- <seanceref> : identifiant AN de la séance (RUANR…), absent de l'échantillon ;
- <metadonnees> : dateseance, legislature, numseance… ;
- <contenu> : des <point> imbriqués (niveau 1 = point de l'ordre du jour, niveau 2 = phase
  du débat comme « Discussion générale »), qui contiennent des <interextraction> (bloc d'un
  orateur, avec sa qualité) puis des <paragraphe>.

Un <paragraphe> est une prise de parole d'un seul orateur : il devient une intervention.
Les interruptions sont des paragraphes à part (code_grammaire INTERRUPTION_…).

Ce module ne touche pas à la base : il transforme le XML en objets simples, testables seuls.
"""

import re
from collections import Counter
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


class CompteRenduInvalide(ValueError):
    """Compte rendu inutilisable en l'état (ex. version provisoire mal numérotée)."""


# --- Nettoyage des valeurs ----------------------------------------------------


def nettoyer_numero_texte(valeur: str | None, nombre_seul: bool = False) -> str | None:
    """« (n[[o]] 3851) » → « 3851 ». Avec plusieurs numéros (« nos 2044, 2061 »), le premier
    est le texte discuté (les suivants sont les rapports) : c'est lui qu'on garde.

    Dans l'attribut bibard de l'export réel, le numéro est aussi écrit seul (« 912 »,
    « 912 rectifié ») : nombre_seul=True l'accepte. Ailleurs (attribut valeur d'un point),
    un nombre seul désigne un article ou un amendement, pas un texte."""
    if not valeur:
        return None
    if "n[[" in valeur:
        # Le marqueur est parfois mal fermé (« n[[os] 1281 ») : on prend ce qui suit « n[[o… ».
        numeros = re.findall(r"\d+", re.split(r"n\[\[\w*[\] ]*", valeur, maxsplit=1)[1])
        return numeros[0] if numeros else None
    if nombre_seul and (m := re.match(r"\s*(\d+)\b", valeur)):
        return m.group(1)
    return None


def normaliser(racine: ET.Element) -> ET.Element:
    """Ramène les deux variantes du format à une seule forme, en place : balises sans espace
    de noms, en minuscules et sans « _ » (inter_extraction et interExtraction deviennent
    interextraction) ; attributs en minuscules (ID_ACTEUR → id_acteur)."""
    for el in racine.iter():
        el.tag = el.tag.rsplit("}", 1)[-1].lower().replace("_", "")
        if any(cle != cle.lower() for cle in el.attrib):
            el.attrib = {cle.lower(): valeur for cle, valeur in el.attrib.items()}
    return racine


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
    """Métadonnée par nom normalisé (dateseance, legislature…)."""
    return metadonnees.findtext(nom)


def _entier(valeur: str | None) -> int | None:
    return int(valeur) if valeur and valeur.lstrip("-").isdigit() else None


def _vide_en_none(valeur: str | None) -> str | None:
    valeur = (valeur or "").strip()
    return valeur or None


def lire_compte_rendu(compte_rendu: ET.Element) -> SeanceLue:
    """Lit un <compterendu> dont les noms ont été normalisés (voir normaliser)."""
    metadonnees = compte_rendu.find("metadonnees")
    legislature = int(_meta(metadonnees, "legislature"))
    debut = date_seance(_meta(metadonnees, "dateseance"))
    identifiant = _vide_en_none(compte_rendu.findtext("seanceref"))
    seance = SeanceLue(
        id=identifiant or identifiant_seance_echantillon(legislature, debut),
        legislature=legislature,
        debut=debut,
    )
    points: dict[int, PointLu] = {}

    def parcourir(el: ET.Element, pile_points: list[ET.Element], bloc: ET.Element | None) -> None:
        for enfant in el:
            if enfant.tag == "point":
                if enfant.get("nivpoint") == "1":
                    _ajouter_point(seance, points, enfant)
                parcourir(enfant, pile_points + [enfant], bloc)
            elif enfant.tag == "interextraction":
                parcourir(enfant, pile_points, enfant)
            elif enfant.tag == "paragraphe":
                intervention = _lire_paragraphe(seance, points, enfant, pile_points, bloc)
                if intervention:
                    seance.interventions.append(intervention)
            # Blocs hors point (ouverture, fin, changement de présidence) : ils contiennent
            # aussi des paragraphes (« La séance est reprise. »).
            elif enfant.tag in ("ouvertureseance", "finseance", "changementpresidence"):
                parcourir(enfant, pile_points, bloc)

    parcourir(compte_rendu.find("contenu"), [], None)
    # ordre_absolu_seance est la clé d'une intervention : des doublons rendraient le
    # rechargement ambigu. Vu sur des versions provisoires (avant JO) de l'export réel.
    ordres = [i.ordre for i in seance.interventions]
    if len(ordres) != len(set(ordres)):
        raise CompteRenduInvalide(
            f"{seance.id} : {len(ordres) - len(set(ordres))} rangs (ordre_absolu_seance) en double"
        )
    _propager_numeros(seance)
    return seance


def _propager_numeros(seance: SeanceLue) -> None:
    """Donne le numéro du texte aux interventions d'un point de l'ordre du jour qui n'en ont pas.

    Dans l'export réel, seuls quelques paragraphes portent le numéro (bibard), souvent ceux
    de la discussion des articles ; la discussion générale du même point n'en a pas. Le
    numéro le plus fréquent du point leur est donné. Quand deux textes sont discutés
    ensemble, un paragraphe garde le sien : seul celui qui n'en a pas reçoit le plus fréquent.
    """
    par_point: dict[str, list[InterventionLue]] = {}
    for intervention in seance.interventions:
        if intervention.point_id:
            par_point.setdefault(intervention.point_id, []).append(intervention)
    for point in seance.points:
        interventions = par_point.get(point.id, [])
        numeros = Counter(i.numero_texte for i in interventions if i.numero_texte)
        if not numeros:
            continue
        # À égalité, le premier numéro rencontré l'emporte (most_common garde l'ordre).
        majoritaire = numeros.most_common(1)[0][0]
        point.numero_texte = point.numero_texte or majoritaire
        for intervention in interventions:
            intervention.numero_texte = intervention.numero_texte or majoritaire


def _ajouter_point(seance: SeanceLue, points: dict[int, PointLu], el: ET.Element) -> None:
    numero = _entier(el.get("valeur_ptsodj"))
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
    orateur = el.find("orateurs/orateur")
    texte = texte_brut(el.find("texte"))
    ordre = _entier(el.get("ordre_absolu_seance"))
    # Sans orateur (didascalie seule, ex. « (La séance est ouverte.) ») : pas une intervention.
    if orateur is None or not texte or ordre is None:
        return None

    nom = (orateur.findtext("nom") or "").replace("\xa0", " ").strip()
    acteur_id = _vide_en_none(el.get("id_acteur")) or _vide_en_none(orateur.findtext("id"))
    qualite_brute = orateur.findtext("qualite") or ""
    # Une interruption est rangée dans le bloc de l'orateur interrompu : la qualité du bloc
    # n'est donc reprise que si le bloc appartient bien à l'orateur du paragraphe.
    if not qualite_brute and bloc is not None and bloc.get("id_acteur") == acteur_id:
        qualite_brute = bloc.get("qualite", "")
    point = points.get(_entier(el.get("valeur_ptsodj")))

    # Le numéro du texte est sur le paragraphe (bibard) ou, à défaut, hérité du Point parent.
    numero_texte = nettoyer_numero_texte(el.get("bibard"), nombre_seul=True)
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
        qualite=qualite_orateur(nom, qualite_brute, el.get("roledebat")),
        texte=texte,
    )


def _type_debat(pile_points: list[ET.Element]) -> str | None:
    """Phase du débat : titre du Point de niveau 2 (« Discussion générale »…). À défaut, le
    titre du niveau 1 s'il ne porte pas de numéro de texte (« Questions au Gouvernement »)."""
    for niveau in ("2", "1"):
        for p in pile_points:
            if p.get("nivpoint") != niveau:
                continue
            # « Discussion des articles (suite) » est la même phase que « Discussion des articles ».
            titre = re.sub(r"\s*\(suite\)$", "", texte_brut(p.find("texte")))
            if titre and (niveau == "2" or not nettoyer_numero_texte(p.get("valeur"))):
                return titre
    return None


def lire_racine(racine: ET.Element) -> Iterator[SeanceLue]:
    """Lit les comptes rendus d'un document : <syceronBrut> (l'échantillon, plusieurs
    comptes rendus) ou <compteRendu> seul (export réel, un fichier par séance)."""
    for compte_rendu in normaliser(racine).iter("compterendu"):
        yield lire_compte_rendu(compte_rendu)


def lire_fichier(chemin: Path) -> Iterator[SeanceLue]:
    yield from lire_racine(ET.parse(chemin).getroot())


def lire_xml(contenu: bytes) -> Iterator[SeanceLue]:
    yield from lire_racine(ET.fromstring(contenu))
