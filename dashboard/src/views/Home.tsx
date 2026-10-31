import { CrewStrip } from "../components/CrewStrip";
import { StatusBar } from "../components/StatusBar";

export default function Home() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="sr-only">Home</h1>
      <StatusBar />
      <CrewStrip />
    </div>
  );
}
