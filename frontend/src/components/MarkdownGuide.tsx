import { useEffect, useId, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";

// Links between guides inside docs/ open the guide in Help instead of a repository path.
const GUIDE_LINKS: Record<string, string> = {
  "10_HOW_RECOMMENDATIONS_WORK.md": "how-recommendations-work",
  "11_TECHNICAL_REFERENCE.md": "technical-reference",
};

/** A mermaid diagram, rendered with the library loaded only when a guide needs it. */
function MermaidDiagram({ source }: { source: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    import("mermaid")
      .then(async ({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: {
            primaryColor: "#FEE6DF",
            primaryBorderColor: "#F96246",
            primaryTextColor: "#251F1C",
            lineColor: "#85776E",
            fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif",
          },
        });
        const rendered = await mermaid.render(`diagram${id}`, source);
        if (!cancelled) setSvg(rendered.svg);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [id, source]);

  if (failed) {
    return <pre className="overflow-x-auto rounded-xl bg-ink-900 p-3 text-xs text-sand-100">{source}</pre>;
  }
  if (!svg) {
    return <div className="skeleton h-40 w-full" aria-label="Loading diagram" />;
  }
  return <div className="my-4 overflow-x-auto rounded-xl border border-sand-200 bg-white p-3 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full" dangerouslySetInnerHTML={{ __html: svg }} />;
}

/** A guide written in Markdown (GitHub tables, code blocks, mermaid diagrams). */
export default function MarkdownGuide({ markdown }: { markdown: string }) {
  return (
    <div className="guide max-w-none text-sm leading-relaxed text-slate-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mb-3 text-2xl font-bold text-slate-900">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-8 border-b border-sand-200 pb-1 text-xl font-bold text-slate-900">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-5 text-base font-semibold text-slate-900">{children}</h3>,
          p: ({ children }) => <p className="my-2">{children}</p>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
          a: ({ href, children }) => {
            const guide = href ? GUIDE_LINKS[href] : undefined;
            if (guide) {
              return (
                <Link to={`/help?guide=${guide}`} className="font-semibold text-coral-700 hover:underline">
                  {children}
                </Link>
              );
            }
            if (!href || !/^https?:\/\//.test(href)) {
              return <span className="font-semibold text-slate-800">{children}</span>; // repository file: not reachable from the app
            }
            return (
              <a href={href} className="font-semibold text-coral-700 hover:underline" target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-xl border border-sand-200">
              <table className="w-full text-left text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-sand-50 text-slate-600">{children}</thead>,
          th: ({ children }) => <th className="px-3 py-2 font-semibold">{children}</th>,
          td: ({ children }) => <td className="border-t border-sand-100 px-3 py-2 align-top">{children}</td>,
          code: ({ className, children }) => {
            const text = String(children).replace(/\n$/, "");
            if (className === "language-mermaid") return <MermaidDiagram source={text} />;
            if (className) {
              return <code className="block overflow-x-auto whitespace-pre rounded-xl bg-ink-900 p-3 font-mono text-xs text-sand-100">{text}</code>;
            }
            return <code className="rounded bg-sand-100 px-1 py-0.5 font-mono text-[12px] text-slate-800">{text}</code>;
          },
          pre: ({ children }) => <div className="my-3">{children}</div>,
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
