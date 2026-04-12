import { useEffect, useState } from "react";

function App() {
  const [status, setStatus] = useState("loading...");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("http://127.0.0.1:8000/status")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => setStatus(data.status))
      .catch((err) => {
        console.error("Fetch error:", err);
        setError(err.message);
        setStatus("failed");
      });
  }, []);

  return (
    <div>
      <h1>Engine: {status}</h1>
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
    </div>
  );
}

export default App;
