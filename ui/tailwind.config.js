/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: { extend: {} },
  // antd provides its own base styles
  corePlugins: { preflight: false },
  plugins: [],
};
