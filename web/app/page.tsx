import { Suspense } from "react";
import { connection } from "next/server";

// Squelette du jalon 1 : prouve que la chaîne front → API → base fonctionne.
// L'écran Actu le remplacera.

type Statut = {
  dernier_run: { debut: string; statut: string } | null;
  derniere_seance: string | null;
};

async function EtatDesDonnees() {
  // Lu à chaque requête : l'adresse de l'API vient de l'environnement du conteneur.
  await connection();
  const urlApi = process.env.API_URL ?? "http://localhost:8000";

  let statut: Statut;
  try {
    const reponse = await fetch(`${urlApi}/api/v1/statut`);
    if (!reponse.ok) throw new Error(`HTTP ${reponse.status}`);
    statut = await reponse.json();
  } catch {
    return <p>API injoignable pour l’instant.</p>;
  }

  if (!statut.derniere_seance) {
    return <p>API connectée. Aucune séance chargée pour l’instant.</p>;
  }
  const date = new Date(statut.derniere_seance).toLocaleDateString("fr-FR", { dateStyle: "long" });
  return <p>Dernière séance chargée : {date}.</p>;
}

export default function Accueil() {
  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "32px 16px" }}>
      <h1 style={{ fontSize: 26, fontWeight: 700 }}>Mot pour mot</h1>
      <p style={{ marginTop: 8 }}>
        Ce que chaque groupe de l’Assemblée nationale pense d’une loi, avec des citations vérifiées
        mot pour mot.
      </p>
      <div style={{ marginTop: 24, fontSize: 14, color: "var(--texte-secondaire)" }}>
        <Suspense fallback={<p>Chargement de l’état des données…</p>}>
          <EtatDesDonnees />
        </Suspense>
      </div>
    </main>
  );
}
