/** Small syntax-highlighted JSON block (no dependency). */
export default function JsonView({ value }) {
  const json = JSON.stringify(value, null, 2);
  const parts = json.split(/("(?:\\.|[^"\\])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?)/g);
  return (
    <pre className="overflow-auto rounded-md bg-ink p-3 font-mono text-[11.5px] leading-relaxed text-[#e9e4ee]">
      {parts.map((p, i) => {
        if (/^".*":$/.test(p)) return <span key={i} className="text-[#e0a3cb]">{p}</span>;
        if (/^"/.test(p)) return <span key={i} className="text-[#8fd6b0]">{p}</span>;
        if (/^(true|false|null)$/.test(p)) return <span key={i} className="text-[#f0c36a]">{p}</span>;
        if (/^-?\d/.test(p)) return <span key={i} className="text-[#f0c36a]">{p}</span>;
        return p;
      })}
    </pre>
  );
}
