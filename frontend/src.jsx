import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function extract(event) {
    event.preventDefault();
    setResult(null);
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/extract", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo procesar el archivo.");
      }
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "cuestionario.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <main>
    <h1>Extractor de cuestionarios</h1>
    <p>Convierte cuestionarios numerados en JSON. Usa documentos inventados o de dominio público.</p>
    <form onSubmit={extract}>
      <label htmlFor="file">Documento · PDF, DOCX o XLSX · hasta 8 MiB</label>
      <input id="file" type="file" accept=".pdf,.docx,.xlsx" required disabled={busy}
        onChange={event => { setFile(event.target.files[0]); setResult(null); setError(""); }} />
      <button disabled={busy || !file}>{busy ? "Procesando…" : "Extraer ítems"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <section aria-label="Resultado">
      <h2>{result.titulo}</h2>
      <p>{result.total_items} ítems · {result.idioma}</p>
      <button onClick={download}>Descargar JSON</button>
      <pre tabIndex={0}>{JSON.stringify(result, null, 2)}</pre>
    </section>}
  </main>;
}
createRoot(document.getElementById("root")).render(<App />);
