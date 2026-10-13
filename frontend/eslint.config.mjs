import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Listing photos come from third-party CDNs that block server-side
      // fetches (hotlink protection), so next/image's optimiser can't be
      // used — plain <img> with lazy loading is intentional.
      "@next/next/no-img-element": "off",
    },
  },
];

export default eslintConfig;
