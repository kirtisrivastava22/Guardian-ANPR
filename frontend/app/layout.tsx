// @ts-ignore: Allow importing global CSS without type declarations
import "./globals.css";
import Navbar from "../components/Navbar";
import AlertToast from "../components/AlertToast";
import {
  AlertProvider,
} from "../contexts/AlertContext";

export const metadata = {
  title: "RoadEye LPR",
  description:
    "License Plate Recognition System",
  icons: {
    icon: "/icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 min-h-screen">
        <AlertProvider>
          <Navbar />

          <AlertToast />

          <main className="max-w-7xl mx-auto px-8 py-8">
            {children}
          </main>
        </AlertProvider>
      </body>
    </html>
  );
}