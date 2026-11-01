# Protocole d'évaluation

Le modèle mis en production est le plus petit qui atteint tous les seuils ci-dessous sur un jeu de test fixe ; aucun choix de modèle ou de prompt ne se fait sans ce protocole.

## Jeux de données

| Jeu | Taille | Usage | Règle |
| --- | --- | --- | --- |
| Développement | 10 lois | Itérer sur les prompts et les réglages | Libre d'usage |
| Test | 20 lois | Mesurer et comparer les candidats | Jamais utilisé pour entraîner ni pour ajuster un prompt |
| Entraînement | Quelques centaines d'exemples | Fine-tuning (distillation) | Aucune loi du jeu de test |

**Composition du jeu de test** : variété de thèmes (social, économie, sécurité, environnement…), de tailles de débat (court, long, budgétaire), de statuts, et au moins une loi où un groupe est divisé et une où un groupe ne s'est pas exprimé.

**Référence** : pour chaque loi du test, une fiche produite par un gros modèle puis corrigée et validée à la main (position de chaque groupe, arguments attendus).

## Métriques et seuils

| Métrique | Calcul | Seuil |
| --- | --- | --- |
| Citations exactes | Part des extraits retrouvés mot pour mot, avant filtrage | ≥ 95 % |
| Format valide | Part des sorties conformes au schéma JSON | 100 % après régénération |
| Position correcte | Accord avec la position de référence (pour, contre, divisé, pas exprimé) | ≥ 90 % |
| Couverture des arguments | Part des arguments de référence retrouvés (jugé par modèle juge) | ≥ 75 % |
| Attribution correcte | Part des citations venant bien du groupe résumé | 100 % |
| Neutralité | Note de 1 à 5 par le modèle juge, selon une grille tirée de la charte | Moyenne ≥ 4, aucun groupe < 3,5 |
| Équité de longueur | Écart de longueur moyenne des résumés entre groupes | ≤ 15 % |
| Temps par loi | Durée de génération sur la RTX 3060 | Run de nuit < 8 h |

## Modèle juge

- Un modèle plus gros que le candidat (ex. MoE 30B local) note neutralité et couverture avec une grille écrite.
- **Calibration** : 20 sorties notées à la main et par le juge ; si l'accord est trop faible, la grille est revue.
- Le juge ne note jamais ses propres sorties.

## Procédure

1. Geler le jeu de test et la référence (version dans le dépôt).
2. Lancer chaque candidat sur les 20 lois avec la même version de prompt.
3. Calculer les métriques par script ; lancer le juge.
4. Relire à la main un échantillon de 5 fiches par candidat.
5. Consigner les résultats dans le tableau ci-dessous et dans le journal d'expériences.
6. Retenir le plus petit candidat qui passe tous les seuils ; sinon, améliorer données ou prompt et recommencer.

## Résultats

| Candidat | Citations exactes | Position correcte | Couverture | Neutralité | Équité longueur | Temps / loi | Décision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Référence (gros modèle) |  |  |  |  |  |  |  |
| Qwen3 4B sans entraînement |  |  |  |  |  |  |  |
| Qwen3 1,7B fine-tuné |  |  |  |  |  |  |  |
| Qwen3 4B fine-tuné |  |  |  |  |  |  |  |

Les résultats retenus sont publiés sur la page Méthode.
