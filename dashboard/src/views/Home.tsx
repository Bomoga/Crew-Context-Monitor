import { CrewStrip } from "../components/CrewStrip";
import { RiskCards } from "../components/RiskCards";
import { StatusBar } from "../components/StatusBar";

export default function Home() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sr-only">Home</h1>
      <StatusBar />
      <CrewStrip />
      <RiskCards />
    </div>
  );
}
