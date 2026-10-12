import js from "@eslint/js";
import tseslint from "typescript-eslint";

const nameItFirst = "Name this value on its own line first.";

export default tseslint.config(
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["src/**/*.ts"],
    rules: {
      curly: ["error", "all"],
      "max-lines": ["error", { max: 100 }],
      "max-statements-per-line": ["error", { max: 1 }],
      "no-nested-ternary": "error",
      "no-multi-assign": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression > CallExpression.arguments",
          message: nameItFirst,
        },
        {
          selector: "NewExpression > CallExpression.arguments",
          message: nameItFirst,
        },
        {
          selector: "CallExpression > ConditionalExpression.arguments",
          message: nameItFirst,
        },
        {
          selector: "CallExpression > AwaitExpression.arguments",
          message: nameItFirst,
        },
        {
          selector: "Property > AwaitExpression.value",
          message: nameItFirst,
        },
      ],
    },
  }
);
