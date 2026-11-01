import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Tout en Inter (wireframes, direction artistique).
const inter = Inter({
  variable: "--police-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Mot pour mot",
  description:
    "Ce que chaque groupe de l'Assemblée nationale pense d'une loi, avec des citations vérifiées mot pour mot.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
