import type { MathfieldElementAttributes } from "mathlive";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "math-field": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & Partial<MathfieldElementAttributes>,
        HTMLElement
      >;
    }
  }
}
