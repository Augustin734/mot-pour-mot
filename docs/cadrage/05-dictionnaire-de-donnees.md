# Dictionnaire de données

Les champs des tables V1, avec leur type PostgreSQL et leur source. Les noms sont fixés depuis le jalon 1 : le schéma de référence est `db/modeles.py`, et ce document en donne le sens.

**Conventions du schéma** (jalon 1) : tout le texte est en `text` et toutes les dates-heures en `timestamptz`. Les valeurs fermées (types, statuts, positions) sont du texte en snake\_case sans accents, contrôlé par une contrainte CHECK plutôt qu'un ENUM PostgreSQL, plus simple à faire évoluer par migration : par exemple `en_cours`, `pas_exprime`, `seance_publique`. La recherche plein texte utilise une configuration `francais`, qui ajoute à `french` l'oubli des accents (extension unaccent).

**Champs communs** (décidé le 1er novembre 2026) : chaque table alimentée par l'open data porte aussi `cree_le` et `maj_le` (timestamptz), la date de première insertion et celle de la dernière mise à jour. Rien n'est supprimé : une correction de l'open data met la ligne à jour et avance `maj_le`.

## legislature

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| numero | int, clé | Open data AN | Numéro de la législature (ex. 17) |
| debut | date | Open data AN | Date de début |
| fin | date, nullable | Open data AN | Date de fin ; vide pour la législature en cours |

## dossier

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| id | text, clé | Open data AN | Identifiant du dossier législatif |
| legislature | int | Open data AN | Numéro de législature |
| titre\_officiel | text | Open data AN | Titre complet |
| titre\_court | text | Calculé ou IA | Titre en langage clair pour les cartes |
| alias | text\[\] | Saisie, IA | Noms médiatiques (ex. nom du ministre) pour la recherche |
| type | enum | Open data AN | Projet ou proposition de loi |
| statut | enum | Calculé | En cours, adopté, rejeté, retiré |
| date\_depot | date | Open data AN | Date de dépôt |
| date\_derniere\_activite | timestamptz | Calculé | Dernière séance, scrutin ou étape |
| score\_importance | numeric | Calculé | Tri de l'écran Actu |
| themes | text\[\] | IA | Thèmes classifiés |
| recherche | tsvector | Calculé | Index plein texte (titre, alias) |

## etape

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| id | text, clé | Open data AN | Identifiant de l'acte législatif |
| dossier\_id | text | Open data AN | Dossier concerné |
| type | enum | Open data AN | Dépôt, commission, séance, CMP, lecture définitive, promulgation |
| chambre | enum | Open data AN | AN ou Sénat |
| date | date | Open data AN | Date de l'étape |

## seance

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| id | text, clé | Open data AN | Identifiant de la réunion. L'échantillon Syceron n'en a pas : il est construit à partir de la date et de l'heure de début, avec le préfixe `ECH` (ex. `ECH-L14-201406301600`) |
| legislature | int | Comptes rendus | Champ `Legislature` des métadonnées ; sert à retrouver le texte discuté |
| type | enum | Open data AN | Séance publique (réunion de commission à partir de la V1.1) |
| organe\_id | text | Open data AN | Commission, ou hall pour la séance publique |
| debut | timestamptz | Open data AN | Date et heure de début |
| url\_compte\_rendu | text | Open data AN | Lien vers le compte rendu officiel |
| url\_video | text | Open data AN | Lien vidéo, si disponible |

## point\_odj

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| id | text, clé | Open data AN | Identifiant du point |
| seance\_id | text | Open data AN | Séance |
| numero | int, nullable | Comptes rendus | Rang dans l'ordre du jour (`valeur_ptsODJ`) |
| dossier\_id | text, nullable | Calculé (numéro du texte) | Loi discutée, retrouvée via la table texte ; vide si non rattachée |
| titre | text | Open data AN | Intitulé du point |

## texte

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| legislature | int, clé (1/2) | Open data AN | L'AN renumérote ses textes à chaque législature |
| numero | text, clé (2/2) | Open data AN | Numéro du texte (ex. 3851), forme nettoyée de l'attribut bibard |
| dossier\_id | text | Open data AN | Dossier législatif auquel appartient le texte |
| type | enum | Open data AN | Texte déposé, texte de commission, texte adopté |

La clé est le couple (legislature, numero) : le « n° 3851 » de la 14e législature et celui de la 16e sont deux textes différents (décidé le 1er novembre 2026). Une intervention retrouve son texte avec `numero_texte` et la législature de sa séance. Ce lien n'est pas une clé étrangère stricte : une séance peut être chargée avant son texte, ou porter un numéro mal formé, et l'intervention est alors journalisée comme non rattachée au lieu de faire échouer la collecte.

## intervention

