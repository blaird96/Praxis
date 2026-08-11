import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  children: string;
  /** Render without a wrapping block element, for use inside <li>/<span>. */
  inline?: boolean;
};

/**
 * Renders scenario-authored assignment text (titles, summaries, objectives).
 * Raw HTML is never enabled - this content is trusted (local scenario code)
 * but there is no reason to allow HTML injection through it.
 */
export function Markdown({ children, inline = false }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={inline ? { p: "span" } : undefined}
    >
      {children}
    </ReactMarkdown>
  );
}
