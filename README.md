# Mot pour mot

Comprendre en 2 minutes ce que chaque groupe politique pense d'une loi,
et retrouver qui a dit quoi pendant les débats de l'Assemblée nationale.

> Projet indépendant, sans lien avec l'Assemblée nationale.
> Les résumés sont générés par IA ; chaque argument est appuyé par une citation
> vérifiée et un lien vers le compte rendu officiel.

## Fonctionnalités

- **Actu** : l'agenda de la semaine, les lois en cours et récemment débattues
- **Chercher** : une loi, ou un propos dans les débats (qui, quand, où)
- **Fiche loi** : synthèse, positions par groupe avec citations, débats séance par séance, votes
- **Chiffres** : composition de l'hémicycle et participation aux scrutins
- **Comprendre l'AN** : guides courts et glossaire

[Captures d'écran à venir]

## Stack

Python (pipeline, FastAPI) · PostgreSQL + pgvector · React (Next.js) ·
Qwen3 fine-tuné en local (QLoRA) · Docker Compose

## Installation

    git clone https://github.com/Augustin734/mot-pour-mot.git
    cd mot-pour-mot
    cp .env.example .env          # puis changer le mot de passe
    docker compose up -d          # base (API et front à venir)
    uv sync                       # dépendances Python (https://docs.astral.sh/uv/)
    uv run alembic upgrade head   # création du schéma
    uv run pytest                 # tests
    python -m pipeline.init       # premier chargement de la législature (à venir)

L'appli est disponible sur http://localhost:[port].
Le modèle local est optionnel : sans lui, la recherche et les fiches sans résumé fonctionnent.

## Structure

    pipeline/  collecte, découpage, liaison, run de nuit
    ml/        dataset, entraînement, évaluation, prompts
    api/       FastAPI
    web/       front
    db/        schéma et migrations
    docs/      dossier de cadrage, ADR, méthode

## Méthode et neutralité

La charte de neutralité, le protocole d'évaluation et les résultats du modèle
sont dans [docs/cadrage/](docs/cadrage/). Une erreur ? Ouvrez une issue avec le lien de la fiche.

## Sources

Données : Assemblée nationale (Licence Ouverte 2.0), Tricoteuses (ODbL), Datan (Licence Ouverte).
Merci à Regards Citoyens, Datan et Tricoteuses pour leur travail sur l'open data parlementaire.

## Licence

Code : AGPL-3.0 · Résumés : Licence Ouverte 2.0 (ODbL s'ils dérivent de Tricoteuses) · Modèle : Apache 2.0