| Champ | Type | Source | Description |
| --- | --- | --- | --- |
| id | bigint, clé | Généré | Identifiant interne |
| seance\_id | text | Comptes rendus | Séance |
| point\_id | text, nullable | Comptes rendus | Point de l'ordre du jour |
| ordre | int | Comptes rendus | Rang dans la séance |
| type\_debat | text | Comptes rendus | Discussion générale, articles, questions au gouvernement… (titre du Point de niveau 2, sans « (suite) ») |
| code\_grammaire | text, nullable | Comptes rendus | Type brut de prise de parole (ex. `INTERRUPTION_1_10`), pour distinguer discours et interruptions |
| numero\_texte | text, nullable | Comptes rendus | Texte discuté (attribut bibard nettoyé) ; clé de la liaison avec la loi |
| article, amendement | text, nullable | Comptes rendus | Article et amendement discutés, quand le compte rendu les indique |
| acteur\_id | text, nullable | Comptes rendus | Identifiant brut de l'orateur (`ID_ACTEUR`, PA…), conservé même pour un ministre absent de la table depute |
| depute\_id | text, nullable | Comptes rendus | Vide pour un ministre ou le président |
| orateur\_libelle | text | Comptes rendus | Nom affiché |
| qualite | enum | Comptes rendus | Député, ministre, rapporteur, président, autre |
| groupe\_id | text, nullable | Calculé | Groupe à la date de l'intervention |
| texte | text | Comptes rendus | Propos intégral |
| nb\_mots | int | Calculé | Pour le temps de parole |
| recherche | tsvector | Calculé | Index plein texte, configuration française |

Le couple (seance\_id, ordre) est unique : c'est la clé naturelle qui rend le rechargement d'une séance idempotent.

## groupe, depute, appartenance

| Table | Champ | Type | Description |
| --- | --- | --- | --- |
| groupe | id | text, clé | Identifiant d'organe AN |
| groupe | sigle, nom | text | Ex. sigle court et nom complet |
| groupe | couleur | text | Couleur traditionnelle du parti, fixée par la charte graphique |
| groupe | legislature | int | Législature du groupe |
| depute | id | text, clé | Identifiant d'acteur AN |
| depute | nom, prenom | text | Identité |
| depute | circonscription | text | Département et numéro |
| appartenance | id | text, clé | Identifiant AN du mandat de groupe (PM…) |
| appartenance | depute\_id, groupe\_id | text | Lien député ↔ groupe |
| appartenance | debut, fin | date | Période d'appartenance ; fin vide si en cours |

## scrutin et vote

| Table | Champ | Type | Description |
| --- | --- | --- | --- |
| scrutin | id | text, clé | Identifiant AN du scrutin |
| scrutin | seance\_id, dossier\_id | text | Séance et loi liées (loi parfois vide) |
| scrutin | numero, date | int, date | Numéro du scrutin dans la législature et date du vote |
| scrutin | objet | text | Ce qui est voté |
| scrutin | type | enum | Ordinaire, solennel, motion |
| scrutin | resultat | enum | Adopté ou rejeté |
| scrutin | pour, contre, abstentions, non\_votants | int | Décompte |
| vote | scrutin\_id, depute\_id | text | Clé composée |
| vote | groupe\_id | text | Groupe à la date du vote |
| vote | position | enum | Pour, contre, abstention, non-votant |
| vote | par\_delegation | bool | Vote par délégation |

## Sorties IA

| Table | Champ | Type | Description |
| --- | --- | --- | --- |
| fiche | id | bigint, clé | Identifiant interne |
| fiche | dossier\_id, version | text, int | Une version par régénération |
| fiche | synthese | text | Synthèse globale |
| fiche | accords, desaccords | jsonb | Listes de 3 points maximum, chacun avec les groupes concernés (T2) |
| fiche | modele, prompt\_version, genere\_le | text, text, timestamptz | Traçabilité |
| fiche | statut | enum | Résultat des contrôles : publiée, à relire, rejetée |
| position\_groupe | fiche\_id, groupe\_id, position | bigint, text, enum | Pour, contre, divisé, pas exprimé |
| argument | position\_id, ordre, texte | bigint, int, text | 2 à 4 par groupe |
| citation | argument\_id, intervention\_id | bigint | Lien vers le propos source |
| citation | extrait | text | Extrait cité |
| citation | verifiee, score\_confiance | bool, numeric | Résultat de la vérification |

## Exploitation et contenu

| Table | Champ | Type | Description |
| --- | --- | --- | --- |
| run\_pipeline | id, debut, fin | bigint, timestamptz | Exécution de nuit |
| run\_pipeline | statut, erreurs, nb\_nouveaux | enum, jsonb, int | Résultat |
| guide | slug, titre, contenu | text | Guide « Comprendre l'AN » en Markdown |
| terme | terme, definition, guide\_slug | text | Glossaire lié aux guides |
