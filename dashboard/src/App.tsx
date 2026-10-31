import { BrowserRouter, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { StatusProvider } from "./hooks/StatusContext";
import Domain from "./views/Domain";
import Events from "./views/Events";
import History from "./views/History";
import Home from "./views/Home";
import Settings from "./views/Settings";

/** The routes, without a router or data, so tests can mount them in a MemoryRouter. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="domain/:name" element={<Domain />} />
        <Route path="history" element={<History />} />
        <Route path="events" element={<Events />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Home />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <StatusProvider>
        <AppRoutes />
      </StatusProvider>
    </BrowserRouter>
  );
}
