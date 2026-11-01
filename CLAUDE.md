# CLAUDE.md — Mot pour mot

Contexte du projet pour Claude Code. À lire avant toute tâche. Le cadrage complet est dans `docs/cadrage/` : en cas de doute, ces documents font foi, et ce fichier les résume.

## Le projet en bref

Appli web open source qui montre, loi par loi, ce que chaque groupe politique de l'Assemblée nationale en pense, avec des citations vérifiées mot pour mot, et qui permet de chercher « qui a dit quoi, quand » dans les débats.

- **Public** : citoyens curieux, militants, étudiants (personas : `docs/cadrage/01-personas.md`).
- **Contexte** : projet perso d'un data analyst (en alternance), aussi utilisé comme projet à présenter en entretien. Le code, les choix et la doc doivent donc être propres et explicables.
- **Langue** : tout en français (doc, commentaires, messages de commit, interface). Les noms dans le code (tables, variables, fonctions) sont en français sans accents, en snake_case : `intervention`, `numero_texte`.

## Décisions prises (ne pas remettre en cause sans demander)

| Sujet | Décision |
|---|---|
| Nom | « Mot pour mot », dépôt `mot-pour-mot` (1er nov. 2026) |
| Architecture | Appli avec serveur, tout tourne sur le PC Windows de l'auteur (ADR-001, ADR-005) |
| Base | PostgreSQL, plein texte en configuration française, puis pgvector en V1.1 (ADR-002) |
| Schéma | SQLAlchemy 2.0 + migrations Alembic, modèles partagés entre pipeline et API ; `texte` identifié par (legislature, numero) ; `cree_le` / `maj_le` sur les tables open data (1er nov. 2026) |
| API | FastAPI, lecture seule, préfixe `/api/v1` (ADR-003, spec : `08-specification-de-l-api.md`) |
| Front | React + Next.js, mobile d'abord (ADR-010) |
| Pipeline | Python, run de nuit lancé par le Planificateur de tâches Windows ; c'est le seul composant qui écrit en base |
| IA | Qwen3 1,7B ou 4B, fine-tuné en QLoRA (Unsloth sous WSL2) sur une RTX 3060 12 Go, servi par Ollama ou llama.cpp, hors Docker (ADR-004) |
| Déploiement | Docker Compose pour la base, l'API et le front (ADR-009) ; Cloudflare Tunnel pour ouvrir aux amis |
| Licence du code | AGPL-3.0 |
| Données | L'open data AN fait foi (Licence Ouverte 2.0). Tricoteuses complète (ODbL : une base dérivée publiée reste sous ODbL). Datan sert au contrôle. |
| Ordre des groupes | Toujours celui de l'hémicycle, de gauche à droite (`groupe.ordre_hemicycle`, tiré de `pipeline/reference/ordre_hemicycle.csv`) |
| Couleurs | Couleurs officielles de l'AN pour les groupes (`couleurAssociee` de l'open data, décidé le 1er nov. 2026) ; le reste de l'interface en noir sur fond cassé |
| Commissions | Les comptes rendus de commission (HTML/PDF seulement) sont reportés en V1.1 ; la V1 ne couvre que la séance publique |

## Principes non négociables

1. **Aucune citation sans vérification** : un extrait n'est publié que s'il existe mot pour mot (après normalisation des espaces et de la ponctuation) dans l'intervention liée (ADR-008).
2. **Neutralité** : l'appli ne juge jamais qui a raison et traite tous les groupes de la même façon (`11-charte-de-neutralite.md`).
3. **Les sorties IA sont versionnées** et jamais écrasées (ADR-007).
4. **Les identifiants AN sont conservés** comme clés (PA… pour un acteur, PO… pour un organe), ce qui rend la collecte idempotente.
5. **Rien n'est supprimé** : les corrections de l'open data mettent les lignes à jour.

## Données : ce qui a été vérifié (29 oct. 2026)

Vérifié sur l'échantillon officiel `Assemblee-nationale/opendata_snippets` (XML « Syceron » des comptes rendus de séance) :

- Chaque séance est découpée en points et en paragraphes. Chaque paragraphe porte :
  - `ID_ACTEUR` (ex. `PA1874`), l'orateur ;
  - `ordre_absolu_seance`, son rang dans la séance ;
  - `code_grammaire` et `code_parole`, le type de prise de parole ou de débat ;
  - `valeur_ptsODJ`, le point de l'ordre du jour ;
  - **`bibard`**, le numéro du texte discuté, au format « (n° 3851) » à nettoyer ;
  - `art` et `adt`, l'article et l'amendement discutés.
