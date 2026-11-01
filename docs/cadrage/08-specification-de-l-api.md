# Spécification de l'API

Une API REST en lecture seule, préfixée `/api/v1`, qui sert tous les écrans du front ; la spécification OpenAPI détaillée sera générée par FastAPI.

## Conventions

- **Format** : JSON, dates ISO 8601, identifiants AN conservés.
- **Pagination** : `limit` (20 par défaut, 100 maximum) et `cursor` ; la réponse contient `next_cursor`.
- **Erreurs** : `{"error": {"code": "not_found", "message": "…"}}` avec le code HTTP correspondant.
- **Lecture seule** : uniquement des GET ; aucune authentification en V1.
- **Cache** : en-têtes de cache d'une heure, invalidés après le run de nuit.

## Endpoints V1

| Écran | Endpoint | Paramètres | Renvoie |
| --- | --- | --- | --- |
| Actu | `GET /actu` | statut, cursor | Cartes de lois triées par importance et date |
| Actu | `GET /agenda` | semaine | Textes à l'ordre du jour |
| Chercher | `GET /lois` | q, statut, theme, cursor | Lois correspondantes |
| Chercher | `GET /interventions` | q, loi, groupe, depute, du, au, cursor | Interventions avec extrait surligné |
| Fiche loi | `GET /lois/{id}` | — | Loi, étapes, dernière fiche IA, scrutins |
| Fiche loi | `GET /lois/{id}/fiches` | version | Historique des fiches IA |
| Fiche loi | `GET /lois/{id}/seances` | — | Frise des débats (séances publiques ; réunions de commission en V1.1) |
| Séance | `GET /seances/{id}` | — | Séance, points de l'ordre du jour |
| Séance | `GET /seances/{id}/interventions` | q, groupe, depute, cursor | Interventions dans l'ordre |
| Séance | `GET /interventions/{id}` | — | Une intervention et son contexte |
| Vote | `GET /scrutins/{id}` | — | Résultat, votes par député, dissidents, données d'hémicycle |
| Chiffres | `GET /chiffres/composition` | legislature | Composition de l'hémicycle et participation aux scrutins par groupe |
| Référentiel | `GET /groupes`, `GET /groupes/{id}` | legislature | Groupes et composition |
| Référentiel | `GET /deputes`, `GET /deputes/{id}` | q, groupe | Députés |
| Comprendre l'AN | `GET /guides`, `GET /guides/{slug}` | — | Guides |
| Comprendre l'AN | `GET /glossaire` | — | Termes et définitions |
| Transparence | `GET /methode` | — | Résultats d'évaluation, version du modèle |
| Transparence | `GET /statut` | — | Dernier run de nuit, fraîcheur des données |

## Endpoints V1.1

| Endpoint | Renvoie |
| --- | --- |
| `GET /chiffres/groupes` | Cohésion, amendements, temps de parole par groupe et période |
| `GET /chiffres/proximite` | Matrice de proximité de vote entre groupes |
| `GET /interventions?mode=semantique` | Recherche sémantique |
| `GET /lois/{id}/amendements` | Amendements clés par groupe |

## Exemple : `GET /lois/{id}`

```json
{
  "id": "DLR5L17N12345",
  "titre_court": "Loi sur l'aide à mourir",
  "statut": "en_cours",
  "etape_courante": {"type": "seance", "chambre": "AN", "date": "2026-10-14"},
  "fiche": {
    "version": 3,
    "genere_le": "2026-10-15T03:12:00Z",
    "modele": "qwen3-4b-ft-v2",
    "synthese": "…",
    "positions": [
      {
        "groupe": {"id": "PO800000", "sigle": "XYZ"},
        "position": "contre",
        "arguments": [
          {
            "texte": "…",
            "citation": {"extrait": "…", "intervention_id": 4821, "verifiee": true, "confiance": 0.95}
          }
        ]
      }
    ]
  },
  "scrutins": [{"id": "VTANR5L17V1234", "resultat": "adopte", "pour": 305, "contre": 199}]
}
```

Les identifiants et valeurs de cet exemple sont fictifs.
