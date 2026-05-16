import "./globals.css";

export const metadata = {
  title: "ClausePilot",
  description: "AI Contract / Document Assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}

