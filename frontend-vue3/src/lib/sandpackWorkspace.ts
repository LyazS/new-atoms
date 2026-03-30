export const DEFAULT_WORKSPACE = {
  '/package.json': `{
  "name": "sandpack-vue-workspace",
  "private": true,
  "scripts": {
    "dev": "vite"
  },
  "dependencies": {
    "vue": "^3.3.2"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^4.2.3",
    "esbuild-wasm": "^0.17.19",
    "vite": "4.2.2"
  }
}
`,
  '/index.html': `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sandpack Vue Workspace</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
`,
  '/vite.config.ts': `import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
});
`,
  '/src/App.vue': `<template>
  <main></main>
</template>
`,
  '/src/main.js': `import { createApp } from "vue";
import App from "./App.vue";
import "./styles.css";

createApp(App).mount("#app");
`,
  '/src/styles.css': `body {
  margin: 0;
}
`,
}

export function cloneDefaultWorkspace() {
  return { ...DEFAULT_WORKSPACE }
}
