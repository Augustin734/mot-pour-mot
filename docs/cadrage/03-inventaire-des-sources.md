# Inventaire des sources

La V1 repose sur deux sources : l'open data de l'Assemblée nationale et Tricoteuses ; les autres arrivent avec les fonctionnalités V1.1 à V3.

| Source | Contenu utile | Format | Mise à jour | Licence | Version |
| --- | --- | --- | --- | --- | --- |
| [Open data de l'Assemblée nationale](https://data.assemblee-nationale.fr/) | Députés, organes (groupes, commissions), dossiers législatifs, scrutins et votes, amendements, réunions (agenda), comptes rendus, questions | XML, JSON (et CSV) | Régulière, non documentée pour les séances (voir vérification) | Licence Ouverte 2.0 | V1 |
| [Comptes rendus des débats AN (DILA)](https://www.data.gouv.fr/datasets/comptes-rendus-des-debats-de-l-assemblee-nationale) | Verbatim de la séance publique, publié au Journal officiel | XML + schéma XSD | Au fil des publications | Licence Ouverte 2.0 | V1 (secours) |
| [Tricoteuses](https://www.tricoteuses.fr/) | Textes des lois (absents de l'open data AN), comptes rendus de commission (V1.1), données temps réel : dérouleur de séance, suivi des amendements, scrutins | API Parlement, API PostgREST, dump PostgreSQL | Temps réel | ODbL 1.0 (données) | V1 |
| [Jeux de données Datan](https://www.data.gouv.fr/fr/organizations/datan/) | Statistiques des députés et groupes, historique depuis 2002 | Tableaux (data.gouv.fr) | Hebdomadaire | Licence Ouverte | V1.1 (contrôle croisé des KPI) |
| [Répertoire HATVP](https://www.data.gouv.fr/datasets/donnees-du-repertoire-des-representants-dinterets-au-format-json/) | Actions de lobbying déclarées (année en cours et 5 précédentes) | JSON + documentation XLSX | Quotidienne | Licence Ouverte | V2 |
| Pétitions de l'Assemblée | Pétitions citoyennes et leur suivi | À vérifier | À vérifier | À vérifier | V2 |
| Flux RSS de médias | Titres et liens d'articles | RSS | Continue | Droit d'auteur : titres et liens seulement | V2 |
| [Open data du Sénat](https://www.data.gouv.fr/organizations/senat) | Sénateurs, travaux législatifs (Dosleg), amendements, comptes rendus depuis 2003 | Dump PostgreSQL | Quotidienne | À vérifier par jeu de données | V2 |
| Parlement européen | Votes nominatifs, délégations françaises | À vérifier | À vérifier | À vérifier | V3 |

## Points d'attention

- **Les textes de loi ne sont pas dans l'open data AN** : Tricoteuses les fournit ; sans eux, pas de « ce que ça change ».
- **La liaison séance ↔ dossier législatif** passe par le numéro du texte discuté (attribut bibard), présent sur chaque paragraphe du compte rendu ; vérifié le 29 octobre, à fiabiliser au jalon 2.
- **Comptes rendus de commission** : HTML et PDF seulement, donc reportés en V1.1 avec un découpage dédié.
- **Une seule source de vérité par donnée** : l'open data AN fait foi ; Tricoteuses complète, Datan sert de contrôle.
- **Attribution** : chaque fiche cite ses sources et leur licence (Licence Ouverte pour l'AN, ODbL pour Tricoteuses).

## À vérifier avant le jalon 2

- [x] Fréquence réelle de mise à jour : non documentée pour les séances (export daté du 21 octobre lors de la vérification du 29), à la minute pour les amendements
- [x] Licence Tricoteuses : ODbL 1.0 pour les données, AGPL-3.0 pour le code
- [ ] Disponibilité et format des données de pétitions (V2, non bloquant)
- [x] Comptes rendus de commission : pas de XML, seulement HTML et PDF, un document par réunion

## Vérification des données (29 octobre 2026)

Le cœur de la V1 est faisable avec la séance publique : le XML de l'Assemblée découpe déjà chaque prise de parole, avec son orateur et le numéro du texte discuté. Les commissions coûtent plus cher et passent en V1.1. Vérifié sur l'échantillon officiel de 132 séances publié par l'Assemblée (14e législature).

| Question | Résultat | Conséquence |
| --- | --- | --- |
| Découper les séances en interventions | Oui. Le XML « Syceron » découpe chaque séance en points et en paragraphes ; chaque prise de parole porte l'identifiant de l'orateur (ID\_ACTEUR, ex. PA1874), son rang dans la séance et le type de débat (discussion générale, articles, questions au gouvernement…). | Pas d'IA nécessaire pour découper ; jalon 2 confirmé |
| Relier une séance à une loi | Oui : chaque paragraphe porte le numéro du texte discuté (attribut bibard, ex. « n° 3851 ») et le numéro du point de l'ordre du jour ; le numéro du texte se retrouve dans les dossiers législatifs. | Liaison par numéro de texte, après nettoyage du format « (n° 3851) » |
| Groupe de l'orateur à la date | Oui : l'identifiant renvoie au jeu « acteurs et organes », qui contient les mandats de groupe datés. | Appartenance historisée confirmée |
| Amendements et votes | Les paragraphes portent l'article et l'amendement discutés ; les résultats de vote sont inclus (pour, contre, votants). | Facilite « amendements clés » et les votes |
| Comptes rendus de commission | Pas de XML : HTML et PDF, un document par réunion, depuis la 15e législature. L'outil @tricoteuses/assemblee sait les récupérer. | Commissions en V1.1 ; la V1 commence par la séance publique |
| Fraîcheur | L'export des séances n'est pas daté du jour ; Tricoteuses fournit un suivi en temps réel. | AN comme référence, Tricoteuses pour la fraîcheur |
| Licence Tricoteuses | ODbL 1.0 : attribution et partage à l'identique des bases dérivées. | Une base publiée qui en dérive doit rester sous ODbL |

## Archives de la 17e législature (vérifié le 1er novembre 2026)

Téléchargées par `python -m pipeline.telechargement`, sous `https://data.assemblee-nationale.fr/static/openData/repository/17/`. Les cinq archives étaient datées du jour même : les séances sont donc désormais exportées quotidiennement, contrairement à la vérification du 29 octobre. Le serveur renvoie `ETag` et `Last-Modified` et répond 304 à une requête conditionnelle : le run de nuit ne retéléchargera que ce qui a changé. Attention : le site répond depuis plusieurs serveurs dont les copies d'une même archive portent des dates et des ETag différents (constaté sur les scrutins). Le pipeline envoie donc la date seule (`If-Modified-Since`) et compare le contenu reçu au cache (SHA-256).

| Archive | Chemin | Taille (zip / décompressé) | Contenu |
| --- | --- | --- | --- |
| Acteurs et organes | `amo/tous_acteurs_mandats_organes_xi_legislature/AMO30_…historique.json.zip` | 14 / 96 Mo | 3 175 acteurs (ministres compris), 10 819 organes, mandats datés |
| Dossiers législatifs | `loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip` | 11 / 39 Mo | 3 380 dossiers, 7 574 documents (le numéro du texte est dans `notice.numNotice`) |
| Scrutins | `loi/scrutins/Scrutins.json.zip` | 29 / 192 Mo | 9 459 scrutins, votes nominatifs ventilés par groupe, `seanceRef` vers la séance |
| Comptes rendus | `vp/syceronbrut/syseron.xml.zip` | 61 / 354 Mo | 650 comptes rendus de séance, un fichier XML par séance |

Constats utiles pour la suite du jalon 2 :

- **Le format réel des comptes rendus diffère de l'échantillon** : balises en camelCase dans un espace de noms (`compteRendu`, `metadonnees`, `point`, `paragraphe`, `interExtraction`), mais les mêmes attributs (`id_acteur`, `ordre_absolu_seance`, `code_grammaire`, `bibard`, `art`, `adt`, `valeur_ptsodj`). Chaque fichier porte ses vrais identifiants : `uid` (CRSANR…) et `seanceRef` (RUANR…, la clé partagée avec les scrutins). Un paragraphe porte aussi `stime`, sa position en secondes dans la vidéo, et le compte rendu une `version` (avant JO ou définitive).
- **Couleurs des groupes** : l'open data les fournit (`couleurAssociee`, ex. `#313567` pour le RN). L'ordre de l'hémicycle n'y est pas : `preseance` suit l'ordre protocolaire (taille des groupes). Il faut donc un petit fichier de référence pour l'ordre de gauche à droite.
- **Un changement de nom crée un nouvel organe** : À Droite (PO845520), puis UDR (PO847173), puis UDDPLR (PO872880) sont trois groupes successifs, chacun avec ses dates.

**Projet proche découvert** : [Open Hémicycle](https://github.com/kecyf/open-hemicycle) (AGPL), centré sur les votes et l'activité de chaque député, avec un indice de cohérence prévu. Il ne résume pas les positions par loi, mais son nom était très proche de notre nom provisoire « Hémicycle », d'où le choix de « Mot pour mot ».

Sources : [page Débats de l'open data AN](https://data.assemblee-nationale.fr/travaux-parlementaires/debats), [FAQ open data AN](https://data.assemblee-nationale.fr/foire-aux-questions), [échantillon officiel opendata\_snippets](https://github.com/Assemblee-nationale/opendata_snippets), [@tricoteuses/assemblee](https://npm.io/package/@tricoteuses/assemblee), [sources vérifiées, hackathon AN 2026](https://github.com/mdaoudi-de/hackathon-an-2026-vigie-marches/blob/main/hackathon-an-2026/docs/sources-verifiees.md).

Voir aussi : [ressources du hackathon AN 2026](https://hackathon2026.assemblee-nationale.fr/supports-conferences/EmmanuelRAVIART_presentation_des_ressources.pdf), pages data.gouv.fr liées dans le tableau.
