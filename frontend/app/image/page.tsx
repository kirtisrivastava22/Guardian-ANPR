"use client";
import { useState } from "react";
import { Upload, Image, CheckCircle2, Loader2 } from "lucide-react";

interface DetectionResult {
  plate_number: string;
  confidence: number;
  id: number;
}

export default function ImagePage() {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [annotatedImage, setAnnotatedImage] = useState<string | null>(null);
  const [results, setResults] = useState<DetectionResult[]>([]);
  const [loading, setLoading] = useState(false);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setPreview(URL.createObjectURL(selectedFile));
      setResults([]);
      setAnnotatedImage(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const controller = new AbortController();
      setTimeout(() => controller.abort(), 60000); // 60s

      const res = await fetch(`${API_BASE}/detect/image`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      const data = await res.json();
      setResults(data.detections || []);

      if (data.annotated_image) {
        setAnnotatedImage(`data:image/jpeg;base64,${data.annotated_image}`);
      }
    } catch (error) {
      console.error("Detection failed:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="bg-white
  rounded-3xl
  shadow-sm
  border border-slate-200
  p-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-4xl font-bold text-cyan-400 mb-8 flex items-center gap-3">
            <Image className="w-10 h-10" />
            Image License Plate Detection
          </h1>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <div className=" border-2 border-dashed border-slate-300
    rounded-3xl
    bg-gray-800
    p-16
    text-center
    hover:border-slate-500
    transition-all">
                <h2 className="text-xl font-semibold text-white mb-4">
                  Upload Image
                </h2>

                <div className="space-y-4">
                  <div
                    className="border-2 border-dashed border-slate-600 rounded-lg p-8 text-center hover:border-cyan-500 transition-colors cursor-pointer"
                    onClick={() =>
                      document.getElementById("file-input")?.click()
                    }
                  >
                    {preview ? (
                      <div className="space-y-2">
                        <CheckCircle2 className="w-12 h-12 mx-auto text-green-400" />
                        <p className="text-slate-300">
                          Image selected: {file?.name}
                        </p>
                        <p className="text-sm text-slate-500">
                          Click to change
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Upload className="w-12 h-12 mx-auto text-slate-400" />
                        <p className="text-slate-300">
                          Click to upload or drag and drop
                        </p>
                        <p className="text-sm text-slate-500">
                          PNG, JPG up to 10MB
                        </p>
                      </div>
                    )}
                    <input
                      id="file-input"
                      type="file"
                      accept="image/*"
                      onChange={handleFileSelect}
                      className="hidden"
                    />
                  </div>

                  <button
                    onClick={handleUpload}
                    disabled={!file || loading}
                    className="px-5 py-3
    rounded-xl
    bg-slate-900
    text-white
    font-medium
    hover:bg-slate-800
    transition-all
    duration-300"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      "Detect License Plates"
                    )}
                  </button>
                </div>
              </div>

              {(preview || annotatedImage) && (
                <div className="bg-slate-800/50 backdrop-blur rounded-xl p-6 border border-slate-700">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {preview && (
                      <div>
                        <h3 className="text-sm font-semibold text-slate-300 mb-2">
                          Original Image
                        </h3>
                        <img
                          src={preview}
                          alt="Original"
                          className="w-full rounded-lg border-2 border-slate-600"
                        />
                      </div>
                    )}
                    {annotatedImage && (
                      <div>
                        <h3 className="text-sm font-semibold text-green-400 mb-2">
                          Detected Plates
                        </h3>
                        <img
                          src={annotatedImage}
                          alt="Annotated"
                          className="w-full rounded-lg border-2 border-green-500/50"
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="lg:col-span-1">
              <div className="bg-slate-800 backdrop-blur rounded-xl p-6 border border-slate-700 sticky top-6">
                <h2 className="text-xl font-semibold text-white mb-4">
                  Detection Results
                </h2>

                <div className="mb-4 p-3 bg-slate-700/50 rounded-lg">
                  <p className="text-sm text-slate-300">
                    Plates Found:{" "}
                    <span className="font-bold text-cyan-400">
                      {results.length}
                    </span>
                  </p>
                </div>

                <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
                  {results.length === 0 ? (
                    <div className="text-center py-12 text-slate-400">
                      <Image className="w-12 h-12 mx-auto mb-3 opacity-50" />
                      <p>No detections yet</p>
                      <p className="text-xs mt-1">
                        Upload an image to detect plates
                      </p>
                    </div>
                  ) : (
                    results.map((result, index) => (
                      <div
                        key={index}
                        className="bg-slate-700/50 rounded-lg p-4 border border-slate-600"
                      >
                        <p className="font-mono text-2xl font-bold text-white mb-2">
                          {result.plate_number}
                        </p>

                        <div className="mt-3">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-slate-400">Confidence</span>
                            <span className="text-cyan-400 font-semibold">
                              {(result.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full bg-slate-600 rounded-full h-1.5">
                            <div
                              className="bg-cyan-500 h-1.5 rounded-full"
                              style={{ width: `${result.confidence * 100}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
