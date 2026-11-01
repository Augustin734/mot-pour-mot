# ADR — Décisions d'architecture

Les dix décisions sont prises ; chaque ADR dit pourquoi, et ce qu'on a écarté.

| N° | Décision | Statut |
| --- | --- | --- |
| 001 | Appli avec serveur plutôt que site statique | Acceptée |
| 002 | PostgreSQL pour les données et la recherche | Acceptée |
| 003 | FastAPI pour l'API | Acceptée |
| 004 | Petit modèle local fine-tuné pour les résumés | Acceptée |
| 005 | Hébergement sur le PC, ouverture via Cloudflare Tunnel | Acceptée |
| 006 | Open data AN comme source de vérité | Acceptée |
| 007 | Sorties IA versionnées, jamais écrasées | Acceptée |
| 008 | Vérification des citations mot pour mot | Acceptée |
| 009 | Docker Compose pour l'installation | Acceptée |
| 010 | Front : React + Next.js | Acceptée |

## ADR-001 — Appli avec serveur

**Contexte** : la recherche dans des centaines de milliers d'interventions, avec filtres par date, groupe et orateur, dépasse ce qu'un site statique fait bien.

**Décision** : une API et une base, servies depuis le PC.

**Écarté** : site statique avec index côté client (index trop lourd, pas de filtres croisés, pas d'évolution vers des fonctions dynamiques).

**Conséquences** : un serveur à maintenir et à sécuriser ; l'appli dépend du PC allumé.

## ADR-002 — PostgreSQL

**Contexte** : il faut des données relationnelles (lois, séances, votes), une recherche plein texte en français et, plus tard, une recherche sémantique.

**Décision** : PostgreSQL avec la recherche plein texte native (configuration française) et pgvector.

**Écarté** : Elasticsearch ou Meilisearch (un service de plus à synchroniser) ; SQLite (moins adapté à la recherche et à la concurrence).

**Conséquences** : une seule base à gérer ; si la pertinence de recherche déçoit, un moteur dédié pourra s'ajouter.

## ADR-003 — FastAPI

**Contexte** : la stack est Python ; l'API est en lecture seule.

**Décision** : FastAPI, avec schémas Pydantic et documentation OpenAPI générée.

**Écarté** : Django (plus lourd pour une API simple) ; Node (deuxième langage côté serveur).

**Conséquences** : mêmes modèles de données partagés entre pipeline et API.

## ADR-004 — Petit modèle local fine-tuné

**Contexte** : tâche étroite et répétitive, budget de 0 €, objectif d'apprendre l'entraînement de modèles.

**Décision** : Qwen3 1,7B à 4B fine-tuné en QLoRA sur la RTX 3060, choisi par comparaison sur un jeu de test fixe.

**Écarté** : API payante (coût, dépendance) ; API gratuite seule (quotas instables).

**Conséquences** : dataset à construire par distillation ; une couche d'abstraction permet de changer de modèle.

## ADR-005 — Hébergement sur le PC

**Contexte** : 0 €, usage personnel puis entre amis.

**Décision** : tout sur le PC ; Cloudflare Tunnel pour l'accès externe.

**Écarté** : VPS (quelques euros par mois) ; ouverture de port sur la box (risque de sécurité).

**Conséquences** : disponibilité liée au PC ; migration prévue par Docker Compose.

## ADR-006 — Open data AN comme source de vérité

**Contexte** : plusieurs sources se recoupent (AN, DILA, Tricoteuses, Datan).

**Décision** : l'open data AN fait foi ; Tricoteuses complète (textes des lois, fraîcheur, commissions en V1.1), Datan sert de contrôle. La liaison séance ↔ loi se fait sur les données AN, par le numéro du texte discuté.

**Conséquences** : en cas de désaccord, la valeur AN est gardée et l'écart journalisé.

## ADR-007 — Sorties IA versionnées

**Décision** : chaque régénération crée une nouvelle version de fiche, avec modèle et prompt.

**Pourquoi** : historique des fiches, audit des erreurs signalées, comparaison entre modèles.

## ADR-008 — Vérification des citations

**Décision** : une citation n'est publiée que si elle existe mot pour mot (après normalisation des espaces et de la ponctuation) dans l'intervention liée.

**Pourquoi** : c'est la garantie principale contre les hallucinations et le socle de l'indice de confiance.

## ADR-009 — Docker Compose

**Décision** : base, API et front en conteneurs ; modèle hors conteneur pour l'accès GPU.

**Pourquoi** : installation en une commande, utile pour les contributeurs et une future migration.

## ADR-010 — React avec Next.js pour le front

**Décision** (28 octobre 2026) : React avec Next.js.

**Pourquoi** : le framework le plus demandé en entretien et le plus documenté ; le rendu côté serveur de Next.js rend les fiches loi lisibles par les moteurs de recherche, utile quand quelqu'un cherche une loi sur Google.

**Écarté** : SvelteKit (plus simple, mais moins présent sur le marché de l'emploi) ; Vue avec Nuxt (solide, mais sans avantage décisif ici).
