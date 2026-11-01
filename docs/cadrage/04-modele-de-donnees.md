# Modèle de données

L'intervention est l'entité centrale : la recherche, la frise des débats et les citations des résumés pointent toutes vers elle.

```mermaid
erDiagram
    LEGISLATURE ||--o{ DOSSIER : "regroupe"
    LEGISLATURE ||--o{ TEXTE : "numérote"
    LEGISLATURE ||--o{ SEANCE : "tient"
    DOSSIER ||--o{ ETAPE : "a"
    DOSSIER ||--o{ TEXTE : "comprend"
    TEXTE ||--o{ INTERVENTION : "discuté dans (numero_texte)"
    SEANCE ||--o{ POINT_ODJ : "contient"
    SEANCE ||--o{ INTERVENTION : "contient"
    POINT_ODJ |o--o{ INTERVENTION : "regroupe"
    SEANCE ||--o{ SCRUTIN : "a lieu pendant"
    DOSSIER |o--o{ SCRUTIN : "porte sur"
    SCRUTIN ||--o{ VOTE : "décompte"
    DEPUTE ||--o{ VOTE : "émet"
    DEPUTE |o--o{ INTERVENTION : "prononce"
    DEPUTE ||--o{ APPARTENANCE : "a"
    GROUPE ||--o{ APPARTENANCE : "compte"
    DOSSIER ||--o{ FICHE : "résumé par (versions)"
    FICHE ||--o{ POSITION_GROUPE : "contient"
    GROUPE ||--o{ POSITION_GROUPE : "concerne"
    POSITION_GROUPE ||--o{ ARGUMENT : "2 à 4"
    ARGUMENT ||--o{ CITATION : "appuyé par"
    INTERVENTION ||--o{ CITATION : "source de"

    LEGISLATURE { int numero PK  date debut  date fin }
    DOSSIER { text id PK  int legislature FK  text titre_officiel  text titre_court  text statut }
    TEXTE { int legislature PK  text numero PK  text dossier_id FK }
    SEANCE { text id PK  int legislature FK  text type  timestamptz debut  text url_compte_rendu }
    INTERVENTION { bigint id PK  text seance_id FK  int ordre  text depute_id FK  text groupe_id FK  text numero_texte FK  text texte }
    GROUPE { text id PK  text sigle  text couleur }
    DEPUTE { text id PK  text nom  text prenom }
    APPARTENANCE { text depute_id FK  text groupe_id FK  date debut  date fin }
    SCRUTIN { text id PK  text seance_id FK  text dossier_id FK  text resultat }
    VOTE { text scrutin_id FK  text depute_id FK  text groupe_id FK  text position }
    CITATION { bigint argument_id FK  bigint intervention_id FK  text extrait  bool verifiee }
```

*L'intervention est l'entité centrale. Le détail des champs est dans le dictionnaire de données.*

La liaison entre une loi et ses débats passe par le numéro du texte discuté : chaque intervention le porte, et la table texte, identifiée par le couple (législature, numéro), le relie au dossier. Le groupe d'un orateur se lit à la date de l'intervention via l'appartenance.

## Règles de conception

- **Identifiants de l'AN conservés** : chaque entité garde l'identifiant de l'open data (ex. PA… pour un député, PO… pour un organe), ce qui rend la collecte idempotente.
- **Le groupe est historisé** : un député peut changer de groupe ; l'intervention et le vote stockent le groupe à la date des faits.
- **Les orateurs non députés** (ministres, président de séance) sont des interventions sans député lié, avec un libellé et une qualité.
- **Les sorties IA sont versionnées** : une nouvelle fiche ne remplace pas l'ancienne, elle s'ajoute avec la version du modèle et du prompt.
- **Rien n'est supprimé** : les corrections de l'open data mettent à jour les lignes, avec une date de dernière mise à jour (`maj_le`).

## Entités hors schéma

| Entité | Rôle | Version |
| --- | --- | --- |
| Position de groupe, argument | Détail d'une fiche IA : un groupe, sa position, ses arguments ordonnés | V1 |
| Guide, terme du glossaire | Contenu de « Comprendre l'AN », lié aux termes des fiches | V1 |
| Run du pipeline | Historique des exécutions de nuit, statut, erreurs | V1 |
| Amendement | Auteur, groupe, article visé, sort, exposé sommaire | V1.1 |
| Indicateur de groupe | Participation, cohésion, proximité par période | V1.1 |
| Embedding d'intervention | Vecteur pour la recherche sémantique (pgvector) | V1.1 |
