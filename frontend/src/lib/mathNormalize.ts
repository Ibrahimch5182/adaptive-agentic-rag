/**
 * The generator occasionally emits inline LaTeX-ish math delimiters/macros around
 * arithmetic (e.g. "\(24 - 5 = 19\)", "\text{total}") that react-markdown has no
 * renderer for and would otherwise show as raw backslash syntax. Rather than pull in a
 * full math-rendering stack for occasional arithmetic, normalize the common tokens to
 * plain text so calculations read cleanly. Pure string transform — no HTML, no new
 * rendering authority over the (untrusted) generated text.
 */
export function normalizeMathText(text: string): string {
  return text
    .replace(/\\\[([\s\S]*?)\\\]/g, "$1")
    .replace(/\\\(([\s\S]*?)\\\)/g, "$1")
    .replace(/\$\$([\s\S]*?)\$\$/g, "$1")
    .replace(/\\text\{([^}]*)\}/g, "$1")
    .replace(/\\mathrm\{([^}]*)\}/g, "$1")
    .replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, "$1/$2")
    .replace(/\\times/g, "×")
    .replace(/\\div/g, "÷")
    .replace(/\\cdot/g, "·")
    .replace(/\\approx/g, "≈")
    .replace(/\\le/g, "≤")
    .replace(/\\ge/g, "≥")
    .replace(/\\%/g, "%");
}
