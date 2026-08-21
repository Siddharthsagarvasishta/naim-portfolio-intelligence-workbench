import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://naim-portfolio-intelligence-workbench.openai.site"),
  title: {
    default: "nAIM Portfolio Intelligence Workbench",
    template: "%s · nAIM",
  },
  description:
    "Name the movement. Own the evidence. nAIM (pronounced name; All Is Mine) is a governed, synthetic portfolio intelligence workbench.",
  applicationName: "nAIM Portfolio Intelligence Workbench",
  keywords: [
    "portfolio risk analytics",
    "credit risk",
    "fraud risk",
    "early warning",
    "strategy testing",
    "synthetic data",
  ],
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    title: "nAIM Portfolio Intelligence Workbench",
    description:
      "Name the movement. Own the evidence. Governed synthetic portfolio intelligence from nAIM.",
    type: "website",
    siteName: "nAIM Portfolio Intelligence Workbench",
    images: [
      {
        url: "/og.png",
        width: 1672,
        height: 941,
        alt: "nAIM Portfolio Intelligence Workbench analytical preview",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "nAIM Portfolio Intelligence Workbench",
    description:
      "Name the movement. Own the evidence. Governed portfolio monitoring, root cause, strategy and scenario evidence.",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