- Les métadonnées contiennent `DateSeance` et `Legislature`, et les résultats de vote (`ResultatVote`) sont inclus.
- **La liaison séance ↔ loi passe par le numéro du texte** (`bibard` → table `texte` → `dossier`), pas par Tricoteuses.
- Le groupe d'un orateur à une date se retrouve dans le jeu « acteurs et organes » (mandats datés) : il est stocké dans `appartenance`.
- La fréquence de mise à jour des séances n'est pas documentée (export daté de plusieurs jours) ; Tricoteuses sert pour la fraîcheur.
- Vu en écrivant le parseur (1er nov. 2026) : les paragraphes d'un orateur sont regroupés dans un `inter_extraction` qui porte sa qualité ; une interruption est un paragraphe à part, rangé dans le bloc de l'orateur interrompu ; plus de la moitié des paragraphes n'ont pas de `bibard` et héritent le numéro du texte de leur `Point` parent.

Vu sur les archives réelles de la 17e (1er nov. 2026, détail dans `03-inventaire-des-sources.md`) : le format des comptes rendus diffère de l'échantillon (camelCase, espace de noms, vrais identifiants CRSANR… et RUANR…), avec les mêmes attributs ; les exports sont quotidiens et le serveur gère les requêtes conditionnelles (ETag).

Le schéma cible est dans `docs/cadrage/05-dictionnaire-de-donnees.md`. Les noms y sont provisoires et doivent être fixés au jalon 1.

## Structure du dépôt (cible)

```
pipeline/  collecte, découpage, liaison, run de nuit
ml/        dataset, entraînement, évaluation, prompts (ml/prompts/t1_position_groupe.v1.md…)
api/       FastAPI, schémas, tests
web/       front Next.js
db/        schéma et migrations
docs/      dossier de cadrage, ADR, méthode
docker-compose.yml
```

## Où on en est

- Cadrage terminé et relu (19 documents dans `docs/cadrage/`). Wireframes mobiles validés (11 écrans, décrits dans `10-wireframes.md`). Les maquettes ordinateur sont obsolètes.
- **Prochaine étape : jalon 1, modèle de données.**
  - Schéma PostgreSQL et migrations Alembic : fait (`db/modeles.py`, migration `0001`, tests dans `tests/db/`, CI GitHub Actions).
  - `docker-compose.yml` avec PostgreSQL, et l'API (`/api/v1/statut`) et le front (Next.js 16, TypeScript) en squelette : fait.
  - Premier script de collecte sur l'échantillon Syceron : fait (`pipeline/syceron.py`, `pipeline/chargement.py`, `python -m pipeline.collecte_echantillon`). Sur les 132 séances : 56 764 interventions, 83,5 % avec un numéro de texte.
- **Jalon 2 en cours** (collecte de la 17e législature, code paramétré par législature). Découpage en PR : CI en Node 24 (#6, fait) ; rôle `lecture_seule` pour l'API (#7, fait, `db/utilisateur_api.py`) ; téléchargement des archives AN (#8, fait, `pipeline/telechargement.py`) ; acteurs et organes (`pipeline/acteurs_organes.py` : couleurs de l'open data, ordre de l'hémicycle dans un fichier de référence, `appartenance.qualite`) ; dossiers et textes ; comptes rendus réels de la 17e ; liaison orateur → groupe et point → dossier, avec bilan des non rattachés ; scrutins ; point d'entrée `python -m pipeline.collecte`.
- Ensuite : jalon 3 (API + recherche). Le détail est dans la section Jalons de `00-cahier-des-charges.md` et dans `15-backlog-priorise.md`.
- Questions encore ouvertes : nom de domaine, taille du modèle (1,7B ou 4B), machine dédiée ou non.

## Façon de travailler attendue

- Avancer par petites étapes vérifiables, avec des tests (pytest) pour les parseurs, l'API et le schéma.
- Expliquer brièvement les choix techniques non évidents : l'auteur doit pouvoir les défendre en entretien.
- Si une demande contredit le cadrage, le signaler et demander avant de changer une décision.
- Mettre à jour `docs/cadrage/` (et ce fichier) quand une décision change.

## Workflow Git (décidé le 1er nov. 2026)

```
feature/xxx ──PR──▶ develop ──PR (fin de jalon)──▶ main
```

- Les branches de travail partent de `develop` et sont préfixées : `feature/`, `fix/`, `docs/`.
- **Toute modification passe par une PR** : push direct, force-push et suppression interdits sur `main` et `develop` (rulesets GitHub).
- **Claude ouvre les PR mais ne les merge jamais** : l'auteur relit et merge lui-même. Aucune approbation n'est exigée par GitHub, car les PR sont ouvertes avec le compte de l'auteur, qui ne peut pas approuver les siennes.
- Merge en *squash* vers `develop` (un commit par fonctionnalité), en *merge commit* vers `main`.
- `develop` → `main` à chaque fin de jalon. Quand la CI existera, les tests devront passer avant tout merge.
