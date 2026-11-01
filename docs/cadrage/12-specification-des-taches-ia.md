# Spécification des tâches IA

Sept tâches, dont trois en V1 ; chacune a une entrée définie, une sortie JSON validée par schéma, et son propre jeu d'évaluation.

| Code | Tâche | Entrée | Sortie | Modèle | Version |
| --- | --- | --- | --- | --- | --- |
| T1 | Position d'un groupe sur une loi | Interventions du groupe sur la loi | Position, 2 à 4 arguments cités | Petit modèle fine-tuné | V1 |
| T2 | Synthèse globale d'une loi | Titre + sorties T1 de tous les groupes | Synthèse, points d'accord et de désaccord | Petit modèle fine-tuné | V1 |
| T3 | Titre court et alias | Titre officiel, exposé des motifs | Titre clair, noms médiatiques probables | Petit modèle | V1 |
| T4 | Thèmes | Titre, synthèse | 1 à 3 thèmes d'une liste fermée | Petit modèle | V1.1 |
| T5 | « Ce que ça change » | Texte de loi | 3 à 6 changements en langage clair | Petit modèle fine-tuné | V1.1 |
| T6 | Amendements clés | Exposés sommaires d'amendements | Résumé d'une phrase par amendement | Petit modèle | V1.1 |
| T7 | Discours vs vote | Sortie T1 + vote du groupe | Cohérent, nuancé ou incohérent, justifié | Modèle MoE moyen + relecture humaine | V2 |

## T1 — Position d'un groupe sur une loi

**Entrée** : la loi (titre, étape), le groupe (nom officiel), la liste de ses interventions sur la loi, chacune avec son identifiant, son orateur et son texte. Si le total dépasse le contexte du modèle, les interventions sont d'abord découpées par article puis résumées en deux passes.

**Sortie** :

```json
{
  "groupe_id": "PO800000",
  "position": "pour | contre | divise | pas_exprime",
  "arguments": [
    {
      "texte": "Le groupe estime que …",
      "citations": [
        {"intervention_id": 4821, "extrait": "texte exact copié de l'intervention"}
      ]
    }
  ]
}
```

**Contraintes** :

- 2 à 4 arguments, 40 mots maximum chacun, introduits par le groupe.
- Au moins une citation par argument ; `extrait` copié mot pour mot, 40 mots maximum ; `intervention_id` pris dans l'entrée.
- `pas_exprime` si aucune intervention ; `arguments` est alors vide.
- `divise` si des orateurs du groupe défendent des positions opposées ; les arguments couvrent les deux côtés.

**Contrôles après génération** : schéma JSON valide, identifiants existants, extraits retrouvés dans le texte source (après normalisation des espaces et de la ponctuation), longueurs respectées. Un échec déclenche une régénération (2 essais maximum), puis la fiche est marquée « à relire ».

## T2 — Synthèse globale

**Entrée** : titre et étape de la loi, sorties T1 validées de tous les groupes.

**Sortie** : `synthese` (80 mots maximum : de quoi parle le texte et où en est le débat), `accords` et `desaccords` (3 points maximum chacun, chacun citant les groupes concernés).

**Contrainte** : n'utiliser que l'information présente dans les sorties T1 ; aucun groupe n'est mis en avant.

## T3 — Titre court et alias

**Sortie** : `titre_court` (8 mots maximum, sans jugement), `alias` (0 à 3 noms d'usage). Les alias sont relus à la main pour les lois de l'écran Actu.

## Règles communes

- Sorties toujours en JSON, validées par schéma (génération contrainte par grammaire quand le moteur le permet).
- Chaque sortie stocke : modèle, version du prompt, date, statut des contrôles.
- Une tâche ne passe en production qu'après avoir atteint les seuils du protocole d'évaluation.
