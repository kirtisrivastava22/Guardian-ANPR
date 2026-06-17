// @ts-ignore: Allow importing global CSS without type declarations
import "./globals.css";
import Navbar from "../components/Navbar";
import AlertToast from "../components/AlertToast";
import {
  AlertProvider,
} from "../contexts/AlertContext";

export const metadata = {
  title: "Guardian ANPR",
  description:
    "Real-Time Automatic Number Plate Recognition and Alert System",
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