# Analyse des licences

Aucune licence n'empêche le projet : les données publiques sont sous Licence Ouverte 2.0 (attribution obligatoire), Qwen3 est sous Apache 2.0, et les données Tricoteuses sont sous ODbL (partage à l'identique des bases dérivées).

## Ce que le projet utilise

| Élément | Licence | Obligation principale | Statut |
| --- | --- | --- | --- |
| Open data AN, DILA, HATVP | [Licence Ouverte 2.0](https://www.data.gouv.fr/pages/legal/licences/etalab-2.0) | Citer la source et la date de mise à jour ; ne pas suggérer d'aval officiel | Compatible |
| Jeux de données Datan | Licence Ouverte (data.gouv.fr) | Citer la source | Compatible |
| Tricoteuses (API, base) | ODbL 1.0 (données), AGPL-3.0 (code) | Créditer Tricoteuses ; une base dérivée publiée reste sous ODbL | Compatible, sous conditions ODbL |
| Qwen3 (1,7B, 4B, 30B-A3B) | [Apache 2.0](https://www.interconnects.ai/p/qwen-3-the-new-open-standard) | Conserver la licence et les mentions ; signaler les modifications | Compatible |
| Flux RSS de presse | Droit d'auteur | Titres et liens seulement, pas de reprise d'article | Compatible si respecté |
| Dépendances de code (FastAPI, PostgreSQL, pgvector, llama.cpp, Ollama, Unsloth) | Licences permissives (MIT, Apache 2.0, PostgreSQL) | Conserver les mentions | À vérifier à l'ajout de chaque dépendance |

## Points clés

- **Attribution des données** : chaque fiche affiche « Source : Assemblée nationale, données mises à jour le … », et la page Méthode liste toutes les sources.
- **Pas d'aval officiel** : l'appli ne doit pas laisser croire qu'elle est un service de l'Assemblée (ni logo, ni nom approchant).
- **Distillation** : le modèle professeur doit autoriser l'usage de ses sorties pour entraîner un autre modèle. Avec Qwen3-30B-A3B (Apache 2.0) comme professeur, c'est le cas ; une API commerciale serait à vérifier au cas par cas.
- **Données personnelles** : les noms des députés et leurs propos publics restent des données personnelles au sens du RGPD ; leur traitement est à décrire dans les mentions légales.

## Licences à choisir pour le projet

| Production | Option recommandée | Alternative | Pourquoi |
| --- | --- | --- | --- |
| Code | AGPL-3.0 | MIT | L'AGPL oblige toute version hébergée modifiée à rester ouverte ; le MIT est plus simple et plus permissif |
| Résumés publiés (open data) | Licence Ouverte 2.0 | CC-BY 4.0 | Cohérent avec les données sources ; passe en ODbL si la base publiée dérive de données Tricoteuses (voir ci-dessous) |
| Modèle fine-tuné | Apache 2.0 | — | Héritée de Qwen3 |
| Documentation | CC-BY 4.0 | Licence Ouverte 2.0 | Réutilisable avec attribution |

**Décision du 28 octobre 2026** : le code est publié sous **AGPL-3.0**. Toute version modifiée mise en ligne devra donc rester ouverte, ce qui protège le projet d'une reprise fermée.

**Point d'attention (29 octobre)** : les données Tricoteuses sont sous ODbL, qui impose le partage à l'identique des bases dérivées. Si l'open data de nos résumés s'appuie sur des données Tricoteuses, elle devra être publiée sous ODbL plutôt que sous Licence Ouverte. L'ODbL est compatible avec la Licence Ouverte des données de l'Assemblée et avec l'AGPL du code.

Cette analyse n'est pas un avis juridique ; en cas de diffusion large, une relecture par un juriste est conseillée.
