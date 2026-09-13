import { Layout } from "./components/Layout";
import { RouterProvider } from "./router/Router";

export function App() {
  return (
    <RouterProvider>
      <Layout />
    </RouterProvider>
  );
}
